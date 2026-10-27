import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from agent_release_gates.db.repository import Repository
from agent_release_gates.db.session import migrate


@pytest.fixture
def database():
    url = os.environ.get(
        "GATES_TEST_DATABASE_URL",
        "postgresql+psycopg://gates:gates-local-only@127.0.0.1:55415/gates_test",
    )
    if not (make_url(url).database or "").endswith("_test"):
        raise RuntimeError("EXPLICIT_TEST_DATABASE_REQUIRED")
    admin = create_engine(url)
    schema = "test_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        migrate(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        yield engine, factory
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def repo(database):
    return Repository(database[1])
