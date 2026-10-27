import json
import os
import subprocess
import sys

from tests.study_support import calibrated, labels_file, make_study, study_config


def test_synthetic_boundaries_exercise_human_live_gate_without_real_calls(repo, tmp_path):
    study = make_study(repo, tmp_path)
    calibrated(study)
    packet = study.capture_holdout()
    qualification = study.qualify_holdout(packet["packet_id"], labels_file(packet))
    assert qualification["qualification"]["status"] == "pass"
    assert qualification["qualification"]["study_mode"] == "human_live"
    release = study.capture_release()
    assert release["candidate"]["decision"]["status"] == "accept"
    assert release["exact_control"]["decision"]["status"] == "reject"
    assert release["semantic_control"]["decision"]["status"] == "reject"
    report = study.report()
    assert report["ledger"]["subject_attempts"] == 20
    assert report["ledger"]["judge_attempts"] == 72
    assert make_study(repo, tmp_path).capture_release() == release


def test_operator_cli_refuses_out_of_order_stage_before_key_or_provider_access(tmp_path):
    config = study_config(tmp_path)
    config["approval"]["approved"] = False
    file = tmp_path / "config.json"
    file.write_text(json.dumps(config))
    result = subprocess.run(
        [sys.executable, "scripts/live_study.py", "--config", str(file), "capture-holdout"],
        env={**os.environ, "ANTHROPIC_API_KEY": "ambient-test-key-never-send"},
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 2
    assert "APPROVAL" in result.stdout
    assert "ambient-test-key-never-send" not in result.stdout + result.stderr
