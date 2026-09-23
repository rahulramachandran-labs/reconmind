"""Assemble the investigation service from settings."""

import os
from contextlib import AsyncExitStack
from typing import Any

from app.agents.deps import AgentDeps
from app.agents.service import InvestigationService
from app.agents.store import MemoryRunStore, SqlRunStore
from app.core.config import ROOT, Settings
from app.domain.registry import get_adapter
from app.llm.providers import LLMChain
from app.llm.traced import TracedLLM
from app.observability.tracer import SqlStepSink, build_langfuse
from app.retrieval.service import RetrievalService
from app.tools.mcp_toolbox import SERVERS, MCPToolBox, stdio_params


def mcp_targets(settings: Settings) -> dict[str, Any]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k in ("PATH", "HOME", "LANG", "DBT_MANIFEST", "DAG_RUNS_PATH")
    }
    env["PYTHONPATH"] = str(ROOT)
    if settings.database_url:
        env["DATABASE_URL"] = settings.database_url
    urls = {
        "warehouse-metadata": settings.warehouse_mcp_url,
        "orchestration-metadata": settings.orchestration_mcp_url,
    }
    if settings.mcp_transport == "inprocess":
        from app.db.session import get_engine
        from mcp_servers.orchestration_metadata.server import build_server as orchestration
        from mcp_servers.warehouse_metadata.server import build_server as warehouse

        engine = get_engine(settings.database_url) if settings.database_url else None
        local = {"warehouse-metadata": warehouse(engine), "orchestration-metadata": orchestration()}
        return {name: urls[name] or local[name] for name in SERVERS}
    return {name: urls[name] or stdio_params(module, env) for name, module in SERVERS.items()}


async def build_investigations(
    settings: Settings,
    stack: AsyncExitStack,
    retrieval: RetrievalService,
    chain: LLMChain,
    engine: Any | None,
) -> InvestigationService:
    adapter = get_adapter(settings.domain_adapter)
    tools = await stack.enter_async_context(MCPToolBox(mcp_targets(settings)))
    if engine is not None:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        from app.db.session import normalize_url

        conninfo = normalize_url(settings.database_url or "").replace(
            "postgresql+psycopg", "postgresql"
        )
        pool: AsyncConnectionPool[Any] = AsyncConnectionPool(
            conninfo,
            max_size=5,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        await pool.open()
        stack.push_async_callback(pool.close)
        checkpointer: Any = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        store: Any = SqlRunStore(engine)
        sink: Any = SqlStepSink(engine)
    else:
        from langgraph.checkpoint.memory import InMemorySaver

        checkpointer, store, sink = InMemorySaver(), MemoryRunStore(), None
    deps = AgentDeps(
        adapter=adapter,
        tools=tools,
        retrieval=retrieval,
        llm=TracedLLM(chain),
        store=store,
        planner_threshold=settings.planner_confidence_threshold,
        review_threshold=settings.review_confidence_threshold,
        report_max_tokens=settings.llm_max_output_tokens_report,
    )
    langfuse = build_langfuse(
        settings.langfuse_public_key,
        settings.langfuse_secret_key.get_secret_value() if settings.langfuse_secret_key else None,
        settings.langfuse_host,
    )
    return InvestigationService(deps, store, checkpointer, sink, langfuse)
