import argparse
import json
import re
import sys
from pathlib import Path

from agent_release_gates.live.budget import prepare_allowance, validate_approval


def main():
    parser = argparse.ArgumentParser(
        description="One explicitly approved live-study stage per command"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "action",
        choices=[
            "prepare",
            "authorize-assistant-review",
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
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--study-id")
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            config = prepare_allowance(Path(__file__).resolve().parents[1], args.study_id or "")
            args.config.parent.mkdir(parents=True, exist_ok=True)
            with args.config.open("x", encoding="utf-8") as output:
                output.write(json.dumps(config, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        "status": "proposal_not_approved",
                        "config_digest": config["approval"]["config_digest"],
                        "file": str(args.config),
                    }
                )
            )
            return 0
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
        if name == "authorize_assistant_review":
            if not args.approval:
                raise ValueError("REVIEW_MODE_APPROVAL_REQUIRED")
            result = study.authorize_assistant_review(json.loads(args.approval.read_bytes()))
        elif name in ["import_calibration_labels", "qualify_holdout"]:
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
