"""Every response carries a request id, and every failure is a problem document."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def test_a_request_id_comes_back_on_every_response(client: TestClient) -> None:
    r = client.get("/healthz")
    assert len(r.headers["x-request-id"]) == 32


def test_a_callers_own_id_is_echoed(client: TestClient) -> None:
    r = client.get("/healthz", headers={"X-Request-ID": "deploy-42.check_1"})
    assert r.headers["x-request-id"] == "deploy-42.check_1"


@pytest.mark.parametrize("forged", ["a" * 65, "id with spaces", "drop;table", ""])
def test_an_id_that_is_not_a_plain_token_is_replaced(client: TestClient, forged: str) -> None:
    r = client.get("/healthz", headers={"X-Request-ID": forged})
    assert r.headers["x-request-id"] != forged
    assert len(r.headers["x-request-id"]) == 32


def test_a_failure_is_a_problem_document_naming_the_request(client: TestClient) -> None:
    r = client.get("/incidents/not-a-uuid", headers={"X-Request-ID": "ref-1"})
    assert r.status_code >= 400
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == r.status_code
    assert body["instance"] == "/incidents/not-a-uuid"
    assert body["request_id"] == "ref-1"
    assert isinstance(body["detail"], str) and body["detail"]
    assert "Traceback" not in body["detail"]


def test_an_invalid_body_says_which_field(client: TestClient) -> None:
    r = client.post("/ask", json={"k": 4})
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == 422 and body["title"].startswith("Unprocessable")
    assert [e["field"] for e in body["errors"]] == ["question"]
