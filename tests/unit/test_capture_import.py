import json
import subprocess
from pathlib import Path

from agent_release_gates.artifacts.store import validate_bundle


def test_actual_adapter_bundles_import_with_all_hashes(tmp_path):
    subprocess.run(
        ["node", "adapters/project13/capture.mjs", "--output", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    bundles = [validate_bundle(json.loads(p.read_bytes())) for p in tmp_path.glob("*/bundle.json")]
    assert len(bundles) == 4
    assert all(b.documents["capture"]["complete"] for b in bundles)
    assert all(b.manifest.usage.state == "not_incurred" for b in bundles)
    assert Path(".local/subject/.git").exists()
