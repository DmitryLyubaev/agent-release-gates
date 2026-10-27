from fastapi.testclient import TestClient

from agent_release_gates.api import create_app
from agent_release_gates.evaluation.gate import decide_release
from agent_release_gates.evaluation.judge import ScriptedJudge
from agent_release_gates.service import EvaluationService
from tests.db_support import registered_bundle, seeded_decision


def client(repo, tmp_path):
    return TestClient(create_app(EvaluationService(repo, tmp_path, ScriptedJudge({}))))


def test_validated_import_and_conflicting_id(repo, tmp_path):
    artifact, _ = registered_bundle(repo)
    api = client(repo, tmp_path)
    raw = artifact.model_dump(mode="json")
    first = api.post("/runs/import", json=raw)
    assert first.status_code == 200
    assert api.get("/runs/run_r01").json()["manifest"]["case_id"] == "r01"
    raw["manifest"]["subject_version"] = "changed"
    assert api.post("/runs/import", json=raw).status_code == 409
    assert len(repo.list_runs()) == 1


def test_unknown_and_paid_requests_cannot_create_records(repo, tmp_path):
    api = client(repo, tmp_path)
    assert api.get("/runs/missing").status_code == 404
    assert (
        api.post(
            "/evaluations", json={"run_ids": [], "mode": "live", "api_key": "do-not-use"}
        ).status_code
        == 422
    )
    assert api.post("/runs/import", json={"arbitrary_path": "../../secret"}).status_code == 422
    assert repo.list_runs() == []


def test_existing_decision_readback_uses_immutable_inputs(repo, tmp_path):
    inputs, _ = seeded_decision(repo)
    saved = repo.save_decision(decide_release(inputs), inputs)
    response = client(repo, tmp_path).get("/decisions/" + saved.id)
    assert response.status_code == 200
    assert response.json()["decision"]["status"] == "accept"
    assert (
        response.json()["inputs"]["qualification"]["label_digest"]
        == inputs.qualification.label_digest
    )


def test_missing_artifact_is_not_silently_reconstructed(repo, tmp_path):
    artifact, _ = registered_bundle(repo)
    api = client(repo, tmp_path)
    assert api.get("/runs/" + artifact.manifest.run_id).status_code == 409
