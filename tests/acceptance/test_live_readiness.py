import json
import os
import subprocess
import sys

from tests.study_support import calibrated, labels_file, make_study


def test_prepared_allowance_is_disabled_and_never_reads_keys_or_starts_database(tmp_path):
    file = tmp_path / "proposal.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/live_study.py",
            "--config",
            str(file),
            "prepare",
            "--study-id",
            "p15-test-proposal",
        ],
        env={
            **os.environ,
            "GATES_DATABASE_URL": "postgresql://must-not-connect",
            "ANTHROPIC_API_KEY": "must-not-read-or-send",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    config = json.loads(file.read_bytes())
    assert config["approval"]["approved"] is False
    assert config["approval"]["personal_account_confirmed"] is False
    assert config["approval"]["config"]["cap_nano_usd"] == 10000000000
    assert config["approval"]["allowed_stages"] == ["calibration"]
    assert "must-not-read-or-send" not in file.read_text() + result.stdout + result.stderr


def test_preview_uses_stored_semantic_scores_and_never_constructs_an_sdk_client(
    repo, tmp_path, monkeypatch
):
    import langsmith

    from agent_release_gates.live.hosted import prepare_study_preview

    study = make_study(repo, tmp_path)
    calibrated(study)
    packet = study.capture_holdout()
    study.qualify_holdout(packet["packet_id"], labels_file(packet))
    study.capture_release()

    def forbidden(*args, **kwargs):
        raise AssertionError("NO_CLIENT_DURING_PREVIEW")

    monkeypatch.setattr(langsmith, "Client", forbidden)
    preview = prepare_study_preview(repo, tmp_path / "artifacts", study.id)
    assert set(preview["payload"]["versions"]) == {"baseline", "candidate"}
    for version in preview["payload"]["versions"].values():
        assert len([run for run in version["runs"] if run["parent_run_id"] is None]) == 4
        scores = {feedback["key"] for feedback in version["feedback"]}
        assert "judge_accept_r1" in scores
        assert "nonempty_explanation" not in scores
    assert preview["payload_digest"]
