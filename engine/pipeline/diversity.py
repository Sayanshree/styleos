"""Step 5: MMR diversity pass.

Maximal Marginal Relevance selects a diverse shortlist from the top-N scored
candidates. Without it the LLM stylist would see 15 outfits that are almost
identical (same top, different shoes) and could only select slight variations.

The MMR formula balances relevance (score) against similarity to already-
selected candidates:

    MMR_i = λ * score_i - (1 - λ) * max_j similarity(i, j)

λ controls the relevance–diversity trade-off. At 0.6 the top candidates win
unless they are very similar to something already selected.
"""

from __future__ import annotations

from pipeline.candidates import CandidateItem
from pipeline.scoring import ScoredCandidate

LAMBDA: float = 0.6  # relevance weight; 1 - LAMBDA = diversity weight


def _item_similarity(a: CandidateItem, b: CandidateItem) -> float:
    """Jaccard similarity over garment attributes used as outfit fingerprints."""
    # Same garment ID → maximum similarity.
    if a.garment_id == b.garment_id:
        return 1.0

    a_attrs: set[str] = {a.category, a.fit or "", a.material or ""}
    b_attrs: set[str] = {b.category, b.fit or "", b.material or ""}
    if a_attrs == b_attrs:
        return 0.9

    union = a_attrs | b_attrs
    intersection = a_attrs & b_attrs
    return len(intersection) / len(union) if union else 0.0


def _outfit_similarity(a: ScoredCandidate, b: ScoredCandidate) -> float:
    """Average pairwise item similarity, weighted toward shared roles."""
    a_by_role = {i.role: i for i in a.candidate.items}
    b_by_role = {i.role: i for i in b.candidate.items}

    shared_roles = set(a_by_role) & set(b_by_role)
    if not shared_roles:
        return 0.0

    total = sum(
        _item_similarity(a_by_role[role], b_by_role[role])
        for role in shared_roles
    )
    return total / len(shared_roles)


def apply_mmr(
    scored: list[ScoredCandidate],
    target: int = 18,
) -> list[ScoredCandidate]:
    """Select up to `target` diverse candidates from the scored list.

    Scores are already normalized to [0, 1] by the scoring module, so the MMR
    formula runs directly without re-normalizing.
    """
    if not scored:
        return []

    if len(scored) <= target:
        return scored

    selected: list[ScoredCandidate] = []
    remaining = list(scored)

    # Always include the top-scored candidate.
    selected.append(remaining.pop(0))

    while remaining and len(selected) < target:
        best_mmr = -1.0
        best_idx = 0

        for i, candidate in enumerate(remaining):
            max_sim = max(
                _outfit_similarity(candidate, s) for s in selected
            )
            mmr = LAMBDA * candidate.score - (1 - LAMBDA) * max_sim

            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i

        selected.append(remaining.pop(best_idx))

    return selected
