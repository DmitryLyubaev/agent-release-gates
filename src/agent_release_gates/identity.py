"""Conservative implementation identity for frozen evaluations and live attempts."""

import hashlib
from pathlib import Path

from agent_release_gates.artifacts.store import digest


def implementation_digest():
    root = Path(__file__).resolve().parent
    files = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*.py"))
    }
    files["uv.lock"] = hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest()
    return digest(files)
