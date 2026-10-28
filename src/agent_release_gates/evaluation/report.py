import html
import json
from datetime import datetime


def report_metrics(inputs: dict, manifests: dict) -> dict:
    qualification = inputs["qualification"]
    provenance = {"assistant_live": "assistant", "human_live": "human", "scripted": "scripted"}.get(
        qualification.get("study_mode"), "unqualified"
    )
    observations = []
    for key in ["baseline", "candidate"]:
        version = inputs.get(key)
        if not version:
            continue
        for case in version["cases"]:
            manifest = manifests[case["run_id"]]
            start = datetime.fromisoformat(manifest["started_at"])
            end = datetime.fromisoformat(manifest["ended_at"])
            derived = manifest["mode"] == "fault_control"
            observations.append(
                {
                    "version": key,
                    "run_id": case["run_id"],
                    "case_id": case["case_id"],
                    "family_id": manifest["family_id"],
                    "mode": manifest["mode"],
                    "derived_control": derived,
                    "agent_elapsed_ms": None if derived else (end - start).total_seconds() * 1000,
                    "source_interval_ms": (end - start).total_seconds() * 1000,
                    "usage": manifest["usage"],
                    "exact_checks": case["exact"]["checks"],
                    "judge_usage": [j["usage"] for j in case["judges"]],
                    "judge_elapsed_ms": [
                        (
                            datetime.fromisoformat(j["ended_at"])
                            - datetime.fromisoformat(j["started_at"])
                        ).total_seconds()
                        * 1000
                        for j in case["judges"]
                    ],
                }
            )
    natural = {r["run_id"]: r for r in observations if not r["derived_control"]}
    judges = {
        j.get("receipt_digest")
        or f"{case['run_id']}:{j['repetition']}:{j.get('settings_digest')}": j
        for key in ["baseline", "candidate"]
        for case in (inputs.get(key) or {}).get("cases", [])
        for j in case["judges"]
    }
    agent_cost = sum(r["usage"]["cost_nano_usd"] or 0 for r in natural.values())
    judge_cost = sum(j["usage"]["cost_nano_usd"] or 0 for j in judges.values())
    return {
        "scope": (
            "Saved-run evaluation against assistant-generated reference labels; human agreement is unmeasured."
            if provenance == "assistant"
            else "saved-run evaluation; scripted labels/judges are not human/live evidence"
        ),
        "review_mode": inputs.get("review_mode", "human"),
        "reference_provenance": provenance,
        "human_validation": provenance == "human" and qualification.get("status") == "pass",
        "observations": observations,
        "natural_case_runs": len(natural),
        "case_families": len({r["family_id"] for r in observations}),
        "qualification": inputs["qualification"],
        "derived_control_costs": "Parent capture usage is retained for provenance, excluded from new-inference totals.",
        "known_agent_cost_nano_usd": agent_cost,
        "known_judge_cost_nano_usd": judge_cost,
        "known_total_cost_nano_usd": agent_cost + judge_cost,
        "unknown_judge_charges": sum(j["usage"]["state"] == "unknown" for j in judges.values()),
        "reserved_judge_cost_nano_usd": sum(
            j["usage"]["reserved_nano_usd"] for j in judges.values()
        ),
        "unknown_agent_charges": sum(r["usage"]["state"] == "unknown" for r in natural.values()),
        "reserved_agent_cost_nano_usd": sum(
            r["usage"]["reserved_nano_usd"] for r in natural.values()
        ),
    }


def render_report(record: dict) -> str:
    return (
        '<!doctype html><meta charset="utf-8"><title>Release evidence</title><h1>Release evidence</h1><pre>'
        + html.escape(json.dumps(record, indent=2, ensure_ascii=False))
        + "</pre>"
    )
