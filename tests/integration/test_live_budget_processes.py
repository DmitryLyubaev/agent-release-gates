import json
import os
import subprocess
import sys

from tests.live_support import allowance, ledger


def test_two_workers_share_one_allowance_and_crash_cannot_replenish_it(tmp_path):
    approval = allowance(tmp_path, cap_nano_usd=3_000_000_000)
    ledger(approval)
    workers = []
    for key in ["attempt-a", "attempt-b"]:
        worker = subprocess.Popen(
            [sys.executable, "-m", "agent_release_gates.live.budget_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONPATH": "src"},
        )
        payload = {
            "operation": "reserve",
            "path": approval["config"]["ledger_path"],
            "approval": approval,
            "arguments": {
                "attempt_key": key,
                "kind": "subject",
                "investigation_id": key,
                "metadata": {"stage": "calibration", "turn": 0},
            },
        }
        worker.stdin.write(json.dumps(payload))
        worker.stdin.close()
        worker.stdin = None
        workers.append(worker)
    replies = [json.loads(worker.communicate(timeout=30)[0]) for worker in workers]
    assert sum(reply["ok"] for reply in replies) == 1
    summary = ledger(approval).summary()
    assert summary["unsettled_calls"] == 1
    assert summary["committed_nano_usd"] == 2_040_960_000
