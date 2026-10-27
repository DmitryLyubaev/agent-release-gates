import json
from pathlib import Path

from agent_release_gates.demo import run_demo
from agent_release_gates.evaluation.judge import ScriptedJudge
from agent_release_gates.service import EvaluationService


def test_actual_scripted_demo_accepts_rejects_and_abstains(repo, tmp_path):
    root = Path("examples/scripted")
    index = json.loads((root / "index.json").read_bytes())
    service = EvaluationService(repo, tmp_path / "artifacts", ScriptedJudge(index["judge_script"]))
    result = run_demo(service, root)
    assert result["decisions"]["pass"]["decision"]["status"] == "accept"
    assert result["decisions"]["exact_reject"]["decision"]["status"] == "reject"
    assert result["decisions"]["semantic_reject"]["decision"]["status"] == "reject"
    assert result["decisions"]["incomplete"]["decision"]["status"] == "inconclusive"
    assert result["qualification"]["study_mode"] == "scripted"
    assert result["qualification"]["status"] == "pass"
    assert result["human_labels"] == 0
    assert result["scripted_labels"] == 24


def test_live_artifacts_cannot_use_scripted_qualification():
    from agent_release_gates.contracts.decisions import GateInput
    from agent_release_gates.evaluation.gate import decide_release
    from tests.support import gate_input

    raw = gate_input()
    raw["candidate"]["mode"] = "live"
    assert decide_release(GateInput.model_validate(raw)).status == "inconclusive"
