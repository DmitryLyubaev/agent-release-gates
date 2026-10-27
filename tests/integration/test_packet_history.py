import json
from pathlib import Path

from agent_release_gates.evaluation.judge import ScriptedJudge
from agent_release_gates.service import EvaluationService


def test_new_capture_packet_cannot_overwrite_a_previous_frozen_view(repo, tmp_path):
    root = Path("examples/scripted")
    index = json.loads((root / "index.json").read_bytes())
    service = EvaluationService(repo, tmp_path, ScriptedJudge({}))
    first_ids = index["review"]["calibration"]
    for run_id in first_ids:
        service.import_run(json.loads((root / run_id / "bundle.json").read_bytes()))
    first = service.review_packet(first_ids, "calibration")
    frozen = (Path(first["directory"]) / "items.json").read_bytes()
    second_ids = []
    for run_id in first_ids:
        raw = json.loads((root / run_id / "bundle.json").read_bytes())
        raw["manifest"]["run_id"] = "copy_" + run_id
        second_ids.append(raw["manifest"]["run_id"])
        service.import_run(raw)
    second = service.review_packet(second_ids, "calibration")
    assert first["directory"] != second["directory"]
    assert (Path(first["directory"]) / "items.json").read_bytes() == frozen
