"""POST /recommend and GET /recommend/{id}/more.

POST /recommend — the product moment.
    Runs the full pipeline (docs/03-recommendation-engine.md):
    intent extraction → candidates → scoring → MMR → LLM stylist →
    modification application → persist 6 outfits → return ranks 1–3.

GET /recommend/{id}/more — pre-computed second page.
    Returns ranks 4–6 from an already-computed recommendation. No pipeline
    rerun — these rows are already stored; the response is cheap.
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

import repository
from app.auth import CallerDep
from app.schemas import (
    MoreOutfitsResponse,
    OutfitItemOut,
    OutfitOut,
    RecommendRequest,
    RecommendResponse,
)
from pipeline import candidates as candidates_stage
from pipeline import diversity as diversity_stage
from pipeline import intent as intent_stage
from pipeline import scoring as scoring_stage
from pipeline import stylist as stylist_stage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["recommend"])


# ---------------------------------------------------------------------------
# POST /recommend
# ---------------------------------------------------------------------------


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(payload: RecommendRequest, caller: CallerDep) -> RecommendResponse:
    """Generate and return the top 3 outfits (ranks 4–6 pre-stored for /more)."""
    t0 = time.monotonic()

    # Fetch persistent user data (body profile + Style DNA).
    body_profile = repository.get_body_profile(caller.user_id)
    style_dna = repository.get_style_dna(caller.user_id)
    style_descriptors: list[str] = style_dna.get("descriptors", [])

    # Snapshot quiz + context for the DB row.
    context: dict = {"quiz": payload.quiz.model_dump(exclude_none=True)}

    # Write the recommendation row BEFORE the pipeline runs.
    # This guarantees the row exists even if the pipeline errors, so latency
    # can always be back-filled and the seq_no denominator stays correct.
    rec_id = repository.create_recommendation(
        caller.user_id,
        occasion=payload.occasion,
        free_text=payload.free_text,
        context=context,
    )

    degraded = False

    try:
        # --- Step 0: Intent extraction (LLM call #1) ---
        intent, intent_degraded = await intent_stage.extract_intent(
            occasion=payload.occasion,
            free_text=payload.free_text,
            quiz=payload.quiz,
            body_profile=body_profile,
            style_descriptors=style_descriptors,
        )
        degraded = degraded or intent_degraded

        # --- Step 2: Candidate generation ---
        all_garments = repository.list_garments_for_scoring(caller.user_id)
        if not all_garments:
            latency_ms = _elapsed_ms(t0)
            repository.update_recommendation_latency(
                caller.user_id, recommendation_id=rec_id, latency_ms=latency_ms
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "wardrobe_empty",
                    "message": "Add some garments to your wardrobe before requesting a recommendation.",
                },
            )

        raw_candidates = candidates_stage.generate_candidates(all_garments, intent)
        if not raw_candidates:
            latency_ms = _elapsed_ms(t0)
            repository.update_recommendation_latency(
                caller.user_id, recommendation_id=rec_id, latency_ms=latency_ms
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "no_candidates",
                    "message": "Your wardrobe has garments but none match the occasion. Try a different occasion or add more clothes.",
                },
            )

        # --- Step 3: Scoring ---
        scored = scoring_stage.score_candidates(
            raw_candidates, intent, body_profile, style_dna
        )

        # --- Steps 4–5: Top N + MMR diversity ---
        top_n = scored[:20]
        diverse = diversity_stage.apply_mmr(top_n)

        # --- Step 6: LLM stylist (call #2) ---
        verdict, stylist_degraded = await stylist_stage.call_stylist(
            diverse, intent, style_descriptors
        )
        degraded = degraded or stylist_degraded

        # --- Step 7: Modification application ---
        outfit_inserts = stylist_stage.build_outfit_inserts(
            verdict, diverse, all_garments, intent
        )

        if not outfit_inserts:
            # Should not happen, but degrade rather than 500.
            outfit_inserts = _fallback_inserts(diverse[:3], intent)
            degraded = True

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("pipeline error for user %s: %s", caller.user_id, exc)
        # Degrade to the top 3 by score with templated reasons.
        try:
            degraded = True
            outfit_inserts = _fallback_inserts(diverse[:3], intent)  # type: ignore[name-defined]
        except Exception:
            latency_ms = _elapsed_ms(t0)
            repository.update_recommendation_latency(
                caller.user_id, recommendation_id=rec_id, latency_ms=latency_ms
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="recommendation pipeline failed",
            )

    # --- Step 8: Persist all outfits ---
    outfit_rows = repository.insert_outfits(
        caller.user_id, recommendation_id=rec_id, outfits=outfit_inserts
    )
    latency_ms = _elapsed_ms(t0)
    repository.update_recommendation_latency(
        caller.user_id, recommendation_id=rec_id, latency_ms=latency_ms
    )

    # Return ranks 1–3 only; ranks 4–6 are available via GET /recommend/{id}/more.
    top_three = [r for r in outfit_rows if r["rank"] <= 3]
    has_more = any(r["rank"] > 3 for r in outfit_rows)

    return RecommendResponse(
        recommendation_id=rec_id,
        latency_ms=latency_ms,
        degraded=degraded,
        has_more=has_more,
        outfits=[_row_to_out(r) for r in top_three],
    )


# ---------------------------------------------------------------------------
# GET /recommend/{recommendation_id}/more
# ---------------------------------------------------------------------------


@router.get("/recommend/{recommendation_id}/more", response_model=MoreOutfitsResponse)
async def recommend_more(recommendation_id: UUID, caller: CallerDep) -> MoreOutfitsResponse:
    """Return pre-computed ranks 4–6 for an existing recommendation."""
    outfit_rows = repository.get_outfits_more(
        caller.user_id, recommendation_id=recommendation_id
    )
    if not outfit_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No additional outfits found for this recommendation.",
        )

    return MoreOutfitsResponse(
        recommendation_id=recommendation_id,
        outfits=[_row_to_out(r) for r in outfit_rows],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _row_to_out(row: dict) -> OutfitOut:
    return OutfitOut(
        outfit_id=UUID(row["id"]),
        rank=row["rank"],
        items=[
            OutfitItemOut(garment_id=UUID(i["garment_id"]), role=i["role"])
            for i in row.get("items", [])
        ],
        reasons=row.get("reasons", []),
    )


def _fallback_inserts(
    scored: list[scoring_stage.ScoredCandidate],
    intent,
) -> list[repository.OutfitInsert]:
    from repository.queries import OutfitInsert

    return [
        OutfitInsert(
            rank=rank,
            score=sc.score,
            reasons=scoring_stage.templated_reasons(sc, intent),
            items=[{"garment_id": i.garment_id, "role": i.role} for i in sc.candidate.items],
        )
        for rank, sc in enumerate(scored, start=1)
    ]
