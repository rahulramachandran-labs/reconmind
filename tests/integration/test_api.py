from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def test_healthz(client: TestClient) -> None:
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["chunks"] > 50
    assert body["llm_provider"] == "extractive"


def test_ask_returns_answer_with_sources(client: TestClient) -> None:
    r = client.post("/ask", json={"question": "which submitter file wins on a resend?", "k": 4})
    assert r.status_code == 200
    body = r.json()
    assert len(body["sources"]) == 4
    assert body["provider"] == "extractive"
    assert body["answer"]


def test_ask_rejects_short_and_oversized_questions(client: TestClient) -> None:
    assert client.post("/ask", json={"question": "hi"}).status_code == 422
    assert client.post("/ask", json={"question": "x" * 1001}).status_code == 413
    assert client.post("/ask", json={"question": "valid question", "k": 50}).status_code == 422


def test_search_and_corpus(client: TestClient) -> None:
    hits = client.get("/search", params={"q": "channel_basket_id renamed", "k": 3}).json()
    assert len(hits) == 3
    assert [h["rank"] for h in hits] == [1, 2, 3]
    docs = client.get("/corpus").json()
    assert {d["doc_type"] for d in docs} >= {"runbook", "schema", "incident"}


def test_cors_allows_frontend_origin(client: TestClient) -> None:
    r = client.options(
        "/ask",
        headers={
            "Origin": "https://reconmind-labs.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers["access-control-allow-origin"] == "https://reconmind-labs.vercel.app"
