import argparse
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:+\-]{1,120}$")]


def serve(server: MCPServer, default_port: int) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    ap.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container-internal
    ap.add_argument("--port", type=int, default=default_port)
    args = ap.parse_args()
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port, stateless_http=True)
