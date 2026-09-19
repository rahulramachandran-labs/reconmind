"""Chat session memory. Postgres when DATABASE_URL is set, in-process otherwise."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy import Engine, func, select

from app.db.models import ChatMessage, ChatSession
from app.db.session import session_scope

MAX_MESSAGES = 200


@dataclass
class StoredMessage:
    role: str
    content: str
    created_at: datetime
    meta: dict[str, Any] = field(default_factory=dict)


class SessionFull(RuntimeError):
    pass


class SessionStore(Protocol):
    def create(self, title: str | None = None) -> UUID: ...
    def exists(self, session_id: UUID) -> bool: ...
    def append(
        self, session_id: UUID, role: str, content: str, meta: dict[str, Any] | None = None
    ) -> None: ...
    def history(self, session_id: UUID, limit: int = 20) -> list[StoredMessage]: ...


class MemorySessionStore:
    def __init__(self) -> None:
        self._data: dict[UUID, list[StoredMessage]] = {}

    def create(self, title: str | None = None) -> UUID:
        sid = uuid.uuid4()
        self._data[sid] = []
        return sid

    def exists(self, session_id: UUID) -> bool:
        return session_id in self._data

    def append(
        self, session_id: UUID, role: str, content: str, meta: dict[str, Any] | None = None
    ) -> None:
        msgs = self._data.setdefault(session_id, [])
        if len(msgs) >= MAX_MESSAGES:
            raise SessionFull(str(session_id))
        msgs.append(StoredMessage(role, content, datetime.now(UTC), meta or {}))

    def history(self, session_id: UUID, limit: int = 20) -> list[StoredMessage]:
        return self._data.get(session_id, [])[-limit:]


class SqlSessionStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, title: str | None = None) -> UUID:
        with session_scope(self.engine) as s:
            row = ChatSession(title=title[:120] if title else None)
            s.add(row)
            s.flush()
            return row.id

    def exists(self, session_id: UUID) -> bool:
        with session_scope(self.engine) as s:
            return s.get(ChatSession, session_id) is not None

    def append(
        self, session_id: UUID, role: str, content: str, meta: dict[str, Any] | None = None
    ) -> None:
        with session_scope(self.engine) as s:
            n = s.scalar(
                select(func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.session_id == session_id)
            )
            if (n or 0) >= MAX_MESSAGES:
                raise SessionFull(str(session_id))
            s.add(ChatMessage(session_id=session_id, role=role, content=content, meta=meta or {}))

    def history(self, session_id: UUID, limit: int = 20) -> list[StoredMessage]:
        with session_scope(self.engine) as s:
            rows = s.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.desc())
                .limit(limit)
            ).all()
            return [StoredMessage(r.role, r.content, r.created_at, r.meta) for r in reversed(rows)]


class SessionHistory(BaseChatMessageHistory):
    """One chat session as a LangChain message history, over either store, so the rest
    of the code can read and write conversation turns as LangChain messages."""

    def __init__(self, store: SessionStore, session_id: UUID, limit: int = 20) -> None:
        self.store, self.session_id, self.limit = store, session_id, limit

    @property
    def messages(self) -> list[BaseMessage]:  # type: ignore[override]
        return [
            HumanMessage(m.content) if m.role == "user" else AIMessage(m.content)
            for m in self.store.history(self.session_id, limit=self.limit)
        ]

    def add_message(self, message: BaseMessage) -> None:
        role = "user" if isinstance(message, HumanMessage) else "assistant"
        meta = dict(message.additional_kwargs.get("meta") or {})
        self.store.append(self.session_id, role, str(message.content), meta)

    def clear(self) -> None:
        raise NotImplementedError("sessions are kept; start a new one instead")
