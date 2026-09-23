"""Request guards: a small per-process rate limiter and the write token check."""

import hmac
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request

_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def parse_limit(spec: str) -> tuple[int, int]:
    """``"20/minute"`` -> (20, 60)."""
    count, _, unit = spec.partition("/")
    return int(count), _UNITS[unit.strip().rstrip("s")]


class RateLimiter:
    """Sliding window per client and route. In memory, which is right for one API
    instance; several instances would need Redis behind the same interface."""

    def __init__(self) -> None:
        self.hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, key: tuple[str, str], limit: int, window: int) -> float | None:
        now = time.monotonic()
        q = self.hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return window - (now - q[0])
        q.append(now)
        return None


def client_ip(request: Request) -> str:
    """Behind a proxy the peer is the proxy, so the client is the entry
    TRUSTED_PROXY_HOPS in from the right of X-Forwarded-For: each hop appends the address
    it saw, so entries a caller sends itself can only sit further left. Taking the first
    entry instead would let anyone reset their own rate limit with a header."""
    peer = request.client.host if request.client else "unknown"
    hops: int = request.app.state.settings.trusted_proxy_hops
    if hops <= 0:
        return peer
    chain = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    return chain[-hops] if len(chain) >= hops else peer


def rate_limit(setting: str) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        settings = request.app.state.settings
        if not settings.rate_limits_enabled:
            return
        limit, window = parse_limit(getattr(settings, setting))
        limiter: RateLimiter = request.app.state.rate_limiter
        retry = limiter.check((client_ip(request), request.url.path), limit, window)
        if retry is not None:
            raise HTTPException(
                429,
                f"rate limit {getattr(settings, setting)} exceeded",
                headers={"Retry-After": str(int(retry) + 1)},
            )

    return dependency


def require_writer(request: Request) -> str:
    """Scans and review decisions need the server-side token when one is configured.
    Returns the reviewer name the web app vouches for."""
    token = request.app.state.settings.write_token
    if token is not None:
        auth = request.headers.get("authorization", "")
        given = auth.removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given.encode(), token.get_secret_value().encode()):
            raise HTTPException(401, "this action needs a signed-in reviewer")
    return request.headers.get("x-reviewer", "reviewer")[:120]
