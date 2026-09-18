"""agent runs, traced steps and incident reports

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts(name: str, **kw: object) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)  # type: ignore[arg-type]


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("trigger", sa.Text, nullable=False),
        sa.Column("question", sa.Text),
        sa.Column("session_id", pg.UUID(as_uuid=True)),
        sa.Column("adapter", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, index=True),
        sa.Column("plan", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("summary", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("trace_id", sa.Text),
        sa.Column("trace_url", sa.Text),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer),
        _ts("started_at", nullable=False, server_default=sa.func.now()),
        _ts("finished_at"),
    )
    op.create_index("ix_agent_runs_started_at", "agent_runs", ["started_at"])
    op.create_table(
        "agent_steps",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "run_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("node", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("provider", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("prompt_version", sa.Text),
        sa.Column("input", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("output", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text),
        _ts("started_at", nullable=False),
    )
    op.create_table(
        "incident_reports",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("finding_type", sa.Text, nullable=False, index=True),
        sa.Column("severity", sa.Text, nullable=False, index=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, index=True),
        sa.Column("report", pg.JSONB, nullable=False),
        sa.Column("review_decision", sa.Text),
        sa.Column("review_note", sa.Text),
        sa.Column("reviewed_by", sa.Text),
        _ts("reviewed_at"),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("incident_reports")
    op.drop_table("agent_steps")
    op.drop_index("ix_agent_runs_started_at", table_name="agent_runs")
    op.drop_table("agent_runs")
