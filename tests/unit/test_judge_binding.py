from agent_release_gates.evaluation.qualification import qualify
from tests.support import qualification_fixture


def test_judge_cannot_score_different_text_under_the_same_item_id():
    labels, results, manifest = qualification_fixture()
    object.__setattr__(labels[0], "item_digest", "f" * 64)
    assert qualify(labels, results, manifest).status == "inconclusive"
