from agent_release_gates.evaluation.judge import ScriptedJudge, judge_saved_item
from tests.unit.test_review import item


def test_malformed_or_provider_error_abstains_without_retry():
    for response in [{"support": "yes"}, RuntimeError("Do not print provider details")]:
        judge = ScriptedJudge({"item_01": response})
        result = judge_saved_item(item(), judge, 1)
        assert not result.accepts
        assert result.state in ["error", "abstained"]
        assert result.reason != "Do not print provider details"


def test_runtime_judge_input_has_no_labels_or_mutation_origin():
    class EvidenceJudge:
        mode = "scripted"
        settings_digest = "b" * 64

        def evaluate(self, payload):
            assert set(payload) == {
                "item_id",
                "evidence",
                "explanation",
                "next_step",
                "rubric_digest",
            }
            return {
                "support": "no",
                "usefulness": "no",
                "evidence_ids": [],
                "reason": "Unsupported claim.",
            }

    result = judge_saved_item(item(), EvidenceJudge(), 2)
    assert result.support == "no"
    assert result.repetition == 2
