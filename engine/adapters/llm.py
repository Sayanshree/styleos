"""Typed adapters for the two LLM calls per recommendation.

Call #1 — Intent extraction:
    Parses occasion + free_text + quiz answers into a structured intent object.
    On failure the pipeline uses the raw quiz values directly; the recommendation
    still proceeds.

Call #2 — Bounded stylist:
    Receives the top ~15–20 scored candidates and returns structured JSON:
    reranked top 6, per-item reasons, optional bounded modification requests.
    The LLM cannot name garments the user does not own. It can only request a
    role swap ({role, preference}) — the engine resolves that against the actual
    wardrobe (see engine/pipeline/stylist.py).

Both sit on the critical path of the one moment the product exists to deliver.
They must fail soft: callers catch AdapterError / AdapterTimeout and degrade
rather than 500-ing.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from google import genai
from google.genai import types

from adapters.base import AdapterError, AdapterTimeout, RetryPolicy
from app.config import settings

logger = logging.getLogger(__name__)

MODEL: Final[str] = "gemini-2.5-flash"

DEFAULT_INTENT_RETRY: Final[RetryPolicy] = RetryPolicy(
    timeout_s=6.0,
    max_attempts=2,
    backoff_s=0.5,
)
"""Intent extraction is fast text-only — two attempts within the 15 s budget."""

DEFAULT_STYLIST_RETRY: Final[RetryPolicy] = RetryPolicy(
    timeout_s=10.0,
    max_attempts=2,
    backoff_s=1.0,
)
"""Two attempts, not more.

A third retry costs more than the fallback is worth: templated reasons in 12 s
beat LLM prose in 30.
"""


# ---------------------------------------------------------------------------
# Shared Gemini client (module-level, thread-safe after first access)
# ---------------------------------------------------------------------------

def _gemini_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


async def _generate_json(
    prompt: str,
    retry: RetryPolicy,
) -> dict[str, Any]:
    """Call Gemini with a JSON-mode prompt; retry on transient errors."""
    client = _gemini_client()
    last_exc: Exception | None = None

    for attempt in range(retry.max_attempts):
        try:
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.models.generate_content(
                        model=MODEL,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.3,
                        ),
                    ),
                ),
                timeout=retry.timeout_s,
            )
            text = response.text or ""
            return json.loads(text)
        except asyncio.TimeoutError as exc:
            last_exc = exc
            logger.warning("LLM timeout on attempt %d", attempt + 1)
        except json.JSONDecodeError as exc:
            last_exc = exc
            logger.warning("LLM returned non-JSON on attempt %d: %s", attempt + 1, exc)
        except Exception as exc:
            last_exc = exc
            logger.warning("LLM error on attempt %d: %s", attempt + 1, exc)

        if attempt < retry.max_attempts - 1:
            await asyncio.sleep(retry.backoff_s)

    if isinstance(last_exc, asyncio.TimeoutError):
        raise AdapterTimeout("LLM timed out after all attempts") from last_exc
    raise AdapterError(f"LLM failed after all attempts: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# Call #1: Intent extraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedIntent:
    """Structured output of the intent extraction call.

    This is the single source of truth about what the user wants for this
    request. All downstream pipeline stages read from it.
    """

    resolved_occasion: str
    dressiness_min: int          # 1–5
    dressiness_max: int          # 1–5
    style_vibe: list[str]        # from the approved aesthetic tag set
    fit_preference: str | None   # quiz overrides profile; None = no preference
    coverage_preference: str | None  # drives weatherFit scoring
    occasion_tags: list[str]     # for occasionFit overlap scoring
    special_notes: str | None = None


def _intent_prompt(
    occasion: str,
    free_text: str | None,
    quiz: dict[str, Any],
    body_profile: dict[str, Any] | None,
    style_descriptors: list[str],
) -> str:
    quiz_line = json.dumps(quiz) if quiz else "{}"
    profile_fit = (body_profile or {}).get("preferred_fit", "none")
    profile_coverage = (body_profile or {}).get("preferred_coverage", "none")
    descriptors_line = ", ".join(style_descriptors) if style_descriptors else "none"

    return f"""You are a fashion intent parser. Extract structured intent from a styling request.

OCCASION: {occasion}
FREE TEXT: {free_text or "(none)"}
QUIZ ANSWERS: {quiz_line}
PERSISTENT PROFILE FIT: {profile_fit}  (the quiz overrides this if set)
PERSISTENT PROFILE COVERAGE: {profile_coverage}  (the quiz overrides this if set)
STYLE MEMORY DESCRIPTORS: {descriptors_line}

RULES:
- Quiz answers override profile values. Always.
- dressiness_min and dressiness_max are integers 1–5 (1=casual, 5=formal).
- style_vibe should contain 1–3 words from: elegant, feminine, romantic, sophisticated, minimal, casual, streetwear, sporty, athleisure, bohemian, classic, chic, glamorous, edgy, relaxed, vintage, festive, ethnic.
- fit_preference: use the quiz value if set, else the profile value, else null.
- coverage_preference: use the quiz coverage value if set, else the profile value, else null.
- occasion_tags: pick relevant tags from [work, date, party, casual, event, outdoor, sport, formal, wedding, festive, ethnic].

Return valid JSON matching this exact schema:
{{
  "resolved_occasion": "string",
  "dressiness_min": integer,
  "dressiness_max": integer,
  "style_vibe": ["string"],
  "fit_preference": "string or null",
  "coverage_preference": "string or null",
  "occasion_tags": ["string"],
  "special_notes": "string or null"
}}"""


class IntentAdapter(Protocol):
    async def extract(
        self,
        occasion: str,
        free_text: str | None,
        quiz: dict[str, Any],
        body_profile: dict[str, Any] | None,
        style_descriptors: list[str],
    ) -> ResolvedIntent: ...


class LLMIntentAdapter:
    """Calls Gemini to extract structured intent from the raw request."""

    def __init__(self, retry: RetryPolicy = DEFAULT_INTENT_RETRY) -> None:
        self.retry = retry

    async def extract(
        self,
        occasion: str,
        free_text: str | None,
        quiz: dict[str, Any],
        body_profile: dict[str, Any] | None,
        style_descriptors: list[str],
    ) -> ResolvedIntent:
        prompt = _intent_prompt(occasion, free_text, quiz, body_profile, style_descriptors)
        data = await _generate_json(prompt, self.retry)

        return ResolvedIntent(
            resolved_occasion=str(data.get("resolved_occasion", occasion)),
            dressiness_min=int(data.get("dressiness_min", 1)),
            dressiness_max=int(data.get("dressiness_max", 5)),
            style_vibe=list(data.get("style_vibe", [])),
            fit_preference=data.get("fit_preference") or None,
            coverage_preference=data.get("coverage_preference") or None,
            occasion_tags=list(data.get("occasion_tags", [occasion.lower()])),
            special_notes=data.get("special_notes") or None,
        )


def fallback_intent(
    occasion: str,
    quiz: dict[str, Any],
    body_profile: dict[str, Any] | None,
) -> ResolvedIntent:
    """Build a best-effort intent without an LLM call.

    Used when call #1 fails. Values come directly from the quiz and profile.
    """
    _OCCASION_DRESSINESS: dict[str, tuple[int, int]] = {
        "work": (3, 4),
        "date": (3, 4),
        "party": (3, 5),
        "casual": (1, 3),
        "event": (4, 5),
        "formal": (5, 5),
        "wedding": (4, 5),
        "outdoor": (1, 3),
        "sport": (1, 2),
        "festive": (3, 5),
        "ethnic": (3, 5),
    }
    key = occasion.lower().split()[0]
    dmin, dmax = _OCCASION_DRESSINESS.get(key, (1, 5))

    profile = body_profile or {}
    return ResolvedIntent(
        resolved_occasion=occasion,
        dressiness_min=dmin,
        dressiness_max=dmax,
        style_vibe=[],
        fit_preference=quiz.get("fit_tonight") or profile.get("preferred_fit") or None,
        coverage_preference=quiz.get("coverage") or profile.get("preferred_coverage") or None,
        occasion_tags=[key],
    )


# ---------------------------------------------------------------------------
# Call #2: Bounded stylist
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModificationRequest:
    """A bounded request from the stylist to swap one garment role."""

    role: str             # the outfit role to replace (e.g. "shoes")
    preference: str       # natural-language description (e.g. "neutral heels")


@dataclass
class RankedOutfit:
    """One outfit selected and explained by the stylist."""

    candidate_index: int       # index into the candidates list
    rank: int                  # 1–6
    reasons: list[str]
    modification: ModificationRequest | None = None


@dataclass(frozen=True)
class StylistVerdict:
    """Parsed output of the stylist call."""

    outfits: list[RankedOutfit]
    degraded: bool = False


@dataclass(frozen=True)
class StylistRequest:
    """What the stylist receives: the scored shortlist and the user's context."""

    intent: ResolvedIntent
    style_descriptors: list[str]
    candidates: list[dict[str, Any]]   # each: {index, score, items: [{garment_id, role, ...}]}


def _stylist_prompt(request: StylistRequest) -> str:
    intent = request.intent
    candidate_json = json.dumps(
        [
            {
                "index": c["index"],
                "score": round(c["score"], 3),
                "items": [
                    {
                        "role": i["role"],
                        "category": i.get("category", ""),
                        "subcategory": i.get("subcategory", ""),
                        "fit": i.get("fit", ""),
                        "formality": i.get("formality", ""),
                        "style_tags": i.get("style_tags", []),
                        "color_hsl": i.get("color_primary", {}),
                    }
                    for i in c["items"]
                ],
            }
            for c in request.candidates
        ],
        indent=2,
    )

    return f"""You are a personal stylist. Select and explain the best outfits from a scored candidate list.

OCCASION: {intent.resolved_occasion}
TARGET DRESSINESS: {intent.dressiness_min}–{intent.dressiness_max} (scale 1–5)
STYLE VIBE: {", ".join(intent.style_vibe) or "no preference"}
FIT PREFERENCE: {intent.fit_preference or "no preference"}
COVERAGE PREFERENCE: {intent.coverage_preference or "no preference"}
USER'S STYLE MEMORY: {", ".join(request.style_descriptors) or "none yet"}

CANDIDATES (already scored — higher score is better):
{candidate_json}

TASK:
1. Select 6 outfits from the candidates. More is better; fewer only if the list is short.
2. Rank them 1 (best) to 6.
3. Write 2–3 natural, friendly reasons per outfit. Reference the occasion, the garments, and why they work together. Never mention scores or confidence numbers.
4. Optionally request ONE bounded modification per outfit: a role swap using garments the user already owns. The engine will look up the replacement — you do NOT name a specific garment. Only request a modification when it clearly improves the outfit.

RULES:
- candidate_index must be an integer from the list above.
- Each candidate_index may appear at most once.
- Do not invent garments. Do not override the occasion or dressiness constraints.
- A modification has a "role" (one of the roles in the outfit's items) and a "preference" (natural-language description).

Return valid JSON:
{{
  "selected": [
    {{
      "candidate_index": integer,
      "rank": integer (1–6),
      "reasons": ["string", "string"],
      "modification": {{"role": "string", "preference": "string"}} or null
    }}
  ]
}}"""


class StylistAdapter(Protocol):
    async def select(self, request: StylistRequest) -> StylistVerdict: ...


class LLMStylistAdapter:
    """Calls Gemini to select and explain the top outfits."""

    def __init__(self, retry: RetryPolicy = DEFAULT_STYLIST_RETRY) -> None:
        self.retry = retry

    async def select(self, request: StylistRequest) -> StylistVerdict:
        """Rerank the candidates, explain the top 6, optionally request modifications.

        Rejects any candidate_index not in `request.candidates` — that is the
        check that keeps the model from referencing outfits it was not shown.
        Raises AdapterError / AdapterTimeout on failure so the caller degrades.
        """
        prompt = _stylist_prompt(request)
        data = await _generate_json(prompt, self.retry)

        valid_indices = {c["index"] for c in request.candidates}
        outfits: list[RankedOutfit] = []

        for item in data.get("selected", []):
            idx = item.get("candidate_index")
            if idx not in valid_indices:
                logger.warning("stylist returned unknown candidate_index %s — skipped", idx)
                continue
            mod_data = item.get("modification")
            modification = (
                ModificationRequest(
                    role=str(mod_data["role"]),
                    preference=str(mod_data["preference"]),
                )
                if isinstance(mod_data, dict) and "role" in mod_data and "preference" in mod_data
                else None
            )
            outfits.append(
                RankedOutfit(
                    candidate_index=idx,
                    rank=int(item.get("rank", len(outfits) + 1)),
                    reasons=list(item.get("reasons", [])),
                    modification=modification,
                )
            )

        if not outfits:
            raise AdapterError("stylist returned no valid selections")

        outfits.sort(key=lambda o: o.rank)
        return StylistVerdict(outfits=outfits)
