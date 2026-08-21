"""Request and response models for the engine's public API.

Shapes mirror the "Key shapes" section of docs/04-architecture-api.md exactly.

Note what is *absent*: no request model carries a `user_id`. Identity is derived
from the verified JWT in `app.auth` and nowhere else, so a caller cannot express a
user_id even to have it ignored. Request models also set `extra="forbid"`, which
turns an attempt to smuggle one in into an explicit validation error rather than a
silent no-op.

Taxonomy note: the internal field name `formality` is preserved for database and
API compatibility. The user-facing label is "Dressiness" (1 = Lounge / Very
Casual … 5 = Formal). Renaming the DB column would require a migration with
no functional benefit — the 1–5 numeric scale is identical.

Confidence note: there is no `confidence` field on `OutfitOut`. The engine's
`score` is used internally for ranking and never surfaced to the user as a
percentage. The user sees the outfit and its `reasons` — a number adds no
value and invites misinterpretation. The `outfit.score` DB column still exists
for analytics; it just never leaves the engine.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

FeedbackSignal = Literal["accepted", "liked", "disliked"]
"""The only signals that exist.

There is deliberately no `ignored`: an ignored recommendation is one with zero
feedback events, derived at query time. This mirrors the CHECK constraint on
`feedback_event.signal` in supabase/migrations/0001_init.sql.
"""


class HealthResponse(BaseModel):
    """Liveness only — reports nothing about the database or downstream services."""

    status: Literal["ok"] = "ok"


# ---------------------------------------------------------------------------
# Quiz / intent models
# ---------------------------------------------------------------------------

WeatherFeel = Literal["warm", "mild", "cool", "cold", "any"]
CoveragePreference = Literal["light", "balanced", "layered", "any"]
FitPreference = Literal["fitted", "relaxed", "oversized", "any"]


class QuizInput(BaseModel):
    """Per-request answers from the occasion quiz.

    All fields are optional — the user can skip any chip. Missing values fall
    back to the persistent body_profile values. A quiz answer always wins over
    the profile when both are present (quiz > profile invariant, CLAUDE.md §8).
    """

    model_config = ConfigDict(extra="forbid")

    weather_feel: WeatherFeel | None = None
    coverage: CoveragePreference | None = None
    fit_tonight: FitPreference | None = None


class RecommendRequest(BaseModel):
    """Body of POST /recommend. Carries no user_id — see the module docstring."""

    model_config = ConfigDict(extra="forbid")

    occasion: str = Field(min_length=1)
    free_text: str | None = Field(default=None, max_length=500)
    quiz: QuizInput = Field(default_factory=QuizInput)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class OutfitItemOut(BaseModel):
    """One garment in a returned outfit, with the role it fills."""

    garment_id: UUID
    role: str


class OutfitOut(BaseModel):
    """A single ranked outfit.

    `outfit_id` is the handle POST /feedback needs; without it the client
    cannot rate anything.

    Ranks 1–3 are returned by POST /recommend. Ranks 4–6 are returned by
    GET /recommend/{id}/more — they are generated in the same pipeline run
    and already stored; no second call to the LLM is needed.

    There is no `confidence` field. The engine score is used internally for
    ranking; surfacing it as a percentage to users adds no value.
    """

    outfit_id: UUID
    rank: int = Field(ge=1, le=6)
    items: list[OutfitItemOut]
    reasons: list[str]


class RecommendResponse(BaseModel):
    """Body of POST /recommend (ranks 1–3).

    `degraded=True` means the stylist fell back to templated reasons built from
    the per-factor score breakdown. The shape is identical either way, so the
    client cannot structurally tell the difference — but it belongs in the logs.

    `has_more=True` tells the client that ranks 4–6 are stored and available
    via GET /recommend/{recommendation_id}/more.
    """

    recommendation_id: UUID
    latency_ms: int
    degraded: bool
    has_more: bool
    outfits: list[OutfitOut]


class MoreOutfitsResponse(BaseModel):
    """Body of GET /recommend/{id}/more (ranks 4–6, pre-computed)."""

    recommendation_id: UUID
    outfits: list[OutfitOut]


class FeedbackRequest(BaseModel):
    """Body of POST /feedback."""

    model_config = ConfigDict(extra="forbid")

    outfit_id: UUID
    signal: FeedbackSignal


class FeedbackResponse(BaseModel):
    """Updated Style DNA, returned so the UI can reflect learning immediately."""

    descriptors: list[str]


# ---------------------------------------------------------------------------
# Garment taxonomy
# ---------------------------------------------------------------------------

# fmt: off
GarmentCategory = Literal[
    "tops",
    "bottoms",
    "one-piece",
    "outerwear",
    "indian-ethnic",
    "fusion-indo-western",
    "activewear",
    "sleepwear-loungewear",
    "swimwear",
    "undergarments",
    "shoes",
    "bags",
    "accessories",
    "traditional-accessories",
    "sets-coords",
]
# fmt: on

Season = Literal["spring", "summer", "fall", "winter"]
TagSource = Literal["ai", "user_corrected"]


class ColorHsl(BaseModel):
    """Numeric colour. Never a colour-name string — harmony scoring is arithmetic."""

    h: int = Field(ge=0, le=359)
    s: int = Field(ge=0, le=100)
    l: int = Field(ge=0, le=100)  # noqa: E741 - the stored jsonb key, not a loop variable


class GarmentOut(BaseModel):
    """A garment as the wardrobe sees it.

    `image_url` is a short-lived signed URL minted at read time, not a permanent
    address — the storage bucket is private. It is null when signing failed, which
    the UI should render as a missing thumbnail rather than a broken card.

    `formality` is the internal field name (1–5 int). The user-facing label is
    "Dressiness". Physical detail fields (material, fit, pattern, length, neckline,
    sleeve) are all nullable — the AI fills what it can; the user may correct them.
    """

    id: UUID
    image_url: str | None
    category: GarmentCategory
    subcategory: str | None
    garment_type: str | None = None
    color_primary: ColorHsl
    material: str | None = None
    pattern: str | None = None
    fit: str | None = None      # silhouette: fitted / relaxed / oversized / A-line …
    length: str | None = None   # mini / midi / maxi / cropped / …
    neckline: str | None = None
    sleeve: str | None = None
    formality: int = Field(ge=1, le=5)   # user-facing label: Dressiness
    seasons: list[str]
    style_tags: list[str]
    occasion_tags: list[str]
    tag_source: TagSource
    created_at: str


class GarmentCreated(BaseModel):
    """Upload result.

    `tagging_status` is surfaced so the UI can say "we could not read this photo,
    please fill in the tags" instead of silently presenting defaults as though the
    model had chosen them.
    """

    garment: GarmentOut
    tagging_status: Literal["ok", "tagging_failed"]
    tagging_error: str | None = None
    background_removed: bool = False


class GarmentUpdate(BaseModel):
    """User corrections. Every field optional; only what is sent is changed.

    `tag_source` is absent by design — it is set to 'user_corrected' by the
    repository, never chosen by the caller.
    """

    model_config = ConfigDict(extra="forbid")

    category: GarmentCategory | None = None
    subcategory: str | None = None
    garment_type: str | None = None
    color_primary: ColorHsl | None = None
    material: str | None = None
    pattern: str | None = None
    fit: str | None = None
    length: str | None = None
    neckline: str | None = None
    sleeve: str | None = None
    formality: int | None = Field(default=None, ge=1, le=5)
    seasons: list[Season] | None = None
    style_tags: list[str] | None = None
    occasion_tags: list[str] | None = None


class AcceptanceWindow(BaseModel):
    """An acceptance rate together with the sample size behind it.

    `n` is not optional. An improvement claimed from a handful of recommendations
    is noise, and a number quoted without its denominator invites the reader to
    assume it is more than it is — see docs/05-evaluation-plan.md.
    """

    rate: float | None = None
    n: int


class MetricsResponse(BaseModel):
    """Body of GET /metrics, scoped to the calling user."""

    early: AcceptanceWindow
    later: AcceptanceWindow
    improvement: float | None = None
    like_rate: float | None = None
    median_latency_ms: int | None = None
    cv_correction_rate: float | None = None
