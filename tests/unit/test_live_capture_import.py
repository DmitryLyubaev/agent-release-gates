import json
import os
import subprocess
import sys

from agent_release_gates.artifacts.store import validate_bundle
from agent_release_gates.evaluation.report import report_metrics


def test_real_live_adapter_with_stubbed_transport_imports_provider_evidence(tmp_path):
    program = """
import {harness} from './adapters/project13/tests/live-support.mjs';
import {writeFile} from 'node:fs/promises';
const h=await harness();
try {await writeFile(process.argv[1],JSON.stringify(await h.capture()));}finally{await h.close();}
"""
    destination = tmp_path / "live.json"
    result = subprocess.run(
        ["node", "--input-type=module", "-e", program, str(destination)],
        check=False,
        env={**os.environ, "GATES_PYTHON_EXECUTABLE": sys.executable},
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    bundle = validate_bundle(json.loads(destination.read_bytes()))
    assert bundle.manifest.usage.cost_nano_usd == 1_200_000
    assert len(bundle.documents["provider_receipts"]) == 4


def test_fault_control_parent_cost_is_not_new_inference():
    manifest = {
        "family_id": "f1",
        "mode": "fault_control",
        "started_at": "2026-10-28T00:00:00+00:00",
        "ended_at": "2026-10-28T00:00:01+00:00",
        "usage": {"state": "known", "cost_nano_usd": 1200000, "reserved_nano_usd": 0},
    }
    inputs = {
        "candidate": {
            "cases": [
                {"run_id": "derived", "case_id": "r01", "exact": {"checks": {}}, "judges": []}
            ]
        },
        "qualification": {},
    }
    metrics = report_metrics(inputs, {"derived": manifest})
    assert metrics["known_agent_cost_nano_usd"] == 0
