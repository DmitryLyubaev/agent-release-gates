from agent_release_gates.db.models import Base
from alembic import op

revision = "0001_audit"
down_revision = None


def upgrade():
    Base.metadata.create_all(op.get_bind())
    op.execute(
        "CREATE FUNCTION reject_audit_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'IMMUTABLE_AUDIT_RECORD'; END; $$"
    )
    for name in [
        "datasets",
        "runs",
        "packets",
        "label_revisions",
        "evaluations",
        "evaluation_runs",
        "qualifications",
        "qualification_runs",
        "decisions",
    ]:
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION reject_audit_change()"
        )


def downgrade():
    raise RuntimeError("AUDIT_DOWNGRADE_NOT_SUPPORTED")
