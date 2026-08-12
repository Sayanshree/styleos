"""POST /feedback — records a signal and updates Style DNA. Structure only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.auth import CallerDep
from app.schemas import FeedbackRequest, FeedbackResponse

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(payload: FeedbackRequest, caller: CallerDep) -> FeedbackResponse:
    """Append a feedback event and return the updated Style DNA descriptors.

    Not implemented. When it is: write the `feedback_event` row (append-only —
    never updated, never deleted), then nudge the user's per-attribute preference
    weights, up for accepted/liked and down for disliked, at a small fixed
    learning rate.

    The response returns descriptors immediately so the UI can show the Style DNA
    shifting in reaction to the rating.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="feedback handling not implemented",
    )
