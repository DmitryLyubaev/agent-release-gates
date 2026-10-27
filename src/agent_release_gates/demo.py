import json
from pathlib import Path
from uuid import uuid4


def run_demo(service, examples: Path) -> dict:
    index = json.loads((examples / "index.json").read_bytes())
    if index["mode"] != "scripted":
        raise ValueError("SCRIPTED_DEMO_ONLY")
    for path in sorted(examples.glob("*/bundle.json")):
        raw = json.loads(path.read_bytes())
        if raw["manifest"]["usage"]["state"] != "not_incurred":
            raise ValueError("SCRIPTED_DEMO_ONLY")
        service.import_run(raw)
    study = "offline_" + uuid4().hex
    qualification = None
    for split in ["calibration", "heldout"]:
        packet = service.review_packet(index["review"][split], split)
        rows = json.loads((Path(packet["directory"]) / "labels-template.json").read_bytes())
        for row in rows:
            response = index["judge_script"][row["item_id"]]
            row.update(
                support=response["support"],
                usefulness=response["usefulness"],
                note="Authored scripted label, not a human review.",
                reviewer="scripted-fixture",
                labelled_at=index["generated_at"],
                provenance="scripted",
            )
        labels = service.import_labels(packet["packet_id"], rows)
        result = service.qualify(packet["packet_id"], labels["id"], study)
        if split == "heldout":
            qualification = result
    evaluations = {key: service.evaluate(ids) for key, ids in index["versions"].items()}
    incomplete = service.evaluate(index["versions"]["candidate"][:3])
    decisions = {
        key: service.compare(evaluations["baseline"]["id"], evaluation_id, qualification["id"])
        for key, evaluation_id in [
            ("pass", evaluations["candidate"]["id"]),
            ("exact_reject", evaluations["exact_fault"]["id"]),
            ("semantic_reject", evaluations["semantic_fault"]["id"]),
            ("incomplete", incomplete["id"]),
        ]
    }
    expected = {
        "pass": "accept",
        "exact_reject": "reject",
        "semantic_reject": "reject",
        "incomplete": "inconclusive",
    }
    if {k: v["decision"]["status"] for k, v in decisions.items()} != expected:
        raise ValueError("UNEXPECTED_DEMO_OUTCOME")
    return {
        "mode": "scripted_offline",
        "human_labels": 0,
        "scripted_labels": 24,
        "paid_calls": 0,
        "model_spend": "not_incurred",
        "qualification": qualification["qualification"],
        "decisions": decisions,
    }
