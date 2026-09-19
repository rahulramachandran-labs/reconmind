import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agents.schemas import ReviewDecision
from app.agents.service import (
    FindingGone,
    InvestigationService,
    NoModelWriteUp,
    UnknownIncident,
)
from app.api.deps import get_app_settings, get_sessions
from app.api.guards import rate_limit, require_writer
from app.core.config import Settings
from app.memory.sessions import SessionFull, SessionStore

router = APIRouter()
Sessions = Annotated[SessionStore, Depends(get_sessions)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]


def get_service(request: Request) -> InvestigationService:
    service = getattr(request.app.state, "investigations", None)
    if service is None:
        raise HTTPException(503, "agents are not enabled on this deployment")
    return service


Service = Annotated[InvestigationService, Depends(get_service)]
Reviewer = Annotated[str, Depends(require_writer)]
_background: set[asyncio.Task[Any]] = set()


def _spawn(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


class ChatRequest(BaseModel):
    question: str = Field(min_length=3)
    session_id: uuid.UUID | None = None


class PlanReview(BaseModel):
    decision: Literal["approve", "reject"]
    specialists: list[str] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=2000)
    reviewer: str = Field(default="reviewer", max_length=120)


def _final_text(events: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    for e in reversed(events):
        if e["type"] == "answer":
            return e["text"], {"provider": e["provider"]}
        if e["type"] == "summary":
            return f"{e['headline']}\n\n{e['summary']}", {}
        if e["type"] == "paused":
            return "Paused for a human decision in the review queue.", {}
    return "", {}


@router.post("/chat/stream", dependencies=[Depends(rate_limit("rate_limit_chat"))])
async def chat_stream(
    body: ChatRequest, service: Service, sessions: Sessions, settings: AppSettings
) -> EventSourceResponse:
    question = body.question.strip()
    if len(question) > settings.max_question_chars:
        raise HTTPException(413, f"question longer than {settings.max_question_chars} characters")
    if body.session_id and sessions.exists(body.session_id):
        session_id = body.session_id
    else:
        session_id = sessions.create(title=question)
    history = [
        {"role": m.role, "content": m.content}
        for m in sessions.history(session_id, limit=settings.history_turns * 2)
    ]

    async def events() -> AsyncIterator[dict[str, str]]:
        yield {"event": "session", "data": json.dumps({"session_id": str(session_id)})}
        seen: list[dict[str, Any]] = []
        run_id = None
        async for event in service.run("question", question, history, session_id):
            seen.append(event)
            run_id = event.get("run_id", run_id)
            yield {"event": event["type"], "data": json.dumps(event, default=str)}
        text, meta = _final_text(seen)
        try:
            sessions.append(session_id, "user", question)
            sessions.append(session_id, "assistant", text, meta | {"run_id": run_id})
        except SessionFull:
            yield {"event": "error", "data": json.dumps({"message": "session is full"})}

    return EventSourceResponse(events(), ping=10)


@router.post("/scan", status_code=202, dependencies=[Depends(rate_limit("rate_limit_scan"))])
async def scan(service: Service, _: Reviewer) -> dict[str, str]:
    run_id = await asyncio.to_thread(service.new_run, "scan")
    _spawn(service.run_to_end(service.run("scan", run_id=run_id)))
    return {"run_id": str(run_id), "status": "started"}


@router.get("/runs")
def runs(service: Service, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[dict[str, Any]]:
    return service.store.list_runs(limit)


@router.get("/runs/{run_id}")
def run_detail(run_id: uuid.UUID, service: Service) -> dict[str, Any]:
    run = service.store.get_run(run_id)
    if run is None:
        raise HTTPException(404, "unknown run")
    return run


@router.get("/incidents")
def incidents(
    service: Service,
    status: Literal["pending_review", "published", "rejected"] | None = None,
    severity: Literal["S1", "S2", "S3", "S4"] | None = None,
) -> list[dict[str, Any]]:
    return service.store.list_incidents(status, severity)


@router.get("/incidents/{report_id}")
def incident(report_id: uuid.UUID, service: Service) -> dict[str, Any]:
    r = service.store.get_incident(report_id)
    if r is None:
        raise HTTPException(404, "unknown incident")
    return r


@router.post(
    "/incidents/{report_id}/regenerate",
    dependencies=[Depends(rate_limit("rate_limit_regenerate"))],
)
async def regenerate(report_id: uuid.UUID, service: Service, reviewer: Reviewer) -> dict[str, Any]:
    """Write the finding up again with the active model; the template's version is kept."""
    try:
        return await service.regenerate(report_id, reviewer)
    except UnknownIncident as exc:
        raise HTTPException(404, "unknown incident") from exc
    except FindingGone as exc:
        raise HTTPException(409, str(exc)) from exc
    except NoModelWriteUp as exc:
        raise HTTPException(503, str(exc)) from exc


class Reopen(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


@router.post(
    "/incidents/{report_id}/reopen", dependencies=[Depends(rate_limit("rate_limit_regenerate"))]
)
def reopen(
    report_id: uuid.UUID, service: Service, reviewer: Reviewer, body: Reopen | None = None
) -> dict[str, Any]:
    """Put a decided finding back in the review queue (the fix didn't hold, or the next
    reviewer should see it). The earlier decision stays in the ledger."""
    report = service.store.reopen(report_id, (body.note if body else None), reviewer)
    if report is None:
        raise HTTPException(409, "only a published or rejected finding can be reopened")
    return report


@router.get("/review")
def review_queue(service: Service) -> dict[str, Any]:
    return {
        "reports": service.store.list_incidents(status="pending_review"),
        "plans": service.store.paused_plan_runs(),
    }


@router.post("/review/reports/{report_id}")
async def review_report(
    report_id: uuid.UUID, body: ReviewDecision, service: Service, reviewer: Reviewer
) -> dict[str, Any]:
    run_id = await asyncio.to_thread(
        service.store.record_decision, report_id, body.decision, body.note, reviewer
    )
    if run_id is None:
        raise HTTPException(409, "that report is not waiting for review")
    run = await asyncio.to_thread(service.store.get_run_row, run_id)
    if run is None or run["status"] != "paused_review":
        # a reopened finding: its run finished long ago, so the decision is applied directly
        decision = {"decision": body.decision, "note": body.note, "reviewer": reviewer}
        applied = await asyncio.to_thread(
            service.store.apply_decisions, run_id, {str(report_id): decision}
        )
        return {"status": "applied", "run_id": str(run_id), "outcome": applied}
    decided, remaining = await asyncio.to_thread(service.store.pending_decisions, run_id)
    if remaining:
        return {"status": "recorded", "remaining": remaining}
    events = await service.run_to_end(service.resume(run_id, decided))
    outcome: list[dict[str, Any]] = next(
        (e["outcome"] for e in events if e["type"] == "review_applied"), []
    )
    return {"status": "resumed", "run_id": str(run_id), "outcome": outcome}


@router.post("/review/runs/{run_id}")
async def review_plan(
    run_id: uuid.UUID, body: PlanReview, service: Service, reviewer: Reviewer
) -> dict[str, Any]:
    run = service.store.get_run_row(run_id)
    if run is None or run["status"] != "paused_plan":
        raise HTTPException(409, "that run is not waiting for a plan decision")
    _spawn(service.run_to_end(service.resume(run_id, body.model_dump() | {"reviewer": reviewer})))
    return {"status": "resumed", "run_id": str(run_id)}
