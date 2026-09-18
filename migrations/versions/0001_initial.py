"""initial schema: raw transactions, reference data, audit ledger, chat sessions

Revision ID: 0001
Revises:
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY = """
create or replace function audit_ledger_append_only() returns trigger
language plpgsql as $$
begin
  raise exception 'audit_ledger is append-only: % rejected', tg_op
    using errcode = 'insufficient_privilege',
          hint = 'append a correcting entry that references the original id';
end;
$$;

create trigger audit_ledger_no_update_delete
  before update or delete on audit_ledger
  for each row execute function audit_ledger_append_only();

create trigger audit_ledger_no_truncate
  before truncate on audit_ledger
  for each statement execute function audit_ledger_append_only();
"""


def _ts(name: str, **kw: object) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)  # type: ignore[arg-type]


def upgrade() -> None:
    op.create_table(
        "submitter_registry",
        sa.Column("submitter_id", sa.Text, primary_key=True),
        sa.Column("submitter_name", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("expected_daily_files", sa.Integer, nullable=False, server_default="1"),
        sa.Column("sla_hhmm", sa.Text, nullable=False),
        sa.Column("contact", sa.Text, nullable=False),
    )
    op.create_table(
        "outlet_location_map",
        sa.Column("outlet_id", sa.Text, primary_key=True),
        sa.Column("location_id", sa.Text, nullable=False, index=True),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date),
    )
    op.create_table(
        "outlet_alias",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("alias_outlet_id", sa.Text, nullable=False),
        sa.Column("outlet_id", sa.Text, nullable=False),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date),
        sa.Column("incident_id", sa.Text),
    )
    op.create_table(
        "file_loads",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("file_name", sa.Text, nullable=False, unique=True),
        sa.Column("submitter_id", sa.Text, nullable=False, index=True),
        sa.Column("business_date", sa.Date, nullable=False, index=True),
        _ts("produced_at", nullable=False),
        _ts("landed_at", nullable=False),
        sa.Column("row_count", sa.Integer, nullable=False),
        sa.Column("trailer_count", sa.Integer),
        sa.Column("header", pg.ARRAY(sa.Text), nullable=False),
        sa.Column("missing_columns", pg.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("unexpected_columns", pg.ARRAY(sa.Text), nullable=False, server_default="{}"),
        _ts("loaded_at", nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("outlet_id", sa.Text),
        sa.Column("location_id", sa.Text),
        sa.Column("transaction_id", sa.Text),
        sa.Column("upc_code", sa.Text),
        sa.Column("channel_basket_id", sa.Text),
        sa.Column("submitter_file_name", sa.Text, nullable=False),
        sa.Column("qty", sa.Integer),
        sa.Column("amount", sa.Numeric(12, 2)),
        _ts("event_ts"),
        _ts("loaded_at", nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_transactions_event_ts", "transactions", ["event_ts"])
    op.create_index("ix_transactions_location_event", "transactions", ["location_id", "event_ts"])
    op.create_index(
        "ix_transactions_dedup_key",
        "transactions",
        ["transaction_id", "channel_basket_id", "upc_code"],
    )
    op.create_index("ix_transactions_file", "transactions", ["submitter_file_name"])

    op.create_table(
        "audit_ledger",
        sa.Column("id", sa.BigInteger, primary_key=True),
        _ts("occurred_at", nullable=False, server_default=sa.func.now()),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False, index=True),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("payload", pg.JSONB, nullable=False, server_default="{}"),
    )
    op.execute(APPEND_ONLY)

    op.create_table(
        "chat_sessions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        sa.Column("title", sa.Text),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("meta", pg.JSONB, nullable=False, server_default="{}"),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.execute("drop trigger if exists audit_ledger_no_truncate on audit_ledger")
    op.execute("drop trigger if exists audit_ledger_no_update_delete on audit_ledger")
    op.drop_table("audit_ledger")
    op.execute("drop function if exists audit_ledger_append_only()")
    op.drop_table("transactions")
    op.drop_table("file_loads")
    op.drop_table("outlet_alias")
    op.drop_table("outlet_location_map")
    op.drop_table("submitter_registry")
