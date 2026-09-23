"""Failures as RFC 9457 problem documents.

Every error carries the request id, so a person can quote one string and I can
find the log line, the run and the trace behind it. `detail` keeps the wording
the handlers already raise, and nothing about the inside of the process leaves
the server when APP_ENV is production.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_id import request_id

MEDIA_TYPE = "application/problem+json"
log = logging.getLogger("reconmind")


def problem(
    request: Request,
    status: int,
    detail: str,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    title = HTTPStatus(status).phrase if status in {s.value for s in HTTPStatus} else "Error"
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "request_id": getattr(request.state, "request_id", "") or request_id(),
        **extra,
    }
    return JSONResponse(body, status_code=status, headers=headers, media_type=MEDIA_TYPE)


def install(app: FastAPI) -> None:
    production = app.state.settings.app_env == "production"

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return problem(request, exc.status_code, detail, headers=dict(exc.headers or {}))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(p) for p in e.get("loc", ())[1:]), "problem": e.get("msg", "")}
            for e in exc.errors()
        ]
        return problem(request, 422, "the request body did not validate", errors=fields)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "") or request_id()
        log.exception("unhandled error", extra={"request_id": rid, "path": request.url.path})
        detail = (
            "something went wrong on our side" if production else f"{type(exc).__name__}: {exc}"
        )
        return problem(request, 500, detail)

    # FastAPI's own HTTPException is a subclass, but the handler map is exact
    app.add_exception_handler(HTTPException, http_error)  # type: ignore[arg-type]
