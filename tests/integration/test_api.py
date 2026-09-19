from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def test_healthz(client: TestClient) -> None:
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["chunks"] > 60
    assert body["retriever"] == "hybrid"
    assert body["llm_providers"] == ["extractive"]
    assert body["database"] is False


def test_ask_creates_a_session_and_remembers_it(client: TestClient) -> None:
    r = client.post("/ask", json={"question": "which submitter file wins on a resend?", "k": 4})
    assert r.status_code == 200
    body = r.json()
    assert len(body["sources"]) == 4 and body["provider"] == "extractive"
    sid = body["session_id"]
    follow = client.post("/ask", json={"question": "why?", "session_id": sid}).json()
    assert follow["session_id"] == sid
    assert follow["retrieval_query"].startswith("which submitter file wins")
    msgs = client.get(f"/sessions/{sid}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[1]["meta"]["provider"] == "extractive"


def test_unknown_session_id_starts_a_new_one(client: TestClient) -> None:
    fake = "00000000-0000-4000-8000-000000000000"
    body = client.post(
        "/ask", json={"question": "how is key drift detected?", "session_id": fake}
    ).json()
    assert body["session_id"] != fake
    assert client.get(f"/sessions/{fake}/messages").status_code == 404


def test_ask_rejects_short_and_oversized_questions(client: TestClient) -> None:
    assert client.post("/ask", json={"question": "hi"}).status_code == 422
    assert client.post("/ask", json={"question": "x" * 1001}).status_code == 413
    assert client.post("/ask", json={"question": "valid question", "k": 50}).status_code == 422


def test_search_modes_and_corpus(client: TestClient) -> None:
    hybrid = client.get("/search", params={"q": "channel_basket_id renamed", "k": 3}).json()
    assert len(hybrid) == 3 and hybrid[0]["bm25_rank"] is not None
    bm25 = client.get("/search", params={"q": "basket_ref", "k": 3, "mode": "bm25"}).json()
    assert bm25 and all(h["dense_rank"] is None for h in bm25)
    dense = client.get("/search", params={"q": "basket_ref", "k": 2, "mode": "dense"}).json()
    assert len(dense) == 2
    docs = client.get("/corpus").json()
    assert {d["doc_type"] for d in docs} >= {"runbook", "schema", "incident", "dbt_model"}


def test_corpus_document_body(client: TestClient) -> None:
    doc = client.get("/corpus/runbooks/schema-drift").json()
    assert doc["title"].startswith("Schema drift") and "## Tolerance rules" in doc["body"]
    assert client.get("/corpus/dbt/stg_transactions").json()["doc_type"] == "dbt_model"
    assert client.get("/corpus/nope").status_code == 404


def test_cors_allows_frontend_origin(client: TestClient) -> None:
    r = client.options(
        "/ask",
        headers={
            "Origin": "https://reconmind-labs.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers["access-control-allow-origin"] == "https://reconmind-labs.vercel.app"


def test_uses_database_sessions_when_available(
    settings: Settings, db_url: str, migrated_engine: object
) -> None:
    s = settings.model_copy(update={"database_url": db_url})
    with TestClient(create_app(s)) as c:
        assert c.get("/healthz").json()["database"] is True
        sid = c.post("/ask", json={"question": "how do I detect key drift?"}).json()["session_id"]
        assert len(c.get(f"/sessions/{sid}/messages").json()) == 2


def test_unreachable_database_falls_back_to_memory(settings: Settings) -> None:
    s = settings.model_copy(update={"database_url": "postgresql://x:y@127.0.0.1:1/none"})
    with TestClient(create_app(s)) as c:
        assert c.get("/healthz").json()["database"] is False
