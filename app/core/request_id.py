"""The id that ties a response header to a log line, a run row and a trace.

A caller may supply its own with ``X-Request-ID``; anything that isn't a short,
plain token is replaced rather than echoed back into logs.
"""

import re
import uuid
from contextvars import ContextVar, Token

HEADER = "x-request-id"
_ALLOWED = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_current: ContextVar[str] = ContextVar("request_id", default="")


def clean(value: str | None) -> str:
    return value if value and _ALLOWED.match(value) else uuid.uuid4().hex


def bind(value: str) -> Token[str]:
    return _current.set(value)


def unbind(token: Token[str]) -> None:
    _current.reset(token)


def request_id() -> str:
    return _current.get()
