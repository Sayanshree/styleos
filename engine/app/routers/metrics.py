"""GET /metrics — evaluation numbers for the calling user. Structure only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.auth import CallerDep
from app.schemas import MetricsResponse

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=MetricsResponse)
async def metrics(caller: CallerDep) -> MetricsResponse:
    """Return acceptance rates and the before/after-learning improvement.

    Authenticated and scoped to the caller — these are one user's numbers, not
    the service's, so this route is not a Prometheus-style scrape target.

    Not implemented. When it is, the early/later split is a WHERE clause on
    `recommendation.seq_no` (<= N versus > N), not a window function over
    timestamps, and acceptance is measured per *recommendation* rather than per
    outfit: the user is shown three options and picking any one is a success.
    Every rate ships with its `n`.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="metrics not implemented",
    )
