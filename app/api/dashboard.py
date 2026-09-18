import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from app.api.agents import Service

router = APIRouter()


@router.get("/dashboard")
async def dashboard(service: Service) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    overview, usage, findings = await asyncio.gather(
        service.deps.adapter.overview(service.deps.tools),
        asyncio.to_thread(service.store.usage_on, today),
        asyncio.to_thread(service.store.open_findings),
    )
    return {
        "pipeline": overview,
        "usage": usage,
        "findings": findings,
        "adapter": service.deps.adapter.title,
    }
