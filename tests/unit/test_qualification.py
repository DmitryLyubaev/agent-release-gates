import pytest

from agent_release_gates.evaluation.qualification import StudyFreeze, qualify
from tests.support import qualification_fixture


@pytest.mark.parametrize("wrong,status", [(0, "pass"), (2, "pass"), (3, "fail")])
def test_each_repetition_needs_fourteen_of_sixteen(wrong, status):
    labels, results, manifest = qualification_fixture()
    for result in results:
        if result.repetition == 2 and int(result.item_id.split("_")[1]) in [9, 11, 13][:wrong]:
            object.__setattr__(result, "usefulness", "no")
    assert qualify(labels, results, manifest).status == status


def test_dangerous_false_accept_is_failure_and_denominator_is_negatives():
    labels, results, manifest = qualification_fixture()
    result = next(r for r in results if r.item_id == "item_12" and r.repetition == 1)
    object.__setattr__(result, "support", "yes")
    object.__setattr__(result, "usefulness", "yes")
    actual = qualify(labels, results, manifest)
    assert actual.status == "fail"
    assert actual.metrics[0]["false_accepts"] == 1
    assert actual.metrics[0]["human_unacceptable"] == 8
    assert actual.metrics[0]["false_accept_rate"] == 0.125
    assert actual.metrics[0]["dangerous_false_accepts"] == 1


def test_missing_or_duplicate_or_changed_judge_identity_is_inconclusive():
    labels, results, manifest = qualification_fixture()
    assert qualify(labels, results[:-1], manifest).status == "inconclusive"
    assert qualify(labels, results + [results[0]], manifest).status == "inconclusive"
    object.__setattr__(results[0], "settings_digest", "f" * 64)
    assert qualify(labels, results, manifest).status == "inconclusive"


def test_inadequate_label_coverage_never_vacuously_passes():
    labels, results, manifest = qualification_fixture()
    for label in labels:
        if label.item_id in ["item_10", "item_12", "item_14", "item_16"]:
            object.__setattr__(label, "support", "yes")
            object.__setattr__(label, "usefulness", "yes")
    assert qualify(labels, results, manifest).status == "inconclusive"


def test_scripted_labels_and_results_never_claim_human_live():
    labels, results, manifest = qualification_fixture()
    assert qualify(labels, results, manifest).study_mode == "scripted"


def test_freeze_allows_initial_plus_two_changes_and_refuses_post_holdout_tuning():
    frozen = StudyFreeze()
    frozen.revise("a" * 64)
    frozen.revise("b" * 64)
    frozen.revise("c" * 64)
    with pytest.raises(ValueError, match="REVISION_LIMIT"):
        frozen.revise("d" * 64)
    frozen.begin_holdout("c" * 64)
    with pytest.raises(ValueError, match="FROZEN"):
        frozen.revise("d" * 64)


def test_legacy_freeze_state_conversion_preserves_initial_and_frozen_identity():
    state = StudyFreeze(revisions=["a" * 64, "b" * 64], frozen="b" * 64)
    assert state.initial == "a" * 64
    assert state.revisions == ["b" * 64]
    with pytest.raises(ValueError, match="FROZEN"):
        state.revise("c" * 64)
