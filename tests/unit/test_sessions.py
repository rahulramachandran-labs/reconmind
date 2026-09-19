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


def test_memory_run_store_counts_repeats_instead_of_adding_rows() -> None:
    from app.agents.schemas import AffectedRecords, IncidentReport
    from app.agents.store import MemoryRunStore

    def report(title: str) -> IncidentReport:
        return IncidentReport(
            id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            finding_type="key_drift",
            specialist="reconciliation",
            severity="S2",
            title=title,
            problem_statement="p",
            affected_records=AffectedRecords(count=1, detail="1 records"),
            root_cause_hypothesis="r" * 20,
            recommended_fix=["f"],
            confidence=0.6,
            confidence_label="medium",
            open_questions=[],
            evidence=[],
            sources=[],
            analysis_by="template",
            needs_review=False,
        )

    store = MemoryRunStore()
    first = store.save_reports(uuid.uuid4(), [report("LOC-1 drift")])
    again = store.save_reports(uuid.uuid4(), [report("LOC-1 drift"), report("LOC-2 drift")])
    assert not first[0].repeat
    assert again[0].repeat and again[0].id == first[0].id and not again[1].repeat
    assert len(store.reports) == 2
    assert [e["action"] for e in store.ledger] == [
        "finding.created",
        "finding.seen_again",
        "finding.created",
    ]
