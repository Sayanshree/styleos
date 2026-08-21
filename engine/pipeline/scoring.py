"""Step 3: Multi-factor scoring.

Computes a weighted score for each candidate outfit. No `seasonFit` factor —
weather feel from the quiz drives `weatherFit` instead (v1 has no weather API).

Formula (CLAUDE.md "Scoring weights"):

    score = w_color   * colorHarmony
          + w_formal  * formalityCoherence
          + w_occasion* occasionFit
          + w_weather * weatherFit
          + w_body    * bodyCompatibility
          + w_pref    * personalization

All factors are normalized to [0, 1]. Weights are constants — documented here
and easy to tune without a deploy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from adapters.llm import ResolvedIntent
from pipeline.candidates import CandidateItem, CandidateOutfit

# ---------------------------------------------------------------------------
# Weights — bodyCompatibility and personalization are deliberately lower so
# the system stays practical and doesn't over-personalize into repetition.
# ---------------------------------------------------------------------------
W_COLOR = 0.25
W_FORMAL = 0.20
W_OCCASION = 0.20
W_WEATHER = 0.15
W_BODY = 0.10
W_PREF = 0.10

assert abs(W_COLOR + W_FORMAL + W_OCCASION + W_WEATHER + W_BODY + W_PREF - 1.0) < 1e-9


@dataclass
class ScoredCandidate:
    """A candidate with its computed score and per-factor breakdown."""

    candidate: CandidateOutfit
    score: float
    factor_scores: dict[str, float]  # for fallback-reason generation


# ---------------------------------------------------------------------------
# colorHarmony
# ---------------------------------------------------------------------------

def _hue_dist(h1: int, h2: int) -> float:
    """Shortest angular distance between two hues (0–180)."""
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)


def _color_harmony(items: list[CandidateItem]) -> float:
    """Reward complementary (~180°), analogous (~30°), or neutral pairings.

    Neutrals (s < 15) are harmonious with everything. A monochromatic palette
    (hue distance < 20°) also scores well. Clashing hues (60–120°) are penalized.
    """
    colors = [i.color_primary for i in items if i.color_primary]
    if len(colors) < 2:
        return 0.8  # single item — neutral score

    total = 0.0
    pairs = 0
    for i in range(len(colors)):
        for j in range(i + 1, len(colors)):
            s1, s2 = colors[i].get("s", 0), colors[j].get("s", 0)
            # Neutrals (low saturation) pair with anything.
            if s1 < 15 or s2 < 15:
                total += 0.9
            else:
                dist = _hue_dist(colors[i].get("h", 0), colors[j].get("h", 0))
                if dist < 20:       # monochromatic
                    total += 1.0
                elif dist < 50:     # analogous
                    total += 0.85
                elif 150 < dist <= 180:  # complementary
                    total += 0.90
                elif 80 < dist <= 150:   # clash zone
                    total += 0.30
                else:
                    total += 0.60
            pairs += 1

    return total / pairs if pairs else 0.8


# ---------------------------------------------------------------------------
# formalityCoherence
# ---------------------------------------------------------------------------

def _formality_coherence(items: list[CandidateItem], intent: ResolvedIntent) -> float:
    """Reward items with consistent dressiness close to the target range.

    Penalizes wide spread (e.g. a 1 next to a 5) and items outside the target.
    """
    formalities = [i.formality for i in items]
    if not formalities:
        return 0.5

    # Penalty for spread within the outfit.
    spread = max(formalities) - min(formalities)
    spread_penalty = spread / 4.0  # 0 = perfect, 1 = max spread

    # Penalty for being outside the target range.
    target_mid = (intent.dressiness_min + intent.dressiness_max) / 2.0
    avg = sum(formalities) / len(formalities)
    distance_to_target = abs(avg - target_mid) / 4.0

    score = 1.0 - 0.5 * spread_penalty - 0.5 * distance_to_target
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# occasionFit
# ---------------------------------------------------------------------------

def _occasion_fit(items: list[CandidateItem], intent: ResolvedIntent) -> float:
    """Overlap between item occasion_tags and the target occasion_tags."""
    if not intent.occasion_tags:
        return 0.7  # no target — neutral

    target = set(intent.occasion_tags)
    total = 0.0
    counted = 0
    for item in items:
        item_tags = set(item.occasion_tags)
        if not item_tags:
            total += 0.5  # untagged item — neutral
        else:
            overlap = len(item_tags & target) / len(item_tags | target)
            total += overlap
        counted += 1

    return total / counted if counted else 0.5


# ---------------------------------------------------------------------------
# weatherFit (driven by quiz.coverage — no weather API in v1)
# ---------------------------------------------------------------------------

# Material warmth buckets (lightweight → heavyweight)
_LIGHT_MATERIALS = {"chiffon", "silk", "satin", "linen", "cotton", "organza", "georgette"}
_HEAVY_MATERIALS = {"wool", "leather", "velvet", "denim", "corduroy", "tweed", "fleece"}

# Sleeve warmth
_WARM_SLEEVES = {"long", "full sleeve", "full-sleeve", "long-sleeve"}
_COOL_SLEEVES = {"sleeveless", "spaghetti strap", "off-shoulder", "strapless"}


def _weather_fit(items: list[CandidateItem], coverage_preference: str | None) -> float:
    """Match outfit heaviness to the user's stated coverage preference.

    light    → reward cool/airy garments; penalize heavy layers
    layered  → reward outerwear, warm materials, long sleeves
    balanced / None → neutral 0.7
    """
    if not coverage_preference or coverage_preference in ("balanced", "any"):
        return 0.7

    score = 0.7
    for item in items:
        mat = (item.material or "").lower()
        sleeve = (item.sleeve or "").lower()

        is_light_mat = mat in _LIGHT_MATERIALS
        is_heavy_mat = mat in _HEAVY_MATERIALS
        is_warm_sleeve = sleeve in _WARM_SLEEVES
        is_cool_sleeve = sleeve in _COOL_SLEEVES
        is_outerwear = item.category == "outerwear"

        if coverage_preference == "light":
            if is_heavy_mat or is_outerwear:
                score -= 0.15
            if is_light_mat or is_cool_sleeve:
                score += 0.08
        elif coverage_preference == "layered":
            if is_light_mat and not is_outerwear:
                score -= 0.10
            if is_heavy_mat or is_warm_sleeve or is_outerwear:
                score += 0.10

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# bodyCompatibility
# ---------------------------------------------------------------------------

_FIT_COMPAT: dict[str, set[str]] = {
    "fitted": {"fitted", "slim", "skinny", "bodycon"},
    "relaxed": {"relaxed", "loose", "regular", "straight"},
    "oversized": {"oversized", "boxy", "loose", "relaxed"},
    "a-line": {"a-line", "flared", "flowy"},
}


def _body_compatibility(items: list[CandidateItem], fit_preference: str | None) -> float:
    """Soft nudge toward the user's fit preference (quiz > profile).

    This is a soft scoring aid, not a hard filter.
    """
    if not fit_preference or fit_preference == "any":
        return 0.7

    preferred = _FIT_COMPAT.get(fit_preference.lower(), {fit_preference.lower()})
    total = 0.0
    counted = 0
    for item in items:
        item_fit = (item.fit or "").lower()
        if not item_fit:
            total += 0.6  # unknown — slightly below neutral
        elif item_fit in preferred:
            total += 1.0
        else:
            total += 0.3
        counted += 1

    return total / counted if counted else 0.7


# ---------------------------------------------------------------------------
# personalization (Style DNA)
# ---------------------------------------------------------------------------

def _personalization(items: list[CandidateItem], dna_weights: dict[str, Any]) -> float:
    """Dot product of item attributes with the user's learned preference weights."""
    if not dna_weights:
        return 0.5

    style_weights: dict[str, float] = dna_weights.get("style_tags", {})
    fit_weights: dict[str, float] = dna_weights.get("fits", {})
    formality_weights: dict[str, float] = dna_weights.get("formality", {})

    total = 0.0
    counted = 0
    for item in items:
        item_score = 0.5  # baseline
        # Style tags contribution
        for tag in item.style_tags:
            if tag in style_weights:
                item_score += style_weights[tag] * 0.2
        # Fit contribution
        fit = item.fit or ""
        if fit in fit_weights:
            item_score += fit_weights[fit] * 0.2
        # Formality contribution
        form_key = str(item.formality)
        if form_key in formality_weights:
            item_score += formality_weights[form_key] * 0.1

        total += max(0.0, min(1.0, item_score))
        counted += 1

    return total / counted if counted else 0.5


# ---------------------------------------------------------------------------
# Main scoring entry point
# ---------------------------------------------------------------------------

def score_candidates(
    candidates: list[CandidateOutfit],
    intent: ResolvedIntent,
    body_profile: dict[str, Any] | None,
    style_dna: dict[str, Any],
) -> list[ScoredCandidate]:
    """Score every candidate and return a list sorted best-first."""
    # Quiz fit/coverage already incorporated into intent by the intent extractor.
    fit_pref = intent.fit_preference
    coverage_pref = intent.coverage_preference
    dna_weights = style_dna.get("weights", {})

    scored: list[ScoredCandidate] = []
    for candidate in candidates:
        items = candidate.items

        f_color = _color_harmony(items)
        f_formal = _formality_coherence(items, intent)
        f_occasion = _occasion_fit(items, intent)
        f_weather = _weather_fit(items, coverage_pref)
        f_body = _body_compatibility(items, fit_pref)
        f_pref = _personalization(items, dna_weights)

        total = (
            W_COLOR * f_color
            + W_FORMAL * f_formal
            + W_OCCASION * f_occasion
            + W_WEATHER * f_weather
            + W_BODY * f_body
            + W_PREF * f_pref
        )

        scored.append(
            ScoredCandidate(
                candidate=candidate,
                score=round(total, 4),
                factor_scores={
                    "colorHarmony": round(f_color, 3),
                    "formalityCoherence": round(f_formal, 3),
                    "occasionFit": round(f_occasion, 3),
                    "weatherFit": round(f_weather, 3),
                    "bodyCompatibility": round(f_body, 3),
                    "personalization": round(f_pref, 3),
                },
            )
        )

    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def templated_reasons(scored: ScoredCandidate, intent: ResolvedIntent) -> list[str]:
    """Generate mechanical reasons from the per-factor breakdown.

    Used when LLM call #2 fails and we need to degrade gracefully.
    """
    factors = scored.factor_scores
    reasons: list[str] = []

    if factors["colorHarmony"] >= 0.8:
        reasons.append("The colours work well together — a harmonious palette for the occasion.")
    elif factors["colorHarmony"] < 0.5:
        reasons.append("The colours are a bold contrast — a statement look for the occasion.")

    if factors["formalityCoherence"] >= 0.8:
        reasons.append(f"Everything is consistently dressed for a {intent.resolved_occasion}.")

    if factors["occasionFit"] >= 0.75:
        reasons.append(f"Well suited to a {intent.resolved_occasion} based on how each piece is tagged.")

    if factors["weatherFit"] >= 0.8:
        reasons.append("The outfit matches the coverage you asked for.")
    elif factors["weatherFit"] < 0.45:
        reasons.append("Note: one or more pieces may feel heavier or lighter than your coverage preference.")

    if not reasons:
        reasons.append(f"A solid match for a {intent.resolved_occasion}.")

    return reasons[:3]
