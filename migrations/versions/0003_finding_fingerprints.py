"""fingerprint incident reports so repeated scans don't duplicate them

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("incident_reports", sa.Column("fingerprint", sa.Text))
    op.add_column(
        "incident_reports",
        sa.Column("seen_count", sa.Integer, nullable=False, server_default="1"),
    )
    op.add_column(
        "incident_reports",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "update incident_reports set fingerprint = finding_type || ':' || title, "
        "last_seen_at = created_at"
    )
    op.alter_column("incident_reports", "fingerprint", nullable=False)
    op.alter_column("incident_reports", "last_seen_at", nullable=False)
    op.create_index("ix_incident_reports_fingerprint", "incident_reports", ["fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_incident_reports_fingerprint", table_name="incident_reports")
    op.drop_column("incident_reports", "last_seen_at")
    op.drop_column("incident_reports", "seen_count")
    op.drop_column("incident_reports", "fingerprint")
