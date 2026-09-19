"""Runs the investigation graph and turns its updates into events for the API."""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from app.agents.deps import AgentDeps
from app.agents.graph import build_graph
from app.agents.schemas import confidence_label, fingerprint
from app.agents.specialists import analyse, write_ups
from app.observability.tracer import LangfuseMirror, RunTracer, StepSink

log = logging.getLogger(__name__)

Event = dict[str, Any]


class UnknownIncident(LookupError):
    pass


class FindingGone(LookupError):
    """The checks no longer find what the report describes."""


class NoModelWriteUp(RuntimeError):
    """No model produced a write-up that validated; the report keeps its template."""


def to_events(node: str, update: dict[str, Any], roles: set[str]) -> list[Event]:
    events: list[Event] = [{"type": "node", "node": node}]
    if node == "planner":
        events.append({"type": "plan", **update["plan"]})
    elif node in roles:
        for item in update.get("findings", []):
            f = item["finding"]
            events.append(
                {
                    "type": "finding",
                    "specialist": node,
                    "finding_type": f["finding_type"],
                    "severity": f["severity"],
                    "title": f["title"],
                    "affected_records": f["affected_records"],
                }
            )
    elif node == "reporter":
        events += [{"type": "report", **r} for r in update.get("reports", [])]
        events.append({"type": "summary", **update["summary"]})
    elif node == "answer":
        events.append(
            {
                "type": "answer",
                "text": update["answer"],
                "provider": update["answer_provider"],
                "model": update.get("answer_model"),
                "fallbacks": update.get("answer_fallbacks", []),
                "sources": update["sources"],
            }
        )
    elif node == "report_review":
        events.append({"type": "review_applied", "outcome": update.get("review_outcome", [])})
    return events


class InvestigationService:
    def __init__(
        self,
        deps: AgentDeps,
        store: Any,
        checkpointer: BaseCheckpointSaver[Any] | None,
        sink: StepSink | None = None,
        langfuse: LangfuseMirror | None = None,
    ) -> None:
        self.deps = deps
        self.store = store
        self.sink = sink
        self.langfuse = langfuse
        self.roles = {s.role for s in deps.adapter.specialists}
        self._tracers: dict[str, RunTracer] = {}
        self.graph = build_graph(deps, self._tracer_for, checkpointer)

    def _tracer_for(self, run_id: str) -> RunTracer:
        tracer = self._tracers.get(run_id)
        if tracer is None:
            tracer = RunTracer(uuid.UUID(run_id), self.sink, self.langfuse)
            self._tracers[run_id] = tracer
        return tracer

    def new_run(
        self, trigger: str, question: str | None = None, session_id: uuid.UUID | None = None
    ) -> uuid.UUID:
        run_id = uuid.uuid4()
        tracer = self._tracer_for(str(run_id))
        self.store.create_run(
            run_id, trigger, question, self.deps.adapter.name, tracer.trace_id, session_id
        )
        return run_id

    async def regenerate(self, report_id: uuid.UUID, reviewer: str) -> dict[str, Any]:
        """Write an existing finding up again with the model the chain would use now,
        keeping the template's version beside it. Runs as its own traced run, so the
        model calls, tokens and cost show up like any other run's."""
        report = await asyncio.to_thread(self.store.get_incident, report_id)
        if report is None:
            raise UnknownIncident(str(report_id))
        adapter, tools = self.deps.adapter, self.deps.tools
        fp = fingerprint(report["finding_type"], report["title"])
        run_id = await asyncio.to_thread(
            self.new_run, "regenerate", f"Write up again: {report['title']}"
        )
        tracer = self._tracer_for(str(run_id))
        start = time.perf_counter()
        status, summary, error = "failed", None, None
        try:
            async with tracer.node("regenerate", {"report_id": str(report_id)}):
                scope = await adapter.resolve_scope(None, tools)
                findings = await adapter.run_checks(report["specialist"], tools, scope)
                finding = next(
                    (f for f in findings if fingerprint(f.finding_type, f.title) == fp), None
                )
                if finding is None:
                    raise FindingGone(f"the checks no longer find: {report['title']}")
                written = await analyse(self.deps, finding)
            template, model = write_ups(adapter, finding, written)
            if model is None:
                raise NoModelWriteUp(
                    "no model produced a write-up that validated; the template stands"
                )
            patch = {
                "analysis_by": "model",
                "template": template.model_dump(mode="json"),
                "model_analysis": model.model_dump(mode="json"),
                "root_cause_hypothesis": model.root_cause_hypothesis,
                "recommended_fix": model.recommended_fix,
                "open_questions": model.open_questions,
                "confidence": model.confidence,
                "confidence_label": confidence_label(model.confidence),
                "sources": [
                    {k: s.model_dump()[k] for k in ("chunk_id", "doc_id", "title", "section")}
                    for s in written.sources
                ],
            }
            updated = await asyncio.to_thread(
                self.store.update_writeups, report_id, patch, reviewer
            )
            status, summary = "completed", f"Written up again by {model.provider} ({model.model})"
            return dict(updated or {})
        except Exception as exc:
            error = str(exc)[:1000]
            raise
        finally:
            await tracer.flush()
            await asyncio.to_thread(
                self.store.finish_run,
                run_id,
                status,
                summary,
                tracer.totals(),
                int((time.perf_counter() - start) * 1000),
                tracer.trace_url,
                error,
            )
            self._tracers.pop(str(run_id), None)

    async def run(
        self,
        trigger: str,
        question: str | None = None,
        history: list[dict[str, str]] | None = None,
        session_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
    ) -> AsyncIterator[Event]:
        rid: uuid.UUID = (
            run_id
            if run_id is not None
            else await asyncio.to_thread(self.new_run, trigger, question, session_id)
        )
        tracer = self._tracer_for(str(rid))
        yield {
            "type": "run",
            "run_id": str(rid),
            "trace_id": tracer.trace_id,
            "trace_url": tracer.trace_url,
        }
        state = {
            "run_id": str(rid),
            "trigger": trigger,
            "question": question,
            "history": history or [],
            "findings": [],
        }
        async for event in self._drive(rid, state):
            yield event

    async def resume(self, run_id: uuid.UUID, value: Any) -> AsyncIterator[Event]:
        await asyncio.to_thread(self.store.mark, run_id, "running")
        async for event in self._drive(run_id, Command(resume=value)):
            yield event

    async def run_to_end(self, events: AsyncIterator[Event]) -> list[Event]:
        return [e async for e in events]

    async def _drive(self, run_id: uuid.UUID, payload: Any) -> AsyncIterator[Event]:
        config: RunnableConfig = {"configurable": {"thread_id": str(run_id)}}
        tracer = self._tracer_for(str(run_id))
        start = time.perf_counter()
        pause: dict[str, Any] | None = None
        try:
            async for chunk in self.graph.astream(payload, config, stream_mode="updates"):
                for node, update in chunk.items():
                    if node == "__interrupt__":
                        pause = update[0].value
                        continue
                    for event in to_events(node, update or {}, self.roles):
                        yield event
            values = (await self.graph.aget_state(config)).values
            latency = int((time.perf_counter() - start) * 1000)
            await tracer.flush()
            if pause is not None:
                status = "paused_plan" if pause["kind"] == "plan" else "paused_review"
                await asyncio.to_thread(
                    self.store.finish_run,
                    run_id,
                    status,
                    _summary_text(values),
                    tracer.totals(),
                    latency,
                    tracer.trace_url,
                )
                yield {"type": "paused", "run_id": str(run_id), **pause}
            else:
                await asyncio.to_thread(
                    self.store.finish_run,
                    run_id,
                    "completed",
                    _summary_text(values),
                    tracer.totals(),
                    latency,
                    tracer.trace_url,
                )
                yield {
                    "type": "done",
                    "run_id": str(run_id),
                    "latency_ms": latency,
                    "trace_url": tracer.trace_url,
                    **tracer.totals(),
                }
        except Exception as exc:
            log.exception("run failed", extra={"run_id": str(run_id)})
            await tracer.flush()
            await asyncio.to_thread(
                self.store.finish_run,
                run_id,
                "failed",
                None,
                tracer.totals(),
                int((time.perf_counter() - start) * 1000),
                tracer.trace_url,
                str(exc)[:1000],
            )
            yield {"type": "error", "run_id": str(run_id), "message": str(exc)[:300]}
        finally:
            self._tracers.pop(str(run_id), None)


def _summary_text(values: dict[str, Any]) -> str | None:
    if values.get("summary"):
        s = values["summary"]
        return f"{s['headline']}\n\n{s['summary']}"
    return values.get("answer")
