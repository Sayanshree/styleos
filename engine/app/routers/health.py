"""GET /health — unauthenticated liveness probe."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the process is up.

    Deliberately unauthenticated and deliberately shallow — this is what the
    platform health check and the cold-start ping call. It touches no dependency
    and says nothing about the database, so it keeps answering even when
    downstream services are down. Making it check Postgres would turn a database
    blip into a rolling restart.
    """
    return HealthResponse()
