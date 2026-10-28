import json

import pytest

from tests.study_support import labels_file, make_study


def mode_approval(study, packet):
    return {
        "approved": True,
        "approved_by": "test-only-owner",
        "approved_at": "2026-10-28T00:00:00Z",
        "study_id": study.id,
        "allowance_config_digest": study.approval["config_digest"],
        "packet_id": packet["packet_id"],
        "review_mode": "assistant",
        "human_validation": False,
        "budget_reset": False,
    }


def assistant_labels(packet):
    path = labels_file(packet)
    rows = json.loads(path.read_bytes())
    for row in rows:
        row["provenance"] = "assistant"
        row["reviewer"] = "synthetic-assistant-test"
    path.write_text(json.dumps(rows))
    return path


def test_assistant_mode_requires_explicit_grant_and_preserves_default_human_requirement(
    repo, tmp_path
):
    study = make_study(repo, tmp_path)
    packet = study.capture_calibration()
    labels = assistant_labels(packet)
    with pytest.raises(ValueError, match="HUMAN"):
        study.import_calibration_labels(packet["packet_id"], labels)
    original_policy = study.service.policy_digest
    approval = mode_approval(study, packet)
    result = study.authorize_assistant_review(approval)
    assert result == study.authorize_assistant_review(approval)
    assert study.state["review_mode"] == "assistant"
    assert study.service.policy_digest != original_policy
    assert study.report()["ledger"]["subject_attempts"] == 4
    changed = {**approval, "approved_at": "2026-10-28T00:01:00Z"}
    with pytest.raises(ValueError, match="MODE|APPROVAL"):
        study.authorize_assistant_review(changed)


@pytest.mark.parametrize(
    "field", ["study_id", "allowance_config_digest", "packet_id", "human_validation"]
)
def test_assistant_mode_refuses_mismatched_grants(repo, tmp_path, field):
    study = make_study(repo, tmp_path)
    # No capture needed: grant shape/identity must be rejected before any dispatch.
    approval = mode_approval(study, {"packet_id": "a" * 64})
    approval[field] = True if field == "human_validation" else "wrong"
    with pytest.raises(ValueError, match="APPROVAL|MODE"):
        study.authorize_assistant_review(approval)
    assert study.report()["ledger"]["subject_attempts"] == 0


def test_human_labels_prevent_later_mode_switch(repo, tmp_path):
    study = make_study(repo, tmp_path)
    packet = study.capture_calibration()
    study.import_calibration_labels(packet["packet_id"], labels_file(packet))
    with pytest.raises(ValueError, match="MODE|STAGE"):
        study.authorize_assistant_review(mode_approval(study, packet))


def test_synthetic_assistant_study_is_persistent_and_never_claims_human_qualification(
    repo, tmp_path
):
    from agent_release_gates.service import EvaluationService

    study = make_study(repo, tmp_path)
    packet = study.capture_calibration()
    approval = mode_approval(study, packet)
    study.authorize_assistant_review(approval)
    imported = study.import_calibration_labels(packet["packet_id"], assistant_labels(packet))
    assert all(row["provenance"] == "assistant" for row in repo.get_labels(imported["id"]).payload)
    study.judge_calibration()
    study.freeze()
    restarted = make_study(repo, tmp_path)
    assert restarted.state["frozen"]["review_mode"] == "assistant"
    assert restarted.service.review_mode == "assistant"
    with pytest.raises(ValueError, match="MODE|FROZEN|STAGE"):
        restarted.authorize_assistant_review({**approval, "approved_at": "2026-10-28T00:02:00Z"})
    heldout = restarted.capture_holdout()
    result = restarted.qualify_holdout(heldout["packet_id"], assistant_labels(heldout))
    assert result["qualification"]["status"] == "pass"
    assert result["qualification"]["study_mode"] == "assistant_live"
    release = restarted.capture_release()
    assert release["candidate"]["decision"]["status"] == "accept"
    assert release["candidate"]["inputs"]["review_mode"] == "assistant"
    assert release["exact_control"]["decision"]["status"] == "reject"
    assert release["semantic_control"]["decision"]["status"] == "reject"
    state = restarted.state
    default = EvaluationService(repo, restarted.root, restarted._judge("release"))
    refused = default.compare(
        state["evaluations"]["baseline"], state["evaluations"]["candidate"], result["id"]
    )
    assert refused["decision"]["status"] == "inconclusive"
    assert restarted.report()["ledger"]["subject_attempts"] == 20
