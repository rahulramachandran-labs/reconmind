from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SubmitterRegistry(Base):
    __tablename__ = "submitter_registry"

    submitter_id: Mapped[str] = mapped_column(Text, primary_key=True)
    submitter_name: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    expected_daily_files: Mapped[int] = mapped_column(Integer, default=1)
    sla_hhmm: Mapped[str] = mapped_column(Text)
    contact: Mapped[str] = mapped_column(Text)


class OutletLocationMap(Base):
    __tablename__ = "outlet_location_map"

    outlet_id: Mapped[str] = mapped_column(Text, primary_key=True)
    location_id: Mapped[str] = mapped_column(Text, index=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class OutletAlias(Base):
    __tablename__ = "outlet_alias"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    alias_outlet_id: Mapped[str] = mapped_column(Text)
    outlet_id: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    incident_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class FileLoad(Base):
    __tablename__ = "file_loads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    file_name: Mapped[str] = mapped_column(Text, unique=True)
    submitter_id: Mapped[str] = mapped_column(Text, index=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    produced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    landed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    row_count: Mapped[int] = mapped_column(Integer)
    trailer_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    header: Mapped[list[str]] = mapped_column(ARRAY(Text))
    missing_columns: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    unexpected_columns: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    """Raw line items. Every contract column is nullable here on purpose: the
    loader maps by name, and a batch that loses a column must still be visible."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    outlet_id: Mapped[str | None] = mapped_column(Text)
    location_id: Mapped[str | None] = mapped_column(Text)
    transaction_id: Mapped[str | None] = mapped_column(Text)
    upc_code: Mapped[str | None] = mapped_column(Text)
    channel_basket_id: Mapped[str | None] = mapped_column(Text)
    submitter_file_name: Mapped[str] = mapped_column(Text, index=True)
    qty: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    event_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLedger(Base):
    """Append-only. A trigger in migration 0001 rejects UPDATE, DELETE and TRUNCATE."""

    __tablename__ = "audit_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, index=True)
    subject: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", order_by="ChatMessage.id", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    session: Mapped[ChatSession] = relationship(back_populates="messages")
