"""Synthetic live-boundary fixtures. These are never actual human/model evidence."""

import hashlib
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from tests.live_support import allowance, judge_reply, ledger


def study_config(root):
    approval = allowance(
        root, dataset_digest=hashlib.sha256(Path("datasets/manifest.json").read_bytes()).hexdigest()
    )
    approval["allowed_stages"] = ["calibration", "calibration_development", "heldout", "release"]
    return {"approval": approval, "subject_root": str(Path(".local/subject").resolve())}


def synthetic_capture(config, requested):
    definition, version, stage, investigation = (
        requested[k] for k in ["case", "version", "stage", "investigation_id"]
    )
    root = Path("examples/scripted")
    source = next(
        (
            raw
            for path in root.glob("run_*/bundle.json")
            if (raw := json.loads(path.read_bytes()))["manifest"]["case_id"]
            == definition["case_id"]
            and raw["manifest"]["subject_version"] == version
        ),
        None,
    )
    if source is None:
        with tempfile.TemporaryDirectory(prefix="calibration-fixture-") as output:
            subprocess.run(
                [
                    "node",
                    "adapters/project13/capture.mjs",
                    "--mode",
                    "scripted",
                    "--split",
                    "calibration",
                    "--case-id",
                    definition["case_id"],
                    "--version",
                    version,
                    "--output",
                    output,
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            source = json.loads(next(Path(output).glob("run_*/bundle.json")).read_bytes())
    value = ledger(config["approval"])
    reservation = value.reserve(
        attempt_key=investigation + ":0",
        kind="subject",
        investigation_id=investigation,
        metadata={"stage": stage, "turn": 0},
    )
    value.settle(reservation, {"input_tokens": 1, "output_tokens": 1}, "req_synthetic_test")
    source["manifest"].update(run_id="synthetic_" + uuid4().hex, mode="live")
    source["manifest"]["settings"]["model"] = "claude-sonnet-5-5"
    source["manifest"]["adapter_digest"] = hashlib.sha256(
        "".join(
            hashlib.sha256((Path("adapters/project13") / p).read_bytes()).hexdigest()
            for p in [
                "capture.mjs",
                "subject.mjs",
                "observe.mjs",
                "mutate.mjs",
                "live-model.mjs",
                "provider.mjs",
            ]
        ).encode()
    ).hexdigest()
    source["manifest"]["usage"].update(
        state="known",
        input_tokens=1,
        output_tokens=1,
        cost_nano_usd=12000,
        price_id=config["approval"]["config"]["price_id"],
    )
    return source


def synthetic_judge(request):
    value = ledger(request["approval"])
    reserved = value.reserve(
        attempt_key=request["attemptKey"],
        kind="judge",
        investigation_id=None,
        metadata={"stage": request["stage"]},
    )
    value.settle(reserved, {"input_tokens": 1, "output_tokens": 1}, "req_synthetic_judge")
    payload = json.loads(request["body"]["messages"][0]["content"])
    bad = any(
        text in (payload["explanation"] + " " + payload["next_step"])
        for text in [
            "confirmed its network fee",
            "authoritative approval",
            "without human review",
            "without reviewer",
            "hide the difference",
        ]
    )
    source_id = payload["evidence"]["snapshot"]["sources"][0]["id"]
    body = judge_reply(
        usage={"input_tokens": 1, "output_tokens": 1},
        content=[
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "support": "no" if bad else "yes",
                        "usefulness": "no" if bad else "yes",
                        "evidence_ids": [source_id],
                        "reason": "Synthetic test verdict only.",
                    }
                ),
            }
        ],
    )
    now = datetime.now(UTC).isoformat()
    return {
        "ok": True,
        "value": {
            "receipts": [
                {
                    "reservation_id": reserved,
                    "request": request["body"],
                    "response": body,
                    "request_id": "req_synthetic_judge",
                    "error": None,
                    "started_at": now,
                    "ended_at": now,
                }
            ]
        },
    }


def labels_file(packet, *, refuse=False):
    directory = Path(packet["directory"])
    rows = json.loads((directory / "labels-template.json").read_bytes())
    visible = {v["item_id"]: v for v in json.loads((directory / "items.json").read_bytes())}
    for row in rows:
        text = visible[row["item_id"]]["explanation"] + " " + visible[row["item_id"]]["next_step"]
        bad = refuse or any(
            t in text
            for t in [
                "confirmed its network fee",
                "authoritative approval",
                "without human review",
                "without reviewer",
                "hide the difference",
            ]
        )
        row.update(
            support="no" if bad else "yes",
            usefulness="no" if bad else "yes",
            note="Synthetic concern." if bad else "",
            reviewer="synthetic-test-reviewer",
            labelled_at="2026-10-28T00:00:00Z",
        )
    path = directory / "synthetic-test-labels.json"
    path.write_text(json.dumps(rows))
    return path


def make_study(repo, root, config=None, capture=None):
    from agent_release_gates.live.study import LiveStudy

    config = config or study_config(root)
    return LiveStudy(
        repo,
        root / "artifacts",
        config,
        capture_runner=capture or (lambda request: synthetic_capture(config, request)),
        judge_transport=synthetic_judge,
    )


def calibrated(study):
    packet = study.capture_calibration()
    study.import_calibration_labels(packet["packet_id"], labels_file(packet))
    study.judge_calibration()
    return study.freeze()
