import json
import re
import sys
from pathlib import Path

from .budget import BudgetLedger


def main():
    try:
        raw = sys.stdin.buffer.read(131073)
        if len(raw) > 131072:
            raise ValueError("INPUT_LIMIT")
        request = json.loads(raw)
        ledger = BudgetLedger(Path(request["path"]), request["approval"])
        operation = request["operation"]
        if operation not in ["reserve", "settle", "summary"]:
            raise ValueError("UNKNOWN_OPERATION")
        value = getattr(ledger, operation)(**request.get("arguments", {}))
        print(json.dumps({"ok": True, "value": value}))
        return 0
    except Exception as error:  # noqa: BLE001 - no external error/credential text crosses stdout
        code = str(error)
        code = code if re.fullmatch(r"[A-Z_]{1,80}", code) else "INVALID_BUDGET_OPERATION"
        print(json.dumps({"ok": False, "error": code}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
