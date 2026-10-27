import json
from pathlib import Path

from agent_release_gates.evaluation.judge import ScriptedJudge
from agent_release_gates.service import EvaluationService
from tests.unit.test_live_judge import live_judge


def test_ambient_keys_never_turn_default_service_into_a_live_caller(
    database, tmp_path, monkeypatch
):
    from agent_release_gates import settings

    monkeypatch.setenv("ANTHROPIC_API_KEY", "unrelated-ambient-test-key")
    monkeypatch.setenv("GATES_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "open_database", lambda: database)
    service = settings.make_service()
    assert isinstance(service.judge, ScriptedJudge)
    raw = json.loads(next(Path("examples/scripted").glob("run_*/bundle.json")).read_bytes())
    service.import_run(raw)
    value = service.evaluate([raw["manifest"]["run_id"]])
    assert all(j["mode"] == "scripted" for j in value["evaluation"]["cases"][0]["judges"])


def test_live_evaluation_persists_real_judge_receipt_and_unknown_usage(repo, tmp_path):
    judge = live_judge(tmp_path, fail=True)
    service = EvaluationService(repo, tmp_path / "runs", judge)
    raw = json.loads(next(Path("examples/scripted").glob("run_*/bundle.json")).read_bytes())
    raw["manifest"].update(run_id="live-service-test", mode="live")
    raw["manifest"]["usage"].update(state="known", cost_nano_usd=1, price_id="test-price")
    service.import_run(raw)
    value = service.evaluate(["live-service-test"])["evaluation"]
    assert not value["usage_complete"]
    assert value["cases"][0]["judges"][0]["receipt_digest"]
