from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.guards import RateLimiter, parse_limit, rate_limit, require_writer
from app.config import Settings


def make_app(**overrides: object) -> TestClient:
    app = FastAPI()
    app.state.settings = Settings(_env_file=None, **overrides)
    app.state.rate_limiter = RateLimiter()

    @app.post("/limited", dependencies=[Depends(rate_limit("rate_limit_scan"))])
    def limited() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/write")
    def write(reviewer: str = Depends(require_writer)) -> dict[str, str]:
        return {"reviewer": reviewer}

    return TestClient(app)


def test_parse_limit() -> None:
    assert parse_limit("20/minute") == (20, 60)
    assert parse_limit("5/hours") == (5, 3600)


def test_rate_limit_returns_429_with_retry_after() -> None:
    c = make_app(rate_limit_scan="2/minute")
    assert c.post("/limited").status_code == 200
    assert c.post("/limited").status_code == 200
    r = c.post("/limited")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    other = c.post("/limited", headers={"x-forwarded-for": "10.0.0.9"})
    assert other.status_code == 200, "limits are per client"


def test_rate_limits_can_be_turned_off() -> None:
    c = make_app(rate_limit_scan="1/minute", rate_limits_enabled=False)
    assert all(c.post("/limited").status_code == 200 for _ in range(3))


def test_sliding_window_forgets_old_hits() -> None:
    lim = RateLimiter()
    assert lim.check(("a", "/x"), 1, 0) is None
    assert lim.check(("a", "/x"), 1, 0) is None


def test_writes_are_open_without_a_token() -> None:
    assert make_app().post("/write", headers={"x-reviewer": "sam"}).json() == {"reviewer": "sam"}


def test_writes_need_the_token_when_one_is_set() -> None:
    c = make_app(write_token=SecretStr("s3cret"))
    assert c.post("/write").status_code == 401
    assert c.post("/write", headers={"authorization": "Bearer wrong"}).status_code == 401
    ok = c.post("/write", headers={"authorization": "Bearer s3cret", "x-reviewer": "rahul"})
    assert ok.json() == {"reviewer": "rahul"}
