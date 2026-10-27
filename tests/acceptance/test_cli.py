import json
import os
import subprocess

import pytest
from sqlalchemy import text

from agent_release_gates.contracts.decisions import GateInput
from agent_release_gates.evaluation.gate import decide_release
from tests.db_support import seeded_decision


@pytest.mark.parametrize("status,exit_code", [("accept", 0), ("reject", 1), ("inconclusive", 2)])
def test_compiled_cli_process_reads_decision_after_restart(repo, database, status, exit_code):
    inputs, _ = seeded_decision(repo)
    raw = inputs.model_dump(mode="json")
    if status == "reject":
        raw["candidate"]["cases"][0]["exact"]["checks"]["money"] = "fail"
    if status == "inconclusive":
        raw["candidate"]["cases"] = raw["candidate"]["cases"][:3]
    inputs = GateInput.model_validate(raw)
    saved = repo.save_decision(decide_release(inputs), inputs)
    with database[0].connect() as c:
        schema = c.execute(text("select current_schema()")).scalar()
    url = (
        database[0]
        .url.update_query_dict({"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
    environment = {**os.environ, "GATES_DATABASE_URL": url}
    for _ in range(2):
        process = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "agent_release_gates.cli",
                "report",
                "--decision-id",
                saved.id,
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert process.returncode == exit_code, process.stderr
        assert json.loads(process.stdout)["decision"]["status"] == status
