"""Body profile and Style DNA persistence.

Part of the repository package — `user_id` is the first argument of every
function, never optional, and every query filters on it.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from repository.client import get_client

logger = logging.getLogger(__name__)

ProfileRow = dict[str, Any]
DnaRow = dict[str, Any]

# Default Style DNA weights when no history exists yet. Each attribute maps
# to a weight in [0, 1]. The learning algorithm nudges these on feedback.
DEFAULT_DNA_WEIGHTS: dict[str, Any] = {
    "colors": {},       # hue-bucket → weight
    "style_tags": {},   # tag → weight
    "fits": {},         # fit value → weight
    "formality": {},    # "1"…"5" → weight
}


def get_body_profile(user_id: str) -> ProfileRow | None:
    """Return the user's body profile, or None if they have not set one."""
    result = (
        get_client()
        .table("body_profile")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = cast(list[ProfileRow], result.data)
    return rows[0] if rows else None


def upsert_body_profile(user_id: str, *, fields: ProfileRow) -> ProfileRow:
    """Create or replace the user's body profile."""
    allowed = {"height_cm", "body_type", "preferred_fit", "preferred_coverage", "notes"}
    clean = {k: v for k, v in fields.items() if k in allowed}
    clean["user_id"] = user_id

    result = (
        get_client()
        .table("body_profile")
        .upsert(clean, on_conflict="user_id")
        .execute()
    )
    rows = cast(list[ProfileRow], result.data)
    return rows[0] if rows else clean


def get_style_dna(user_id: str) -> DnaRow:
    """Return the user's Style DNA, creating a blank one if absent."""
    result = (
        get_client()
        .table("style_dna")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = cast(list[DnaRow], result.data)
    if rows:
        return rows[0]

    # Bootstrap an empty Style DNA row on first access.
    blank: DnaRow = {
        "user_id": user_id,
        "weights": DEFAULT_DNA_WEIGHTS,
        "descriptors": [],
    }
    get_client().table("style_dna").insert(blank).execute()
    return blank


def update_style_dna(
    user_id: str,
    *,
    weights: dict[str, Any],
    descriptors: list[str],
) -> DnaRow:
    """Persist updated preference weights and human-readable descriptors."""
    result = (
        get_client()
        .table("style_dna")
        .update({"weights": weights, "descriptors": descriptors})
        .eq("user_id", user_id)
        .execute()
    )
    rows = cast(list[DnaRow], result.data)
    return rows[0] if rows else {"user_id": user_id, "weights": weights, "descriptors": descriptors}


def list_garments_for_scoring(user_id: str) -> list[dict[str, Any]]:
    """Return all garments for a user, with the fields the scoring pipeline needs.

    Deliberately a separate function from the garments router's list — it
    selects only the columns the pipeline touches, and returns them as plain
    dicts rather than signed-URL-enriched GarmentOut objects.
    """
    result = (
        get_client()
        .table("garment")
        .select(
            "id, category, subcategory, garment_type, color_primary, "
            "material, fit, length, sleeve, formality, seasons, "
            "style_tags, occasion_tags"
        )
        .eq("user_id", user_id)
        .execute()
    )
    return cast(list[dict[str, Any]], result.data)
