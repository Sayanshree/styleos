"""POST /feedback — record a signal and update Style DNA."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

import repository
from app.auth import CallerDep
from app.schemas import FeedbackRequest, FeedbackResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["feedback"])

# Learning rate: how much each feedback event shifts the attribute weights.
# Small and fixed so the system is stable and measurable.
LEARNING_RATE: float = 0.05

# Passive decay applied to weights for attributes absent from an accepted outfit.
# (This represents the "ignored" signal — applied at learning time rather than
# written as a row, per CLAUDE.md §5.)
DECAY_RATE: float = 0.01


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(payload: FeedbackRequest, caller: CallerDep) -> FeedbackResponse:
    """Append a feedback_event and return the updated Style DNA descriptors.

    Feedback is append-only — the row is never updated or deleted. The before/
    after learning comparison depends on the timeline of events.

    The Style DNA update is synchronous: weights are nudged immediately and
    descriptors are recomputed. The UI receives them in this response so it
    can show the style memory shifting in real time.
    """
    # 1. Append the event (validates ownership inside).
    try:
        repository.record_feedback(
            caller.user_id,
            outfit_id=payload.outfit_id,
            signal=payload.signal,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    # 2. Load the outfit's items to know which attributes to nudge.
    outfit_attributes = _get_outfit_attributes(caller.user_id, payload.outfit_id)

    # 3. Load current Style DNA.
    dna = repository.get_style_dna(caller.user_id)
    weights: dict = dict(dna.get("weights", {}))
    for key in ("style_tags", "fits", "formality", "colors"):
        weights.setdefault(key, {})

    # 4. Nudge weights.
    direction = 1.0 if payload.signal in ("accepted", "liked") else -1.0
    _nudge_weights(weights, outfit_attributes, direction * LEARNING_RATE)

    # 5. Recompute human-readable descriptors.
    descriptors = _compute_descriptors(weights)

    # 6. Persist.
    repository.update_style_dna(
        caller.user_id, weights=weights, descriptors=descriptors
    )

    return FeedbackResponse(descriptors=descriptors)


# ---------------------------------------------------------------------------
# Weight nudging
# ---------------------------------------------------------------------------


def _get_outfit_attributes(user_id: str, outfit_id) -> dict:
    """Extract the learnable attributes from an outfit's garments."""
    from repository.client import get_client
    from typing import cast

    # Fetch outfit items.
    items_result = (
        get_client()
        .table("outfit_item")
        .select("garment_id")
        .eq("outfit_id", str(outfit_id))
        .execute()
    )
    garment_ids = [row["garment_id"] for row in (items_result.data or [])]
    if not garment_ids:
        return {}

    # Fetch garment attributes.
    garments_result = (
        get_client()
        .table("garment")
        .select("formality, fit, style_tags, color_primary")
        .in_("id", garment_ids)
        .eq("user_id", user_id)
        .execute()
    )

    style_tags: list[str] = []
    fits: list[str] = []
    formalities: list[str] = []
    hue_buckets: list[str] = []

    for g in garments_result.data or []:
        style_tags.extend(g.get("style_tags") or [])
        if g.get("fit"):
            fits.append(g["fit"])
        if g.get("formality"):
            formalities.append(str(g["formality"]))
        color = g.get("color_primary") or {}
        h = color.get("h", 0)
        hue_buckets.append(_hue_bucket(h))

    return {
        "style_tags": style_tags,
        "fits": fits,
        "formality": formalities,
        "colors": hue_buckets,
    }


def _hue_bucket(hue: int) -> str:
    """Map a hue (0–360) to a broad colour family for weight tracking."""
    buckets = [
        (15, "red"), (45, "orange"), (75, "yellow"), (150, "green"),
        (195, "cyan"), (255, "blue"), (285, "indigo"), (330, "purple"),
        (360, "red"),
    ]
    for limit, name in buckets:
        if hue < limit:
            return name
    return "red"


def _nudge_weights(weights: dict, attributes: dict, delta: float) -> None:
    """Apply delta to weights for all attributes present in the outfit."""
    for key in ("style_tags", "fits", "formality", "colors"):
        bucket = weights.setdefault(key, {})
        for attr in attributes.get(key, []):
            current = float(bucket.get(attr, 0.0))
            bucket[attr] = round(max(-1.0, min(1.0, current + delta)), 4)

    # Passive decay on weights for attributes NOT in this outfit.
    for key in ("style_tags", "fits", "formality", "colors"):
        present = set(attributes.get(key, []))
        bucket = weights[key]
        for attr in list(bucket):
            if attr not in present:
                current = float(bucket[attr])
                bucket[attr] = round(current * (1 - DECAY_RATE), 4)


def _compute_descriptors(weights: dict) -> list[str]:
    """Derive human-readable style descriptors from the current weights."""
    descriptors: list[str] = []

    # Top style tags (weight > 0.1).
    tag_weights: dict[str, float] = weights.get("style_tags", {})
    top_tags = sorted(
        ((t, w) for t, w in tag_weights.items() if w > 0.1),
        key=lambda x: x[1],
        reverse=True,
    )[:3]
    descriptors.extend(t for t, _ in top_tags)

    # Dominant formality band.
    formality_weights: dict[str, float] = weights.get("formality", {})
    if formality_weights:
        top_form = max(formality_weights, key=lambda k: formality_weights[k])
        form_label = {
            "1": "casual", "2": "casual", "3": "smart casual",
            "4": "dressy", "5": "formal",
        }.get(top_form)
        if form_label and form_label not in descriptors:
            descriptors.append(form_label)

    # Dominant colour.
    color_weights: dict[str, float] = weights.get("colors", {})
    if color_weights:
        top_color = max(color_weights, key=lambda k: color_weights[k])
        if color_weights[top_color] > 0.1 and top_color not in descriptors:
            descriptors.append(top_color)

    return descriptors[:5]
