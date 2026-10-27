import json
import subprocess
from pathlib import Path

from agent_release_gates.artifacts.manifest import load_dataset
from agent_release_gates.artifacts.store import validate_bundle
from agent_release_gates.contracts.datasets import ExpectedCase
from agent_release_gates.evaluation.exact import check_exact


def test_actual_workflow_release_cases_satisfy_exact_contracts(tmp_path):
    subprocess.run(
        ["node", "adapters/project13/capture.mjs", "--output", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    catalog = load_dataset("datasets")
    for path in tmp_path.glob("*/bundle.json"):
        artifact = validate_bundle(json.loads(path.read_bytes()))
        definition = next(c for c in catalog.cases if c.case_id == artifact.manifest.case_id)
        gold = ExpectedCase.model_validate_json((Path("datasets") / definition.gold).read_bytes())
        assert check_exact(artifact, gold).passed, check_exact(artifact, gold).checks
