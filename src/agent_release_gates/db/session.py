import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from alembic import command


def migrate(engine):
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def open_database(url: str | None = None):
    value = url or os.environ.get(
        "GATES_DATABASE_URL",
        "postgresql+psycopg://gates:gates-local-only@127.0.0.1:55415/gates_test",
    )
    engine = create_engine(value, pool_pre_ping=True)
    return engine, sessionmaker(engine, expire_on_commit=False)
