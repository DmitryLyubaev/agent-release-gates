import argparse
import json
import re
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Preview saved synthetic scores offline; upload only with exact payload/destination approval"
    )
    commands = parser.add_subparsers(dest="action", required=True)
    preview = commands.add_parser("preview")
    preview.add_argument("--study-id", required=True)
    preview.add_argument("--artifact-root", type=Path)
    preview.add_argument("--output", type=Path, required=True)
    sync = commands.add_parser("sync")
    sync.add_argument("--approval", type=Path, required=True)
    sync.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args()
    try:
        from agent_release_gates.db.repository import Repository
        from agent_release_gates.db.session import migrate, open_database
        from agent_release_gates.langsmith.sync import PostgresSyncRepository
        from agent_release_gates.live.hosted import prepare_study_preview, sync_approved_preview

        engine, factory = open_database()
        migrate(engine)
        repository = Repository(factory)
        if args.action == "preview":
            value = prepare_study_preview(
                repository,
                args.artifact_root or Path("artifacts/live") / args.study_id,
                args.study_id,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as output:
                output.write(json.dumps(value, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        "payload_digest": value["payload_digest"],
                        "inventory": value["inventory"],
                        "file": str(args.output),
                    }
                )
            )
            return 0
        value = sync_approved_preview(
            json.loads(args.payload.read_bytes()),
            json.loads(args.approval.read_bytes()),
            PostgresSyncRepository(repository),
        )
        print(json.dumps(value))
        return 0 if all(v["state"] == "confirmed" for v in value.values()) else 2
    except Exception as error:  # noqa: BLE001 - do not echo provider/SDK exception contents
        code = str(error)
        print(
            json.dumps(
                {
                    "error": code
                    if re.fullmatch(r"[A-Z_]{1,100}", code)
                    else "HOSTED_OPERATION_INCOMPLETE"
                }
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
