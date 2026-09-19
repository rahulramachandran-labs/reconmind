"""MCP clients for the agents.

Servers are reached over stdio (a subprocess, the default for local runs and
the single-container deploy), over streamable HTTP when a URL is configured
(docker compose), or in-process in tests. Every call is recorded as a traced
tool step.
"""

import json
import sys
import time
from contextlib import AsyncExitStack
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from app.observability.tracer import current_tracer

SERVERS = {
    "warehouse-metadata": "mcp_servers.warehouse_metadata",
    "orchestration-metadata": "mcp_servers.orchestration_metadata",
}


class ToolError(RuntimeError):
    pass


def stdio_params(module: str, env: dict[str, str]) -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=["-m", module], env=env)


class MCPToolBox:
    def __init__(self, targets: dict[str, Any]) -> None:
        """``targets`` maps a server name to anything ``mcp.Client`` accepts: a URL,
        ``StdioServerParameters`` or an in-process server."""
        self.targets = targets
        self._clients: dict[str, Client] = {}
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> "MCPToolBox":
        self._stack = AsyncExitStack()
        for name, target in self.targets.items():
            self._clients[name] = await self._stack.enter_async_context(
                Client(target, read_timeout_seconds=60)
            )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._stack:
            await self._stack.aclose()
        self._clients.clear()

    async def list_tools(self) -> dict[str, list[str]]:
        return {
            name: [t.name for t in (await c.list_tools()).tools]
            for name, c in self._clients.items()
        }

    async def tool_specs(self) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
        """Every tool on every server, described the way models are offered tools, and a
        map from those names back to (server, tool). Names are prefixed with the server,
        ``warehouse__get_table_stats``, so two servers can't collide."""
        specs: list[dict[str, Any]] = []
        route: dict[str, tuple[str, str]] = {}
        for server, client in self._clients.items():
            prefix = server.split("-")[0]
            for t in (await client.list_tools()).tools:
                name = f"{prefix}__{t.name}"
                route[name] = (server, t.name)
                specs.append(
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": (t.description or "")[:500],
                            "parameters": t.input_schema,
                        },
                    }
                )
        return specs, route

    async def call(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        client = self._clients.get(server)
        if client is None:
            raise ToolError(f"no MCP server named {server}")
        tracer = current_tracer()
        start = time.perf_counter()
        error = None
        out: dict[str, Any] = {}
        try:
            res = await client.call_tool(tool, args)
            if res.is_error:
                text = " ".join(getattr(c, "text", "") for c in res.content)
                error = text[:500] or "tool error"
                raise ToolError(f"{server}/{tool}: {error}")
            out = res.structured_content or {}
            if not out and res.content:
                out = json.loads(getattr(res.content[0], "text", "{}") or "{}")
            return out
        finally:
            if tracer:
                tracer.record(
                    kind="tool",
                    name=f"{server}/{tool}",
                    input=args,
                    output=_preview(out),
                    latency_ms=int((time.perf_counter() - start) * 1000),
                    error=error,
                )


def _preview(obj: dict[str, Any], limit: int = 4000) -> dict[str, Any]:
    text = json.dumps(obj, default=str)
    return obj if len(text) <= limit else {"truncated": text[:limit]}
