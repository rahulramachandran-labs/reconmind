"""Per-run tracing.

Every node, LLM call, tool call and retrieval inside an agent run is recorded
as a step. Steps always go to Postgres (``agent_steps``) when a database is
configured, so the Traces screen works anywhere; they are mirrored to LangFuse
when its keys are set. ``TracedLLM`` refuses to run outside a run, which is
what makes "no untraced LLM calls" a property of the code rather than a habit.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

log = logging.getLogger(__name__)

_TRACER: ContextVar["RunTracer | None"] = ContextVar("reconmind_tracer", default=None)
_NODE: ContextVar[str] = ContextVar("reconmind_node", default="run")
_PARENT: ContextVar[str | None] = ContextVar("reconmind_parent_span", default=None)


def current_tracer() -> "RunTracer | None":
    return _TRACER.get()


@dataclass
class Step:
    node: str
    kind: str
    name: str
    started_at: datetime
    latency_ms: int = 0
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


class StepSink(Protocol):
    def write(self, run_id: UUID, steps: list[Step]) -> None: ...


class SqlStepSink:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def write(self, run_id: UUID, steps: list[Step]) -> None:
        from sqlalchemy import insert

        from app.db.models import AgentStep

        with self.engine.begin() as conn:
            conn.execute(
                insert(AgentStep),
                [
                    {**asdict(s), "run_id": run_id, "cost_usd": Decimal(str(s.cost_usd))}
                    for s in steps
                ],
            )


_LF_TYPES = {"node": "agent", "llm": "generation", "tool": "tool", "retrieval": "retriever"}


class LangfuseMirror:
    def __init__(self, client: Any) -> None:
        self.client = client

    def trace_id(self, run_id: UUID) -> str:
        return str(self.client.create_trace_id(seed=str(run_id)))

    def url(self, trace_id: str) -> str | None:
        try:
            return str(self.client.get_trace_url(trace_id=trace_id))
        except Exception:  # pragma: no cover - depends on the server
            return None

    def start(self, trace_id: str, parent: str | None, step: Step) -> Any:
        ctx: dict[str, str] = {"trace_id": trace_id}
        if parent:
            ctx["parent_span_id"] = parent
        kwargs: dict[str, Any] = {
            "trace_context": ctx,
            "name": step.name,
            "as_type": _LF_TYPES.get(step.kind, "span"),
            "input": step.input,
            "metadata": {"node": step.node},
        }
        if step.kind == "llm":
            kwargs |= {
                "model": step.model,
                "version": step.prompt_version,
                "usage_details": {"input": step.prompt_tokens, "output": step.completion_tokens},
                "cost_details": {"total": step.cost_usd},
            }
        return self.client.start_observation(**kwargs)

    def end(self, obs: Any, step: Step) -> None:
        obs.update(
            output=step.output, level="ERROR" if step.error else None, status_message=step.error
        )
        obs.end()

    def flush(self) -> None:
        self.client.flush()


class RunTracer:
    def __init__(
        self,
        run_id: UUID,
        sink: StepSink | None = None,
        langfuse: LangfuseMirror | None = None,
    ) -> None:
        self.run_id = run_id
        self.sink = sink
        self.langfuse = langfuse
        self.trace_id = langfuse.trace_id(run_id) if langfuse else run_id.hex
        self.steps: list[Step] = []
        self._pending: list[Step] = []

    @property
    def trace_url(self) -> str | None:
        return self.langfuse.url(self.trace_id) if self.langfuse else None

    def record(self, kind: str, name: str, **fields: Any) -> Step:
        step = Step(
            node=_NODE.get(),
            kind=kind,
            name=name,
            started_at=fields.pop("started_at", None) or datetime.now(UTC),
            **fields,
        )
        self.steps.append(step)
        self._pending.append(step)
        if self.langfuse:
            try:
                self.langfuse.end(self.langfuse.start(self.trace_id, _PARENT.get(), step), step)
            except Exception as exc:  # tracing must never break a run
                log.warning("langfuse mirror failed", extra={"error": str(exc)})
        return step

    @asynccontextmanager
    async def node(self, name: str, input: dict[str, Any] | None = None) -> AsyncIterator[Step]:
        step = Step(
            node=name, kind="node", name=name, started_at=datetime.now(UTC), input=input or {}
        )
        obs = None
        if self.langfuse:
            try:
                obs = self.langfuse.start(self.trace_id, None, step)
            except Exception as exc:
                log.warning("langfuse mirror failed", extra={"error": str(exc)})
        tokens = (
            _TRACER.set(self),
            _NODE.set(name),
            _PARENT.set(getattr(obs, "id", None)),
        )
        start = time.perf_counter()
        try:
            yield step
        except Exception as exc:
            step.error = f"{type(exc).__name__}: {exc}"[:1000]
            raise
        finally:
            step.latency_ms = int((time.perf_counter() - start) * 1000)
            self.steps.append(step)
            self._pending.append(step)
            _PARENT.reset(tokens[2])
            _NODE.reset(tokens[1])
            _TRACER.reset(tokens[0])
            if obs is not None:
                try:
                    self.langfuse.end(obs, step)  # type: ignore[union-attr]
                except Exception as exc:
                    log.warning("langfuse mirror failed", extra={"error": str(exc)})
            await self.flush()

    @asynccontextmanager
    async def activate(self) -> AsyncIterator["RunTracer"]:
        """Make this tracer current outside any node (used by the ask endpoint)."""
        token = _TRACER.set(self)
        try:
            yield self
        finally:
            _TRACER.reset(token)
            await self.flush()

    async def flush(self) -> None:
        if not self._pending:
            return
        pending, self._pending = self._pending, []
        if self.sink:
            try:
                await asyncio.to_thread(self.sink.write, self.run_id, pending)
            except Exception as exc:
                log.warning("could not persist trace steps", extra={"error": str(exc)})
        if self.langfuse:
            try:
                self.langfuse.flush()
            except Exception as exc:  # pragma: no cover
                log.warning("langfuse flush failed", extra={"error": str(exc)})

    def totals(self) -> dict[str, Any]:
        llm = [s for s in self.steps if s.kind == "llm"]
        return {
            "llm_calls": len(llm),
            "tool_calls": sum(1 for s in self.steps if s.kind == "tool"),
            "prompt_tokens": sum(s.prompt_tokens for s in llm),
            "completion_tokens": sum(s.completion_tokens for s in llm),
            "cost_usd": round(sum(s.cost_usd for s in llm), 6),
        }


def build_langfuse(
    public_key: str | None, secret_key: str | None, host: str | None
) -> LangfuseMirror | None:
    if not (public_key and secret_key):
        return None
    from langfuse import Langfuse

    return LangfuseMirror(Langfuse(public_key=public_key, secret_key=secret_key, host=host))
