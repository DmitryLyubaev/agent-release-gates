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


def test_judge_refusal_preserves_later_exact_violation_without_more_paid_calls(repo, tmp_path):
    from agent_release_gates.artifacts.store import canonical
    from agent_release_gates.live.study import node_json

    judge = live_judge(tmp_path, fail=True)
    service = EvaluationService(repo, tmp_path / "runs", judge)
    raws = sorted(
        (
            json.loads(path.read_bytes())
            for path in Path("examples/scripted").glob("run_*/bundle.json")
        ),
        key=lambda raw: raw["manifest"]["case_id"],
    )
    raws = [
        raw
        for raw in raws
        if raw["manifest"]["subject_version"] == "candidate"
        and raw["manifest"]["mode"] == "scripted"
        and raw["manifest"]["split"] == "release"
    ]
    assert len(raws) == 4
    # Derive one actual money violation, placed after the first unresolved judge call.
    raws[-1] = node_json(
        """import {mutateBundle} from './adapters/project13/mutate.mjs';
let t='';for await(const p of process.stdin)t+=p;
process.stdout.write(JSON.stringify(mutateBundle(JSON.parse(t),'change_money')));""",
        raws[-1],
    )
    # Version consistency is irrelevant to this independent exact-check regression.
    for raw in raws:
        raw["manifest"]["mode"] = "scripted"
        raw["manifest"]["subject_version"] = "candidate"
        raw["manifest"]["fault_recipe"] = None
        raw["manifest"]["settings"].pop("control_recipe", None)
        service.import_run(json.loads(canonical(raw)))
    result = service.evaluate([raw["manifest"]["run_id"] for raw in raws])["evaluation"]
    assert len(result["cases"]) == 4
    assert not result["usage_complete"]
    assert "fail" in result["cases"][-1]["exact"]["checks"].values()
    assert all(not case["judges"] for case in result["cases"][1:])
    assert len(judge.ledger.summary()["calls"]) == 1
