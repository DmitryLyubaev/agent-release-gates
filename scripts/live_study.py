import argparse
import json
import re
import sys
from pathlib import Path

from agent_release_gates.live.budget import validate_approval


def main():
    parser = argparse.ArgumentParser(
        description="One explicitly approved live-study stage per command"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "action",
        choices=[
            "capture-calibration",
            "import-calibration-labels",
            "judge-calibration",
            "revise-judge",
            "calibration-development",
            "freeze",
            "capture-holdout",
            "qualify-holdout",
            "capture-release",
            "report",
        ],
    )
    parser.add_argument("--packet-id")
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--round", type=int, default=1)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_bytes())
        validate_approval(config["approval"])
        from agent_release_gates.db.repository import Repository
        from agent_release_gates.db.session import migrate, open_database
        from agent_release_gates.live.study import LiveStudy

        engine, factory = open_database()
        migrate(engine)
        root = (
            Path(config["approval"]["config"]["project_root"])
            / "artifacts/live"
            / config["approval"]["config"]["study_id"]
        )
        study = LiveStudy(Repository(factory), root, config)
        name = args.action.replace("-", "_")
        if name in ["import_calibration_labels", "qualify_holdout"]:
            result = getattr(study, name)(args.packet_id, args.labels)
        elif name == "revise_judge":
            result = study.revise_judge(json.loads(args.settings.read_bytes()))
        elif name == "calibration_development":
            result = study.calibration_development(args.round)
        else:
            result = getattr(study, name)()
        print(json.dumps(result))
        return 0
    except Exception as error:  # noqa: BLE001 - operator errors never disclose credentials or raw provider exceptions
        code = str(error)
        print(
            json.dumps(
                {
                    "error": code
                    if re.fullmatch(r"[A-Z_]{1,100}", code)
                    else "INVALID_OR_INCOMPLETE_STUDY_INPUT"
                }
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
