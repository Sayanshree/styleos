"""Step 2: Candidate outfit generation.

Builds valid outfit combinations from the user's wardrobe and the resolved
intent. Prunes hard before scoring to keep the candidate set manageable.
"""

from __future__ import annotations

import itertools
import logging
import random
from dataclasses import dataclass, field
from typing import Any

from adapters.llm import ResolvedIntent

logger = logging.getLogger(__name__)

# Maximum combinations to score. Beyond this we sample to avoid O(n^4) blowup
# on large wardrobes.
MAX_CANDIDATES: int = 200

# Category → outfit role mapping (mirrors docs/03-recommendation-engine.md).
_ROLE_CATEGORIES: dict[str, list[str]] = {
    "top": ["tops", "activewear"],
    "bottom": ["bottoms"],
    "one-piece": ["one-piece"],
    "outerwear": ["outerwear"],
    "shoes": ["shoes"],
    "accessory": ["accessories", "bags", "traditional-accessories"],
    "ethnic-set": ["indian-ethnic", "fusion-indo-western", "sets-coords"],
}


@dataclass
class CandidateItem:
    """One garment filling one role inside a candidate outfit."""

    garment_id: str
    role: str
    category: str
    subcategory: str | None
    color_primary: dict[str, int]   # {h, s, l}
    material: str | None
    fit: str | None
    sleeve: str | None
    formality: int
    style_tags: list[str]
    occasion_tags: list[str]
    garment_type: str | None = None
    length: str | None = None


@dataclass
class CandidateOutfit:
    """A valid combination of garments, not yet scored."""

    items: list[CandidateItem]
    index: int = 0  # assigned after generation


def _make_item(row: dict[str, Any], role: str) -> CandidateItem:
    color = row.get("color_primary") or {"h": 0, "s": 0, "l": 50}
    return CandidateItem(
        garment_id=str(row["id"]),
        role=role,
        category=row["category"],
        subcategory=row.get("subcategory"),
        color_primary=color if isinstance(color, dict) else {"h": 0, "s": 0, "l": 50},
        material=row.get("material"),
        fit=row.get("fit"),
        sleeve=row.get("sleeve"),
        formality=int(row.get("formality", 3)),
        style_tags=list(row.get("style_tags") or []),
        occasion_tags=list(row.get("occasion_tags") or []),
        garment_type=row.get("garment_type"),
        length=row.get("length"),
    )


def _hard_pass(garment: dict[str, Any], intent: ResolvedIntent) -> bool:
    """Return True if the garment passes hard constraints.

    Filters out garments that definitively cannot be part of a valid outfit:
    - Formality too far outside the target range (± 1 tolerance).
    - No occasion overlap at all when occasion_tags are set.
    """
    formality = int(garment.get("formality", 3))
    if formality < intent.dressiness_min - 1 or formality > intent.dressiness_max + 1:
        return False

    if intent.occasion_tags:
        garment_occ = set(garment.get("occasion_tags") or [])
        if garment_occ and not garment_occ.intersection(set(intent.occasion_tags)):
            return False

    return True


def generate_candidates(
    garments: list[dict[str, Any]],
    intent: ResolvedIntent,
) -> list[CandidateOutfit]:
    """Build and prune candidate outfits from the wardrobe.

    Two outfit shapes are supported:
    - (top + bottom) + optional shoes + optional outerwear
    - (one-piece OR ethnic-set) + optional shoes + optional outerwear

    Accessories are addable but optional and are skipped in the base
    combinatorics to keep the space manageable.
    """
    # Bucket garments by role after hard-filtering.
    role_buckets: dict[str, list[dict[str, Any]]] = {role: [] for role in _ROLE_CATEGORIES}
    for g in garments:
        cat = g.get("category", "")
        for role, cats in _ROLE_CATEGORIES.items():
            if cat in cats:
                if _hard_pass(g, intent):
                    role_buckets[role].append(g)

    candidates: list[CandidateOutfit] = []

    # Shape A: top + bottom
    tops = role_buckets["top"]
    bottoms = role_buckets["bottom"]
    shoes = role_buckets["shoes"]
    outerwear = role_buckets["outerwear"]

    if tops and bottoms:
        pairs = list(itertools.product(tops, bottoms))
        if len(pairs) > MAX_CANDIDATES:
            pairs = random.sample(pairs, MAX_CANDIDATES)
        for top, bottom in pairs:
            items: list[CandidateItem] = [
                _make_item(top, "top"),
                _make_item(bottom, "bottom"),
            ]
            if shoes:
                items.append(_make_item(shoes[0], "shoes"))  # best shoe added later in scoring
            candidates.append(CandidateOutfit(items=items))

    # Shape B: one-piece
    for piece in role_buckets["one-piece"]:
        items = [_make_item(piece, "one-piece")]
        if shoes:
            items.append(_make_item(shoes[0], "shoes"))
        candidates.append(CandidateOutfit(items=items))

    # Shape C: ethnic-set
    for piece in role_buckets["ethnic-set"]:
        items = [_make_item(piece, "ethnic-set")]
        if shoes:
            items.append(_make_item(shoes[0], "shoes"))
        candidates.append(CandidateOutfit(items=items))

    # For top+bottom outfits: also try different shoe options (up to 3).
    if shoes and len(shoes) > 1:
        augmented: list[CandidateOutfit] = []
        for candidate in candidates:
            has_top = any(i.role == "top" for i in candidate.items)
            if not has_top:
                augmented.append(candidate)
                continue
            base_items = [i for i in candidate.items if i.role != "shoes"]
            for shoe in shoes[:3]:
                augmented.append(CandidateOutfit(items=base_items + [_make_item(shoe, "shoes")]))
        candidates = augmented

    # Cap total before scoring.
    if len(candidates) > MAX_CANDIDATES:
        candidates = random.sample(candidates, MAX_CANDIDATES)

    # Assign indices.
    for i, c in enumerate(candidates):
        c.index = i

    logger.debug("generated %d candidates from %d garments", len(candidates), len(garments))
    return candidates
