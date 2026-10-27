import os

from sqlalchemy import create_engine

from agent_release_gates.db.models import Base
from alembic import context

connection = context.config.attributes.get("connection")
if connection is not None:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(os.environ["GATES_DATABASE_URL"])
    with engine.begin() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
