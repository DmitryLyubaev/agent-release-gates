import json
from pathlib import Path

import pytest

from tests.study_support import calibrated, labels_file, make_study, study_config, synthetic_capture


def test_calibration_packet_is_blind_complete_and_restart_never_recaptures(repo, tmp_path):
    study = make_study(repo, tmp_path)
    packet = study.capture_calibration()
    rows = json.loads(Path(packet["directory"], "items.json").read_bytes())
    assert len(rows) == 8
    assert all(
        set(row) == {"item_id", "item_digest", "evidence", "explanation", "next_step"}
        for row in rows
    )
    assert not any("origin" in row or "judge" in row for row in rows)
    assert make_study(repo, tmp_path).capture_calibration() == packet
    assert study.report()["ledger"]["subject_attempts"] == 4
    with pytest.raises(ValueError, match="STAGE"):
        study.capture_holdout()
    with pytest.raises(ValueError, match="STAGE"):
        study.judge_calibration()


def test_missing_explanation_is_a_failed_capture_not_an_authored_review_item(repo, tmp_path):
    config = study_config(tmp_path)

    def no_explanation(request):
        raw = synthetic_capture(config, request)
        raw["documents"]["proposal"] = None
        from tests.support import seal

        return seal(raw)

    study = make_study(repo, tmp_path, config, capture=no_explanation)
    with pytest.raises(ValueError, match="CAPTURE"):
        study.capture_calibration()
    assert study.report()["status"] == "incomplete"
    with pytest.raises(ValueError, match="STAGE"):
        study.capture_calibration()


def test_labels_freeze_then_heldout_preserves_first_failure_and_forbids_tuning(repo, tmp_path):
    study = make_study(repo, tmp_path)
    calibrated(study)
    with pytest.raises(ValueError, match="FROZEN"):
        study.revise_judge({"instructions": "A different judge prompt"})
    heldout = study.capture_holdout()
    assert len(json.loads(Path(heldout["directory"], "items.json").read_bytes())) == 16
    result = study.qualify_holdout(heldout["packet_id"], labels_file(heldout, refuse=True))
    assert result["qualification"]["status"] == "inconclusive"
    assert (
        make_study(repo, tmp_path).qualify_holdout(
            heldout["packet_id"], labels_file(heldout, refuse=True)
        )
        == result
    )
    with pytest.raises(ValueError, match="QUALIFICATION"):
        study.capture_release()


def test_two_judge_revisions_are_subsequent_to_initial_identity(repo, tmp_path):
    study = make_study(repo, tmp_path)
    packet = study.capture_calibration()
    study.import_calibration_labels(packet["packet_id"], labels_file(packet))
    study.judge_calibration()
    study.revise_judge({"instructions": "Use evidence IDs and preserve review. Version two."})
    study.judge_calibration()
    study.revise_judge({"instructions": "Use evidence IDs and preserve review. Version three."})
    study.judge_calibration()
    with pytest.raises(ValueError, match="REVISION_LIMIT"):
        study.revise_judge({"instructions": "Version four."})
    assert study.report()["ledger"]["judge_attempts"] == 24


def test_changed_output_root_cannot_reopen_a_study_allowance(repo, tmp_path):
    from agent_release_gates.live.study import LiveStudy

    config = study_config(tmp_path)
    make_study(repo, tmp_path, config).capture_calibration()
    with pytest.raises(ValueError, match="CONFIG"):
        LiveStudy(repo, tmp_path / "another-output", config)


@pytest.mark.parametrize("field", ["adapter_digest", "model"])
def test_post_freeze_capture_identity_mismatch_preserves_failure_and_never_replaces_it(
    repo, tmp_path, field
):
    config = study_config(tmp_path)

    def changed(request):
        raw = synthetic_capture(config, request)
        if request["stage"] == "heldout":
            if field == "adapter_digest":
                raw["manifest"][field] = "0" * 64
            else:
                raw["manifest"]["settings"][field] = "wrong-model"
        return raw

    study = make_study(repo, tmp_path, config, capture=changed)
    calibrated(study)
    with pytest.raises(ValueError, match="CAPTURE_IDENTITY"):
        study.capture_holdout()
    assert study.report()["status"] == "incomplete"
    attempts = study.report()["ledger"]["subject_attempts"]
    with pytest.raises(ValueError, match="STAGE"):
        study.capture_holdout()
    assert study.report()["ledger"]["subject_attempts"] == attempts


def test_calibration_development_stays_within_eight_extra_runs_and_keeps_original_packet(
    repo, tmp_path
):
    study = make_study(repo, tmp_path)
    packet = study.capture_calibration()
    study.import_calibration_labels(packet["packet_id"], labels_file(packet))
    first = study.calibration_development(1)
    assert study.calibration_development(1) == first
    study.calibration_development(2)
    with pytest.raises(ValueError, match="DEVELOPMENT_LIMIT"):
        study.calibration_development(3)
    assert study.report()["ledger"]["subject_attempts"] == 12
    assert study.report()["results"]["capture_calibration"] == packet


def test_stale_state_revision_cannot_claim_another_stage(repo, tmp_path):
    study = make_study(repo, tmp_path)
    initial = study.state
    repo.live_study(
        study.id,
        study.config_digest,
        {**initial, "revision": initial["revision"] + 1, "pending": "capture_calibration"},
        initial["revision"],
    )
    with pytest.raises(ValueError, match="CONCURRENT"):
        repo.live_study(
            study.id,
            study.config_digest,
            {**initial, "pending": "different-stage"},
            initial["revision"],
        )
    assert study.state["pending"] == "capture_calibration"


def test_parser_only_revision_invalidates_frozen_study_before_holdout(repo, tmp_path, monkeypatch):
    from agent_release_gates.live import judge
    from agent_release_gates.service import EvaluationService

    study = make_study(repo, tmp_path)
    calibrated(study)
    parser = Path(judge.__file__).resolve()
    original = Path.read_bytes

    def changed(path):
        raw = original(path)
        return raw + b"\n# changed parser\n" if path.resolve() == parser else raw

    monkeypatch.setattr(Path, "read_bytes", changed)
    assert (
        EvaluationService(repo, study.root, study.service.judge).evaluator_digest
        != study.service.evaluator_digest
    )
    with pytest.raises(ValueError, match="FROZEN_IDENTITY"):
        study.capture_holdout()
    assert study.report()["ledger"]["subject_attempts"] == 4


def test_new_study_id_cannot_make_exposed_holdout_families_fresh(repo, tmp_path):
    from agent_release_gates.artifacts.store import digest

    first = make_study(repo, tmp_path / "first")
    calibrated(first)
    packet = first.capture_holdout()
    second_config = study_config(tmp_path / "second")
    second_config["approval"]["config"]["study_id"] = "different-study"
    second_config["approval"]["config_digest"] = digest(second_config["approval"]["config"])
    second = make_study(repo, tmp_path / "second", second_config)
    with pytest.raises(ValueError, match="HELDOUT_FAMILIES_PREVIOUSLY_USED"):
        second.capture_calibration()
    assert second.report()["ledger"]["subject_attempts"] == 0
    assert first.capture_holdout() == packet


def test_holdout_claim_rechecks_other_study_exposure_after_parallel_calibrations(repo, tmp_path):
    from agent_release_gates.artifacts.store import digest

    first = make_study(repo, tmp_path / "first")
    second_config = study_config(tmp_path / "second")
    second_config["approval"]["config"]["study_id"] = "different-study"
    second_config["approval"]["config_digest"] = digest(second_config["approval"]["config"])
    second = make_study(repo, tmp_path / "second", second_config)
    calibrated(first)
    calibrated(second)
    first.capture_holdout()
    with pytest.raises(ValueError, match="HELDOUT_FAMILIES_PREVIOUSLY_USED"):
        second.capture_holdout()
    assert second.report()["ledger"]["subject_attempts"] == 4


@pytest.mark.parametrize("legacy", [False, True])
def test_interrupted_exposure_cannot_be_hidden_by_family_rename(repo, legacy):
    dataset = repo.register_dataset(Path("datasets/manifest.json").read_bytes())
    case = next(case for case in dataset.payload["cases"] if case["split"] == "heldout")
    family = {key: case[key] for key in ["family_id", "fixture_digest"]}
    first = {"revision": 0, "pending": None, "results": {}, "captures": {}}
    if legacy:
        first.update(pending="capture_heldout", frozen={"dataset": dataset.id})
    repo.live_study("first", "a" * 64, first)
    if not legacy:
        repo.live_study(
            "first",
            "a" * 64,
            {**first, "revision": 1, "pending": "capture_heldout"},
            0,
            claim_families=[family],
            heldout_families=[family],
        )
    repo.live_study("second", "b" * 64, {"revision": 0, "used_families": []})
    renamed = {**family, "family_id": "renamed-heldout-family"}
    with pytest.raises(ValueError, match="HELDOUT_FAMILIES_PREVIOUSLY_USED"):
        repo.live_study(
            "second",
            "b" * 64,
            {"revision": 1, "pending": "capture_heldout"},
            0,
            claim_families=[renamed],
            heldout_families=[renamed],
        )
