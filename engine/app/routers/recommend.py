"""POST /recommend — the product moment. Structure only, no pipeline."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.auth import CallerDep
from app.schemas import RecommendRequest, RecommendResponse

router = APIRouter(tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(payload: RecommendRequest, caller: CallerDep) -> RecommendResponse:
    """Generate the top 3 outfits for an occasion.

    Not implemented. When it is, the order is fixed by
    docs/03-recommendation-engine.md:

        resolve target profile -> generate candidates -> score
        -> take top ~15-20 -> LLM rerank + explain -> top 3

    The `recommendation` row is written *before* the pipeline runs, so latency can
    be measured and the row survives an engine error; `latency_ms` is filled in
    afterwards. `seq_no` is assigned server-side inside that insert.

    Note `caller` rather than anything in `payload` supplies the user id.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="recommendation pipeline not implemented",
    )
