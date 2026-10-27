import argparse
import json
from pathlib import Path

from agent_release_gates.demo import run_demo
from agent_release_gates.settings import make_service

parser = argparse.ArgumentParser()
parser.add_argument("--examples", type=Path, default=Path("examples/scripted"))
parser.add_argument("--output", type=Path, default=Path("artifacts/offline-demo.json"))
args = parser.parse_args()
index = json.loads((args.examples / "index.json").read_bytes())
result = run_demo(make_service(index["judge_script"]), args.examples)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(
    json.dumps(
        {
            "mode": result["mode"],
            "human_labels": result["human_labels"],
            "scripted_labels": result["scripted_labels"],
            "qualification": result["qualification"]["status"],
            "decisions": {
                k: {"id": v["id"], "status": v["decision"]["status"]}
                for k, v in result["decisions"].items()
            },
            "output": str(args.output),
        }
    )
)
