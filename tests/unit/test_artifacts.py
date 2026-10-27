import pytest

from agent_release_gates.artifacts.store import import_bundle, validate_bundle
from tests.support import bundle, seal


def test_reimport_same_bytes_has_same_receipt(tmp_path):
    first = import_bundle(validate_bundle(bundle()), tmp_path)
    assert import_bundle(validate_bundle(bundle()), tmp_path) == first
    assert len(list(tmp_path.glob("*/bundle.json"))) == 1


def test_same_run_id_different_content_refused(tmp_path):
    import_bundle(validate_bundle(bundle()), tmp_path)
    raw = bundle()
    raw["documents"]["proposal"]["explanation"] = "Different"
    with pytest.raises(ValueError, match="RUN_CONFLICT"):
        import_bundle(validate_bundle(seal(raw)), tmp_path)


def test_hash_mismatch_refused_before_write(tmp_path):
    raw = bundle()
    raw["documents"]["proposal"]["differenceMinor"] = "9"
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        import_bundle(validate_bundle(raw), tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("run_id", ["../outside", "/absolute", "a/b", "a\\b", ""])
def test_run_id_cannot_escape_root(run_id):
    with pytest.raises(ValueError):
        validate_bundle(bundle(run_id))
