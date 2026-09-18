import uuid
from typing import Any

import pytest

from app.observability.tracer import LangfuseMirror, RunTracer, Step, current_tracer


class FakeObs:
    def __init__(self, log: list[Any], kwargs: dict[str, Any]) -> None:
        self.id = f"span-{len(log)}"
        self.log, self.kwargs = log, kwargs

    def update(self, **kw: Any) -> None:
        self.kwargs["update"] = kw

    def end(self) -> None:
        self.log.append(self.kwargs)


class FakeLangfuse:
    def __init__(self) -> None:
        self.log: list[Any] = []
        self.flushed = 0

    def create_trace_id(self, seed: str) -> str:
        return "t" + seed.replace("-", "")[:31]

    def get_trace_url(self, trace_id: str) -> str:
        return f"https://langfuse.local/trace/{trace_id}"

    def start_observation(self, **kw: Any) -> FakeObs:
        return FakeObs(self.log, kw)

    def flush(self) -> None:
        self.flushed += 1


class ListSink:
    def __init__(self) -> None:
        self.written: list[Step] = []

    def write(self, run_id: uuid.UUID, steps: list[Step]) -> None:
        self.written.extend(steps)


async def test_node_context_attributes_child_steps_and_flushes() -> None:
    sink = ListSink()
    tracer = RunTracer(uuid.uuid4(), sink=sink)
    assert current_tracer() is None
    async with tracer.node("planner"):
        assert current_tracer() is tracer
        tracer.record(kind="tool", name="orchestration-metadata/list_dag_runs", latency_ms=3)
        tracer.record(
            kind="llm",
            name="planner",
            provider="p",
            prompt_tokens=10,
            completion_tokens=5,
            cost_usd=0.01,
        )
    assert current_tracer() is None
    assert [(s.node, s.kind) for s in sink.written] == [
        ("planner", "tool"),
        ("planner", "llm"),
        ("planner", "node"),
    ]
    assert tracer.totals() == {
        "llm_calls": 1,
        "tool_calls": 1,
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "cost_usd": 0.01,
    }


async def test_errors_are_recorded_on_the_node() -> None:
    tracer = RunTracer(uuid.uuid4())
    with pytest.raises(RuntimeError):
        async with tracer.node("reporter"):
            raise RuntimeError("boom")
    assert tracer.steps[-1].error == "RuntimeError: boom"


async def test_langfuse_mirror_nests_children_under_the_node() -> None:
    lf = FakeLangfuse()
    run_id = uuid.uuid4()
    tracer = RunTracer(run_id, langfuse=LangfuseMirror(lf))
    async with tracer.node("data_quality"):
        tracer.record(
            kind="llm",
            name="analyse",
            model="m",
            prompt_version="v@1",
            prompt_tokens=7,
            completion_tokens=3,
            cost_usd=0.002,
        )
    child, node = lf.log
    assert child["as_type"] == "generation" and child["version"] == "v@1"
    assert child["trace_context"]["parent_span_id"] == "span-0"
    assert child["usage_details"] == {"input": 7, "output": 3}
    assert node["as_type"] == "agent"
    assert tracer.trace_url == f"https://langfuse.local/trace/{tracer.trace_id}"
    assert lf.flushed == 1


async def test_a_broken_sink_does_not_break_the_run() -> None:
    class Broken:
        def write(self, run_id: uuid.UUID, steps: list[Step]) -> None:
            raise OSError("disk full")

    tracer = RunTracer(uuid.uuid4(), sink=Broken())
    async with tracer.node("finalize"):
        pass
    assert tracer.steps
