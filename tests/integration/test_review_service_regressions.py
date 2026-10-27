import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_release_gates.api import create_app
from agent_release_gates.demo import run_demo
from agent_release_gates.evaluation.judge import ScriptedJudge
from agent_release_gates.service import EvaluationService
from tests.support import seal


def setup_demo(repo, tmp_path):
    root = Path("examples/scripted")
    index = json.loads((root / "index.json").read_bytes())
    responses = {
        **index["judge_script"],
        **{
            "changed_" + run_id: index["judge_script"][run_id]
            for run_id in index["versions"]["candidate"]
        },
    }
    service = EvaluationService(repo, tmp_path, ScriptedJudge(responses))
    result = run_demo(service, root)
    saved = repo.get_decision(result["decisions"]["pass"]["id"])
    return service, index, saved


def test_missing_baseline_artifact_after_evaluation_is_inconclusive(repo, tmp_path):
    service, index, saved = setup_demo(repo, tmp_path)
    run = repo.get_run(index["versions"]["baseline"][0])
    (tmp_path / run.storage_key).unlink()
    result = service.compare(saved.baseline_id, saved.candidate_id, saved.qualification_id)
    assert result["decision"]["status"] == "inconclusive"


@pytest.mark.parametrize("field", ["source", "tools", "model"])
def test_prompt_only_comparison_refuses_other_target_changes(repo, tmp_path, field):
    service, index, saved = setup_demo(repo, tmp_path)
    run_ids = []
    for old in index["versions"]["candidate"]:
        raw = service.read_run(old).model_dump(mode="json")
        raw["manifest"]["run_id"] = "changed_" + old
        raw["manifest"]["subject_version"] = "changed_candidate"
        if field == "source":
            raw["manifest"].update(subject_commit="f" * 40, source_digest="e" * 64)
        else:
            raw["manifest"]["settings"][field] = "different-target"
        service.import_run(raw)
        run_ids.append(raw["manifest"]["run_id"])
    evaluation = service.evaluate(run_ids)
    result = service.compare(saved.baseline_id, evaluation["id"], saved.qualification_id)
    assert result["decision"]["status"] == "inconclusive"


def test_malformed_document_cannot_be_persisted_through_api(repo, tmp_path):
    from tests.support import bundle

    service = EvaluationService(repo, tmp_path, ScriptedJudge({}))
    raw = bundle()
    raw["manifest"]["dataset_digest"] = service.dataset_record.id
    raw["documents"]["proposal"] = "malformed proposal"
    response = TestClient(create_app(service)).post("/runs/import", json=seal(raw))
    assert response.status_code == 422
    assert repo.list_runs() == []
