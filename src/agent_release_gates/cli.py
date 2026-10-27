import argparse
import json
import sys
from pathlib import Path

from agent_release_gates.settings import make_service

EXITS = {"accept": 0, "reject": 1, "inconclusive": 2}


def main():
    parser = argparse.ArgumentParser(description="Evaluate saved synthetic agent runs")
    parser.add_argument("--judge-script", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("import-run")
    command.add_argument("file", type=Path)
    for name in ["evaluate", "review-packet"]:
        command = commands.add_parser(name)
        command.add_argument("--run-id", action="append", required=True)
        if name == "review-packet":
            command.add_argument("--split", choices=["calibration", "heldout"], required=True)
            command.add_argument("--output", type=Path)
    command = commands.add_parser("import-labels")
    command.add_argument("--packet-id", required=True)
    command.add_argument("file", type=Path)
    command = commands.add_parser("qualify")
    command.add_argument("--packet-id", required=True)
    command.add_argument("--labels-id", required=True)
    command.add_argument("--study-id", required=True)
    command = commands.add_parser("compare")
    command.add_argument("--baseline-id")
    command.add_argument("--candidate-id", required=True)
    command.add_argument("--qualification-id")
    command = commands.add_parser("report")
    command.add_argument("--decision-id", required=True)
    args = parser.parse_args()
    try:
        responses = json.loads(args.judge_script.read_bytes()) if args.judge_script else {}
        service = make_service(responses)
        match args.command:
            case "import-run":
                value = service.import_run(json.loads(args.file.read_bytes()))
            case "evaluate":
                value = service.evaluate(args.run_id)
            case "review-packet":
                value = service.review_packet(args.run_id, args.split, args.output)
            case "import-labels":
                value = service.import_labels(args.packet_id, json.loads(args.file.read_bytes()))
            case "qualify":
                value = service.qualify(args.packet_id, args.labels_id, args.study_id)
            case "compare":
                value = service.compare(args.baseline_id, args.candidate_id, args.qualification_id)
            case "report":
                value = service.decision(args.decision_id)
        print(json.dumps(value, ensure_ascii=False))
        return EXITS[value["decision"]["status"]] if "decision" in value else 0
    except (ValueError, KeyError, OSError):
        print(json.dumps({"error": "INVALID_OR_INCOMPLETE_INPUT"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
