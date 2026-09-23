"""ASGI middleware: one request id per request, echoed on the response.

Written against the raw ASGI interface rather than ``BaseHTTPMiddleware`` so the
chat stream is not wrapped in another task, which would cut the context the id
lives in halfway through a stream.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.request_id import HEADER, bind, clean, unbind

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class RequestIdMiddleware:
    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        given = next(
            (v.decode("latin-1") for k, v in scope.get("headers", []) if k == HEADER.encode()),
            None,
        )
        rid = clean(given)
        scope.setdefault("state", {})["request_id"] = rid
        token = bind(rid)

        async def send_with_id(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((HEADER.encode(), rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            unbind(token)
