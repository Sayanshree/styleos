"""Recommendation, feedback, and outfit persistence.

Part of the repository package, so the rules there apply: `user_id` is the
first argument of every public function, never optional, and every query
filters on it. The engine holds the service-role key and bypasses RLS, so
these filters are the tenant boundary — not a convenience.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID, uuid4

from app.schemas import FeedbackSignal
from repository.client import get_client

logger = logging.getLogger(__name__)

GarmentRow = dict[str, Any]
OutfitRow = dict[str, Any]
RecommendationRow = dict[str, Any]


# ---------------------------------------------------------------------------
# recommendation
# ---------------------------------------------------------------------------


def create_recommendation(
    user_id: str,
    *,
    occasion: str,
    context: dict[str, Any],
    free_text: str | None = None,
) -> UUID:
    """Insert the `recommendation` row and return its id.

    Written *before* the scoring pipeline runs, so latency can be measured
    and the row still exists if the engine errors. `latency_ms` is filled in
    afterwards via `update_recommendation_latency`.

    `seq_no` is assigned inside this insert's transaction as
    `max(seq_no) + 1` for the user. It is never client-supplied; the
    `unique (user_id, seq_no)` constraint makes that safe under concurrency.

    Supabase does not support a raw `select coalesce(max(...), 0) + 1` in
    the insert payload, so we fetch the current max and increment here. Under
    low write concurrency this is fine; at higher scale a DB-side trigger or
    advisory lock would be safer.
    """
    client = get_client()

    # Fetch current max seq_no for this user.
    result = (
        client.table("recommendation")
        .select("seq_no")
        .eq("user_id", user_id)
        .order("seq_no", desc=True)
        .limit(1)
        .execute()
    )
    rows = cast(list[RecommendationRow], result.data)
    next_seq = (rows[0]["seq_no"] + 1) if rows else 1

    rec_id = uuid4()
    client.table("recommendation").insert(
        {
            "id": str(rec_id),
            "user_id": user_id,
            "occasion": occasion,
            "free_text": free_text,
            "context": context,
            "seq_no": next_seq,
            # latency_ms intentionally omitted — filled in after the pipeline.
        }
    ).execute()

    return rec_id


def update_recommendation_latency(
    user_id: str,
    *,
    recommendation_id: UUID,
    latency_ms: int,
) -> None:
    """Back-fill `latency_ms` after the pipeline completes."""
    get_client().table("recommendation").update({"latency_ms": latency_ms}).eq(
        "user_id", user_id
    ).eq("id", str(recommendation_id)).execute()


# ---------------------------------------------------------------------------
# outfit + outfit_item
# ---------------------------------------------------------------------------


class OutfitInsert:
    """Transient value holding one outfit's data before it's persisted."""

    __slots__ = ("rank", "score", "reasons", "items")

    def __init__(
        self,
        rank: int,
        score: float,
        reasons: list[str],
        items: list[dict[str, str]],  # [{"garment_id": ..., "role": ...}]
    ) -> None:
        self.rank = rank
        self.score = score
        self.reasons = reasons
        self.items = items  # already validated against owned wardrobe


def insert_outfits(
    user_id: str,
    *,
    recommendation_id: UUID,
    outfits: list[OutfitInsert],
) -> list[OutfitRow]:
    """Persist all outfits (ranks 1–6) and their items in one shot.

    Returns the inserted outfit rows, each augmented with their generated id
    so the caller can build the API response without a second query.
    """
    client = get_client()
    result_rows: list[OutfitRow] = []

    for outfit in outfits:
        outfit_id = uuid4()
        client.table("outfit").insert(
            {
                "id": str(outfit_id),
                "recommendation_id": str(recommendation_id),
                "rank": outfit.rank,
                "score": outfit.score,
                "reasons": outfit.reasons,
            }
        ).execute()

        # Insert outfit_items in one batch.
        item_rows = [
            {
                "outfit_id": str(outfit_id),
                "garment_id": item["garment_id"],
                "role": item["role"],
            }
            for item in outfit.items
        ]
        if item_rows:
            client.table("outfit_item").insert(item_rows).execute()

        result_rows.append(
            {
                "id": str(outfit_id),
                "recommendation_id": str(recommendation_id),
                "rank": outfit.rank,
                "score": outfit.score,
                "reasons": outfit.reasons,
                "items": outfit.items,
            }
        )

    return result_rows


def get_outfits_more(
    user_id: str,
    *,
    recommendation_id: UUID,
) -> list[OutfitRow]:
    """Return ranks 4–6 for an existing recommendation.

    Verifies ownership via the join to `recommendation` — the engine holds
    the service-role key, so this check is the tenant boundary.
    """
    client = get_client()

    # Confirm the recommendation belongs to this user.
    rec = (
        client.table("recommendation")
        .select("id")
        .eq("id", str(recommendation_id))
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not rec.data:
        return []

    outfits_result = (
        client.table("outfit")
        .select("id, rank, score, reasons")
        .eq("recommendation_id", str(recommendation_id))
        .gte("rank", 4)
        .order("rank")
        .execute()
    )
    outfits = cast(list[OutfitRow], outfits_result.data)

    # Fetch items for each outfit.
    for outfit in outfits:
        items_result = (
            client.table("outfit_item")
            .select("garment_id, role")
            .eq("outfit_id", outfit["id"])
            .execute()
        )
        outfit["items"] = cast(list[OutfitRow], items_result.data)

    return outfits


# ---------------------------------------------------------------------------
# feedback_event
# ---------------------------------------------------------------------------


def record_feedback(
    user_id: str,
    *,
    outfit_id: UUID,
    signal: FeedbackSignal,
) -> None:
    """Append a `feedback_event` row.

    Append-only — rows are never updated and never deleted, because the
    timeline is what makes the before/after learning comparison possible.

    `user_id` is verified against the outfit's owner before the insert so a
    caller cannot rate someone else's outfit.
    """
    client = get_client()

    # Verify the outfit belongs to this user (via the recommendation join).
    ownership = (
        client.table("outfit")
        .select("id, recommendation_id")
        .eq("id", str(outfit_id))
        .limit(1)
        .execute()
    )
    if not ownership.data:
        raise LookupError(f"outfit {outfit_id} not found")

    rec_id = ownership.data[0]["recommendation_id"]
    rec_check = (
        client.table("recommendation")
        .select("id")
        .eq("id", rec_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not rec_check.data:
        raise PermissionError(f"outfit {outfit_id} does not belong to user {user_id}")

    client.table("feedback_event").insert(
        {
            "user_id": user_id,
            "outfit_id": str(outfit_id),
            "signal": signal,
        }
    ).execute()
