from agent_release_gates.db.models import LiveStudyRecord
from alembic import op

revision = "0002_live_studies"
down_revision = "0001_audit"


def upgrade():
    LiveStudyRecord.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("AUDIT_DOWNGRADE_NOT_SUPPORTED")
