"""The agent endpoints through the real app: MCP servers run as stdio subprocesses."""

import json
import time
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(settings: Settings, db_url: str, loaded_engine: Engine) -> Iterator[TestClient]:
    with loaded_engine.begin() as conn:
        conn.execute(text("delete from agent_runs"))
    s = settings.model_copy(update={"database_url": db_url, "agents_enabled": True})
    with TestClient(create_app(s)) as c:
        yield c


def _wait(client: TestClient, run_id: str, timeout: float = 90) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/runs/{run_id}").json()
        if run["status"] not in ("running",):
            return run
        time.sleep(0.5)
    raise AssertionError(f"run {run_id} still running")


def _sse(body: str) -> list[tuple[str, dict]]:
    out, event = [], None
    for line in body.splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and event:
            out.append((event, json.loads(line.split(":", 1)[1])))
    return out


def test_scan_review_and_traces(client: TestClient) -> None:
    started = client.post("/scan")
    assert started.status_code == 202
    run = _wait(client, started.json()["run_id"])
    assert run["status"] == "paused_review"
    assert any(s["name"].startswith("warehouse-metadata/") for s in run["steps"])

    incidents = client.get("/incidents").json()
    assert sorted(i["severity"] for i in incidents) == ["S1", "S2", "S2", "S2"]
    queue = client.get("/review").json()
    assert [r["severity"] for r in queue["reports"]] == ["S1"]

    report_id = queue["reports"][0]["id"]
    res = client.post(
        f"/review/reports/{report_id}", json={"decision": "approve", "reviewer": "rahul"}
    )
    assert res.json()["status"] == "resumed"
    assert client.get(f"/incidents/{report_id}").json()["status"] == "published"
    assert client.get(f"/runs/{run['id']}").json()["status"] == "completed"
    assert (
        client.post(f"/review/reports/{report_id}", json={"decision": "approve"}).status_code == 409
    )
    assert client.get("/review").json()["reports"] == []

    runs = client.get("/runs").json()
    assert runs[0]["id"] == run["id"] and "llm_calls" in runs[0]


def test_chat_streams_the_graph_and_keeps_the_session(client: TestClient) -> None:
    res = client.post("/chat/stream", json={"question": "are there any duplicate submissions?"})
    events = _sse(res.text)
    kinds = [e for e, _ in events]
    assert kinds[0] == "session" and "plan" in kinds and "finding" in kinds
    assert kinds[-1] in ("done", "paused")
    plan = next(d for e, d in events if e == "plan")
    assert plan["specialists"] == ["reconciliation"]
    session_id = events[0][1]["session_id"]
    msgs = client.get(f"/sessions/{session_id}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["meta"]["run_id"]

    follow = _sse(
        client.post(
            "/chat/stream", json={"question": "how do I fix it?", "session_id": session_id}
        ).text
    )
    assert follow[0][1]["session_id"] == session_id


def test_plan_review_endpoint_refuses_runs_that_are_not_waiting(client: TestClient) -> None:
    fake = "00000000-0000-4000-8000-000000000000"
    assert client.post(f"/review/runs/{fake}", json={"decision": "approve"}).status_code == 409
    assert client.get(f"/runs/{fake}").status_code == 404
    assert client.get(f"/incidents/{fake}").status_code == 404


def test_agent_routes_503_when_agents_are_off(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        assert c.post("/scan").status_code == 503


def test_regenerate_needs_a_model_and_a_known_incident(client: TestClient) -> None:
    started = client.post("/scan")
    _wait(client, started.json()["run_id"])
    incidents = client.get("/incidents").json()
    assert len(incidents) == 4 and all(r["duplicate_of"] is None for r in incidents)
    assert all(r["template"] and r["model_analysis"] is None for r in incidents)
    res = client.post(f"/incidents/{incidents[0]['id']}/regenerate")
    assert res.status_code == 503, "without a model the template stands"
    assert client.post(f"/incidents/{uuid.uuid4()}/regenerate").status_code == 404


def test_a_finding_can_be_reopened_and_signed_off_again(client: TestClient) -> None:
    started = client.post("/scan")
    _wait(client, started.json()["run_id"])
    s1 = next(r for r in client.get("/incidents").json() if r["severity"] == "S1")
    first = client.post(f"/review/reports/{s1['id']}", json={"decision": "approve"})
    assert first.json()["status"] == "resumed"
    assert client.post(f"/incidents/{s1['id']}/reopen", json={"note": "next reviewer"}).is_success
    queue = client.get("/review").json()["reports"]
    assert [r["id"] for r in queue] == [s1["id"]]
    # its run finished when it was first approved, so this decision applies directly
    again = client.post(
        f"/review/reports/{s1['id']}", json={"decision": "annotate", "note": "resend asked"}
    )
    assert again.json()["status"] == "applied"
    after = client.get(f"/incidents/{s1['id']}").json()
    assert after["status"] == "published" and after["review_note"] == "resend asked"
    assert client.post(f"/incidents/{s1['id']}/reopen").is_success
    assert client.post(f"/incidents/{s1['id']}/reopen").status_code == 409, "already open"
