"""What a production deployment must have before it serves a request.

Local runs and tests keep every default. In production the three settings below
are the difference between a demo and a service that can be trusted with a
review decision, so the process refuses to start without them and says why.
"""

import logging

from app.core.config import Settings

log = logging.getLogger("reconmind")


class Misconfigured(RuntimeError):
    pass


def check_production(settings: Settings) -> None:
    if settings.app_env != "production":
        return
    problems = []
    if settings.write_token is None:
        problems.append("WRITE_TOKEN is unset: anyone could scan or sign a finding off")
    if not settings.database_url:
        problems.append("DATABASE_URL is unset: runs, reports and the ledger would live in memory")
    wild = [o for o in settings.cors_origins if "*" in o]
    if wild:
        problems.append(f"CORS_ORIGINS allows any origin ({', '.join(wild)})")
    if problems:
        raise Misconfigured("refusing to start in production:\n" + "\n".join(problems))
    if settings.demo_mode:
        log.warning("DEMO_MODE is on in production: paid providers are dropped from the chain")
