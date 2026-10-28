import json
import subprocess
import sys


def test_node_boundary_preserves_unicode_under_a_non_utf8_windows_locale():
    program = """
import json,locale
locale.getencoding=lambda:'cp1252'
from agent_release_gates.live.study import node_json
print(json.dumps(node_json("process.stdout.write(JSON.stringify({text:String.fromCodePoint(99,97,102,233,32,8364,32,128512)}))",{})))
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8=0", "-c", program],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert json.loads(result.stdout)["text"] == "café € 😀"
