import json
from pathlib import Path

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
    assert all(
        row["provenance"] == "assistant"
        for row in json.loads((Path(heldout["directory"]) / "labels-template.json").read_bytes())
    )
    result = restarted.qualify_holdout(heldout["packet_id"], assistant_labels(heldout))
    assert result["qualification"]["status"] == "pass"
    assert result["qualification"]["study_mode"] == "assistant_live"
    release = restarted.capture_release()
    assert release["candidate"]["decision"]["status"] == "accept"
    assert release["candidate"]["inputs"]["review_mode"] == "assistant"
    assert release["exact_control"]["decision"]["status"] == "reject"
    assert release["semantic_control"]["decision"]["status"] == "reject"
    from agent_release_gates.live.hosted import prepare_study_preview

    preview = prepare_study_preview(repo, restarted.root, restarted.id)
    assert preview["payload"]["reference_provenance"] == "assistant"
    assert preview["payload"]["human_validation"] is False
    for version in preview["payload"]["versions"].values():
        for run in version["runs"]:
            if run["parent_run_id"] is None:
                assert run["extra"]["metadata"]["reference_provenance"] == "assistant"
                assert run["extra"]["metadata"]["human_validation"] is False
    state = restarted.state
    default = EvaluationService(repo, restarted.root, restarted._judge("release"))
    refused = default.compare(
        state["evaluations"]["baseline"], state["evaluations"]["candidate"], result["id"]
    )
    assert refused["decision"]["status"] == "inconclusive"
    assert restarted.report()["ledger"]["subject_attempts"] == 20


def test_cli_authorizes_assistant_mode_without_another_model_attempt(repo, database, tmp_path):
    import os
    import subprocess
    import sys

    from sqlalchemy import text

    from agent_release_gates.live.study import LiveStudy
    from tests.study_support import study_config, synthetic_capture, synthetic_judge

    config = study_config(tmp_path)
    study = LiveStudy(
        repo,
        tmp_path / "artifacts/live/study-test",
        config,
        capture_runner=lambda request: synthetic_capture(config, request),
        judge_transport=synthetic_judge,
    )
    packet = study.capture_calibration()
    config_file = tmp_path / "operator.json"
    approval_file = tmp_path / "assistant-mode.json"
    config_file.write_text(json.dumps(config))
    approval_file.write_text(json.dumps(mode_approval(study, packet)))
    with database[0].connect() as connection:
        schema = connection.execute(text("SELECT current_schema()")).scalar_one()
    url = database[0].url.update_query_dict({"options": f"-csearch_path={schema}"})
    result = subprocess.run(
        [
            sys.executable,
            "scripts/live_study.py",
            "--config",
            str(config_file),
            "authorize-assistant-review",
            "--approval",
            str(approval_file),
        ],
        env={
            **os.environ,
            "GATES_DATABASE_URL": url.render_as_string(hide_password=False),
            "ANTHROPIC_API_KEY": "must-not-send",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["review_mode"] == "assistant"
    assert study.state["review_mode"] == "assistant"
    assert study.report()["ledger"]["subject_attempts"] == 4
