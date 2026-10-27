import pytest

from agent_release_gates.evaluation.judge import ScriptedJudge
from agent_release_gates.service import EvaluationService
from tests.db_support import registered_bundle


def test_one_version_cannot_mix_target_settings_between_cases(repo, tmp_path):
    service = EvaluationService(repo, tmp_path, ScriptedJudge({}))
    first, _ = registered_bundle(repo, "run_first", "r01")
    second, _ = registered_bundle(repo, "run_second", "r02")
    raw = second.model_dump(mode="json")
    raw["manifest"]["settings"]["model"] = "different-model"
    service.import_run(first.model_dump(mode="json"))
    # This is a distinct capture, not conflicting content under an existing ID.
    raw["manifest"]["run_id"] = "run_different"
    service.import_run(raw)
    with pytest.raises(ValueError, match="TARGET_IDENTITIES"):
        service.evaluate(["run_first", "run_different"])
