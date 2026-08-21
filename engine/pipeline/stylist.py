"""Steps 6–7: LLM stylist selection + engine modification application.

Step 6 (LLM call #2):
    Passes the diverse candidate slate to the LLM. The LLM selects up to 6,
    writes natural-language reasons, and may request a bounded modification
    (role swap + preference string) for each outfit. It cannot name garments;
    the engine resolves the swap from the actual wardrobe.

Step 7 (engine applies modifications):
    For each modification request the engine searches the wardrobe for a
    garment matching the role and preference. If found and valid, it swaps the
    garment and rescores. If not found, the original outfit is kept unchanged.
    The LLM never learns whether its modification was fulfilled.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from adapters.base import AdapterError, AdapterTimeout
from adapters.llm import (
    LLMStylistAdapter,
    ModificationRequest,
    ResolvedIntent,
    RankedOutfit,
    StylistRequest,
    StylistVerdict,
)
from pipeline.candidates import CandidateItem, CandidateOutfit
from pipeline.scoring import ScoredCandidate, score_candidates, templated_reasons
from repository.queries import OutfitInsert

logger = logging.getLogger(__name__)

_stylist = LLMStylistAdapter()


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _candidate_to_dict(sc: ScoredCandidate) -> dict[str, Any]:
    """Serialize a ScoredCandidate for the LLM prompt."""
    return {
        "index": sc.candidate.index,
        "score": sc.score,
        "items": [
            {
                "garment_id": item.garment_id,
                "role": item.role,
                "category": item.category,
                "subcategory": item.subcategory,
                "garment_type": item.garment_type,
                "fit": item.fit,
                "formality": item.formality,
                "style_tags": item.style_tags,
                "occasion_tags": item.occasion_tags,
                "color_primary": item.color_primary,
                "material": item.material,
            }
            for item in sc.candidate.items
        ],
    }


# ---------------------------------------------------------------------------
# Step 6: Call the LLM stylist
# ---------------------------------------------------------------------------


async def call_stylist(
    diverse: list[ScoredCandidate],
    intent: ResolvedIntent,
    style_descriptors: list[str],
) -> tuple[StylistVerdict, bool]:
    """Return (verdict, degraded).

    On failure: returns a deterministic top-6 verdict with templated reasons.
    `degraded=True` is forwarded to the response so it can be logged.
    """
    candidates_for_llm = [_candidate_to_dict(sc) for sc in diverse]
    request = StylistRequest(
        intent=intent,
        style_descriptors=style_descriptors,
        candidates=candidates_for_llm,
    )

    try:
        verdict = await _stylist.select(request)
        return verdict, False
    except (AdapterError, AdapterTimeout) as exc:
        logger.warning("stylist call failed, using fallback: %s", exc)

    # Fallback: deterministic top 6 with templated reasons.
    fallback_outfits: list[RankedOutfit] = []
    for rank, sc in enumerate(diverse[:6], start=1):
        fallback_outfits.append(
            RankedOutfit(
                candidate_index=sc.candidate.index,
                rank=rank,
                reasons=templated_reasons(sc, intent),
                modification=None,
            )
        )
    return StylistVerdict(outfits=fallback_outfits, degraded=True), True


# ---------------------------------------------------------------------------
# Step 7: Engine applies modifications
# ---------------------------------------------------------------------------


def _preference_match(garment: dict[str, Any], preference: str) -> float:
    """Simple keyword match between a free-text preference and garment attributes.

    Returns 0–1. No NLP — just checks whether key words from the preference
    appear in the garment's fields.
    """
    pref_words = set(preference.lower().split())
    garment_text = " ".join(
        str(v).lower()
        for k, v in garment.items()
        if k in ("subcategory", "garment_type", "fit", "material", "style_tags", "occasion_tags", "color_primary")
        and v
    )
    matches = sum(1 for w in pref_words if w in garment_text)
    return matches / max(len(pref_words), 1)


def _try_modification(
    outfit_items: list[CandidateItem],
    mod: ModificationRequest,
    all_garments: list[dict[str, Any]],
    intent: ResolvedIntent,
) -> list[CandidateItem] | None:
    """Attempt to fulfill a modification request.

    Returns the modified item list, or None if no suitable replacement was
    found or the replacement did not improve the outfit.
    """
    from pipeline.candidates import _ROLE_CATEGORIES, _make_item
    from pipeline.scoring import _color_harmony, _formality_coherence, W_COLOR, W_FORMAL

    # Find which role categories match this request's role.
    role_cats = _ROLE_CATEGORIES.get(mod.role, [])
    candidates = [
        g for g in all_garments
        if g.get("category") in role_cats
        # Don't suggest a garment already in the outfit.
        and str(g["id"]) not in {i.garment_id for i in outfit_items}
    ]

    if not candidates:
        logger.debug("no candidates for modification role=%s", mod.role)
        return None

    # Rank by preference match.
    ranked = sorted(candidates, key=lambda g: _preference_match(g, mod.preference), reverse=True)
    best = ranked[0]

    # Check that preference match is meaningful (> 0).
    if _preference_match(best, mod.preference) == 0:
        return None

    new_items = [i for i in outfit_items if i.role != mod.role]
    new_items.append(_make_item(best, mod.role))

    # Quick sanity check: new outfit must not be dramatically worse on key factors.
    old_color = _color_harmony(outfit_items)
    new_color = _color_harmony(new_items)
    old_form = _formality_coherence(outfit_items, intent)
    new_form = _formality_coherence(new_items, intent)
    old_key = W_COLOR * old_color + W_FORMAL * old_form
    new_key = W_COLOR * new_color + W_FORMAL * new_form

    if new_key < old_key - 0.15:
        logger.debug("modification rejected: key score dropped %.3f → %.3f", old_key, new_key)
        return None

    return new_items


# ---------------------------------------------------------------------------
# Build final OutfitInsert list
# ---------------------------------------------------------------------------


def build_outfit_inserts(
    verdict: StylistVerdict,
    diverse: list[ScoredCandidate],
    all_garments: list[dict[str, Any]],
    intent: ResolvedIntent,
) -> list[OutfitInsert]:
    """Combine LLM selections with modification application to produce final outfits.

    Returns up to 6 OutfitInsert objects, one per rank. Always at least 1.
    """
    index_to_scored: dict[int, ScoredCandidate] = {
        sc.candidate.index: sc for sc in diverse
    }

    inserts: list[OutfitInsert] = []
    seen_indices: set[int] = set()

    for ranked_outfit in sorted(verdict.outfits, key=lambda o: o.rank)[:6]:
        idx = ranked_outfit.candidate_index
        if idx in seen_indices:
            continue
        sc = index_to_scored.get(idx)
        if sc is None:
            continue
        seen_indices.add(idx)

        items = list(sc.candidate.items)

        # Attempt modification if requested.
        if ranked_outfit.modification:
            modified = _try_modification(items, ranked_outfit.modification, all_garments, intent)
            if modified:
                items = modified
                logger.debug(
                    "applied modification: role=%s pref=%s",
                    ranked_outfit.modification.role,
                    ranked_outfit.modification.preference,
                )

        inserts.append(
            OutfitInsert(
                rank=len(inserts) + 1,  # re-rank sequentially after filtering
                score=sc.score,
                reasons=ranked_outfit.reasons,
                items=[{"garment_id": i.garment_id, "role": i.role} for i in items],
            )
        )

    return inserts
