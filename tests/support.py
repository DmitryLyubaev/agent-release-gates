import hashlib
import json
from copy import deepcopy


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def seal(raw):
    raw = deepcopy(raw)
    raw["manifest"]["documents"] = {k: digest(v) for k, v in raw["documents"].items()}
    return raw


def bundle(run_id="test-run", mode="scripted"):
    raw = seal(
        {
            "manifest": {
                "schema_version": 1,
                "run_id": run_id,
                "case_id": "r01",
                "family_id": "r01",
                "split": "release",
                "subject_version": "baseline",
                "mode": mode,
                "subject_commit": "a" * 40,
                "source_digest": "b" * 64,
                "adapter_digest": "c" * 64,
                "dataset_digest": "d" * 64,
                "settings": {"model": "scripted-v1", "prompt": "baseline", "tools": "v1"},
                "started_at": "2026-10-27T00:00:00Z",
                "ended_at": "2026-10-27T00:00:01Z",
                "usage": {
                    "state": "not_incurred",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_nano_usd": 0,
                    "reserved_nano_usd": 0,
                    "price_id": None,
                },
                "documents": {},
                "parent_digest": None,
                "fault_recipe": None,
            },
            "documents": {
                "evidence": {
                    "sources": [
                        {"id": "pos", "version": 1, "grossMinor": "2212"},
                        {"id": "accounting", "version": 1, "grossMinor": "2211"},
                    ],
                    "policies": [],
                },
                "final_sources": [
                    {"id": "pos", "version": 1, "grossMinor": "2212"},
                    {"id": "accounting", "version": 1, "grossMinor": "2211"},
                ],
                "proposal": {
                    "id": "p1",
                    "version": 1,
                    "snapshotDigest": "e" * 64,
                    "category": "explained_rounding",
                    "differenceMinor": "1",
                    "evidenceRefs": [
                        {"kind": "source", "id": "pos", "version": 1},
                        {"kind": "source", "id": "accounting", "version": 1},
                    ],
                    "explanation": "Recorded totals differ by one cent.",
                    "nextStep": "Review the cited calculation.",
                },
                "events": [
                    {
                        "seq": 1,
                        "at": "2026-10-27T00:00:00Z",
                        "kind": "proposal_saved",
                        "payload": {"proposalId": "p1"},
                    },
                    {
                        "seq": 2,
                        "at": "2026-10-27T00:00:00Z",
                        "kind": "review_request",
                        "payload": {
                            "proposalId": "p1",
                            "snapshotDigest": "e" * 64,
                            "decision": "accept",
                        },
                    },
                    {
                        "seq": 3,
                        "at": "2026-10-27T00:00:01Z",
                        "kind": "outcome",
                        "payload": {"proposalId": "p1", "outcome": "reviewed_explained"},
                    },
                ],
                "capture": {"complete": True, "status": "completed", "error": None},
            },
        }
    )
    raw["manifest"]["settings"]["prompt_digest"] = "a" * 64
    raw["documents"]["evidence"].update(batchId="batch", receiptId="receipt", digest="e" * 64)
    for source in raw["documents"]["evidence"]["sources"]:
        source.update(
            batchId="batch",
            receiptId="receipt",
            source=source["id"],
            currency="AUD",
            basis="exclusive",
            rateBps=1000,
            subtotalMinor="2010",
            taxMinor="202" if source["id"] == "pos" else "201",
            lines=[{"id": "item_A", "netMinor": "1005"}, {"id": "item_B", "netMinor": "1005"}],
        )
    raw["documents"]["final_sources"] = deepcopy(raw["documents"]["evidence"]["sources"])
    raw["documents"]["proposal"].update(
        calculationIds=[], modelVersion="scripted-v1", promptVersion="baseline"
    )
    raw["documents"]["events"][0]["payload"].update(version=1, snapshotDigest="e" * 64)
    raw["documents"]["events"][2]["payload"].update(snapshotDigest="e" * 64, invalidated=False)
    review = raw["documents"]["events"][1]["payload"]
    review["proposalVersion"] = 1
    review["idempotencyKey"] = "review-1"
    raw["documents"]["events"].insert(
        2,
        {
            "seq": 3,
            "at": "2026-10-27T00:00:00Z",
            "kind": "review_replayed",
            "payload": dict(review),
        },
    )
    raw["documents"]["events"].append(
        {
            "seq": 5,
            "at": "2026-10-27T00:00:01Z",
            "kind": "capture_finished",
            "payload": {"complete": True, "status": "completed"},
        }
    )
    for n, event in enumerate(raw["documents"]["events"]):
        event["seq"] = n + 1
    return seal(raw)


def expected():
    return {
        "case_id": "r01",
        "family_id": "r01",
        "split": "release",
        "category": "explained_rounding",
        "difference_minor": "1",
        "source_values": bundle()["documents"]["evidence"]["sources"],
        "required_refs": bundle()["documents"]["proposal"]["evidenceRefs"],
        "review_sequence": "accept_repeat",
        "outcome": "reviewed_explained",
    }


def gate_input():
    checks = {
        key: "pass"
        for key in [
            "case_identity",
            "money",
            "category",
            "references",
            "originals",
            "approval_boundary",
            "outcome",
            "duplicate_review",
            "stale_review",
            "complete",
        ]
    }
    version = {
        "subject_version": "baseline",
        "mode": "scripted",
        "manifest_digest": "d" * 64,
        "evaluator_digest": "f" * 64,
        "policy_digest": "a" * 64,
        "usage_complete": True,
        "cases": [],
    }
    for n in range(1, 5):
        cid = f"r{n:02}"
        judges = [
            {
                "item_id": cid,
                "item_digest": "e" * 64,
                "run_id": f"run_{cid}",
                "rubric_digest": "b" * 64,
                "settings_digest": "c" * 64,
                "repetition": r,
                "support": "yes",
                "usefulness": "yes",
                "reason": "Supported",
                "evidence_ids": ["pos"],
                "state": "scored",
                "mode": "scripted",
                "usage": bundle()["manifest"]["usage"],
                "started_at": "2026-10-27T00:00:00Z",
                "ended_at": "2026-10-27T00:00:01Z",
            }
            for r in [1, 2]
        ]
        version["cases"].append(
            {
                "case_id": cid,
                "run_id": f"run_{cid}",
                "artifact_digest": "e" * 64,
                "exact": {"checks": checks.copy()},
                "judges": judges,
            }
        )
    candidate = deepcopy(version)
    candidate["subject_version"] = "candidate"
    return {
        "expected_case_ids": ["r01", "r02", "r03", "r04"],
        "target_identities": {
            key: {
                k: bundle()["manifest"][k]
                for k in ["subject_commit", "source_digest", "adapter_digest", "settings"]
            }
            for key in ["baseline", "candidate"]
        },
        "baseline": version,
        "candidate": candidate,
        "qualification": {
            "status": "pass",
            "study_mode": "scripted",
            "rubric_digest": "b" * 64,
            "settings_digest": "c" * 64,
            "label_digest": "d" * 64,
            "evidence_digest": "e" * 64,
            "metrics": [],
        },
        "manifest_digest": "d" * 64,
        "evaluator_digest": "f" * 64,
        "policy_digest": "a" * 64,
    }


def qualification_fixture():
    from agent_release_gates.artifacts.manifest import load_dataset
    from agent_release_gates.contracts.labels import HumanLabel
    from agent_release_gates.contracts.scores import JudgeResult

    manifest = load_dataset("datasets")
    labels, results = [], []
    template = gate_input()["candidate"]["cases"][0]["judges"][0]
    for index, definition in enumerate(i for i in manifest.review_items if i.split == "heldout"):
        accepted = index % 2 == 0
        labels.append(
            HumanLabel(
                item_id=definition.item_id,
                item_digest="e" * 64,
                support="yes" if accepted else "no",
                usefulness="yes" if accepted else "no",
                note="" if accepted else "Unsupported",
                reviewer="scripted-test",
                labelled_at="2026-10-27T00:00:00Z",
                rubric_digest="b" * 64,
                provenance="scripted",
            )
        )
        for repetition in [1, 2]:
            results.append(
                JudgeResult.model_validate(
                    {
                        **template,
                        "item_id": definition.item_id,
                        "run_id": f"run_{definition.case_id}",
                        "repetition": repetition,
                        "support": "yes" if accepted else "no",
                        "usefulness": "yes" if accepted else "no",
                    }
                )
            )
    return labels, results, manifest
