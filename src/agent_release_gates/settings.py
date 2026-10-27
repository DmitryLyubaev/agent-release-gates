import os
from pathlib import Path

from agent_release_gates.db.repository import Repository
from agent_release_gates.db.session import migrate, open_database
from agent_release_gates.evaluation.judge import ScriptedJudge
from agent_release_gates.service import EvaluationService


def make_service(responses=None):
    engine, factory = open_database()
    migrate(engine)
    return EvaluationService(
        Repository(factory),
        Path(os.environ.get("GATES_ARTIFACT_ROOT", "artifacts")),
        ScriptedJudge(responses or {}),
    )


def app_factory():
    from agent_release_gates.api import create_app

    return create_app(make_service())
