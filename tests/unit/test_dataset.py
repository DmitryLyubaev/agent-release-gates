import json
from pathlib import Path

import pytest

from agent_release_gates.artifacts.manifest import load_dataset


def test_dataset_has_family_isolated_8_and_16_review_items():
    manifest = load_dataset("datasets")
    assert {
        s: sum(c.split == s for c in manifest.cases) for s in ["calibration", "heldout", "release"]
    } == {"calibration": 4, "heldout": 8, "release": 4}
    assert {
        s: sum(i.split == s for i in manifest.review_items) for s in ["calibration", "heldout"]
    } == {"calibration": 8, "heldout": 16}
    assert sum(i.dangerous for i in manifest.review_items if i.split == "heldout") >= 4


def test_family_cannot_span_splits(tmp_path):
    raw = json.loads(Path("datasets/manifest.json").read_text(encoding="utf-8"))
    raw["cases"][4]["family_id"] = raw["cases"][0]["family_id"]
    (tmp_path / "manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="FAMILY_SPLIT"):
        load_dataset(tmp_path)
