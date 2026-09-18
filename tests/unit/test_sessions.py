import uuid

import pytest

from app.sessions import MAX_MESSAGES, MemorySessionStore, SessionFull


def test_memory_store_keeps_order_and_limits_history() -> None:
    store = MemorySessionStore()
    sid = store.create("first question")
    assert store.exists(sid) and not store.exists(uuid.uuid4())
    for i in range(5):
        store.append(sid, "user" if i % 2 == 0 else "assistant", f"m{i}", {"i": i})
    assert [m.content for m in store.history(sid, limit=2)] == ["m3", "m4"]
    assert store.history(uuid.uuid4()) == []


def test_memory_store_refuses_to_grow_forever() -> None:
    store = MemorySessionStore()
    sid = store.create()
    for _ in range(MAX_MESSAGES):
        store.append(sid, "user", "x")
    with pytest.raises(SessionFull):
        store.append(sid, "user", "one too many")
