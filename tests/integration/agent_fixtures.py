from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.engine import Engine

from app.agents.llm import TracedLLM
from app.agents.nodes import AgentDeps
from app.agents.service import InvestigationService
from app.agents.store import SqlRunStore
from app.config import Settings
from app.domain.registry import get_adapter
from app.llm import LLMChain
from app.observability.tracer import SqlStepSink
from app.retrieval.service import RetrievalService
from app.tools.mcp_toolbox import MCPToolBox
from mcp_servers.orchestration_metadata.server import build_server as orchestration
from mcp_servers.warehouse_metadata.server import build_server as warehouse


@asynccontextmanager
async def retail_service(
    engine: Engine, settings: Settings, providers: list[Any] | None = None, adapter: Any = None
) -> AsyncIterator[InvestigationService]:
    retrieval = RetrievalService.from_settings(settings)
    servers = {"warehouse-metadata": warehouse(engine), "orchestration-metadata": orchestration()}
    async with MCPToolBox(servers) as tools:
        store = SqlRunStore(engine)
        deps = AgentDeps(
            adapter=adapter or get_adapter("retail_recon"),
            tools=tools,
            retrieval=retrieval,
            llm=TracedLLM(LLMChain(providers or [])),
            store=store,
        )
        yield InvestigationService(deps, store, InMemorySaver(), SqlStepSink(engine))
