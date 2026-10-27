#!/usr/bin/env bash
set -euo pipefail
uv run python scripts/offline_demo.py
for spec in pass:0 exact_reject:1 semantic_reject:1 incomplete:2; do
  name=${spec%:*}
  expected=${spec#*:}
  id=$(uv run python -c 'import json,sys; print(json.load(open("artifacts/offline-demo.json"))["decisions"][sys.argv[1]]["id"])' "$name")
  code=0
  uv run release-gates report --decision-id "$id" >/dev/null || code=$?
  test "$code" = "$expected"
  echo "$name: exit $code"
done
