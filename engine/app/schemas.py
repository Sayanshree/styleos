"""Request and response models for the engine's public API.

Shapes mirror the "Key shapes" section of docs/04-architecture-api.md exactly.

Note what is *absent*: no request model carries a `user_id`. Identity is derived
from the verified JWT in `app.auth` and nowhere else, so a caller cannot express a
user_id even to have it ignored. Request models also set `extra="forbid"`, which
turns an attempt to smuggle one in into an explicit validation error rather than a
silent no-op.
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


class RequestContext(BaseModel):
    """Ambient context gathered by the BFF and passed through on the request.

    Both fields are optional: on a weather lookup failure the BFF sends a neutral
    context and the engine drops `weatherFit` from scoring, renormalising the
    remaining weights.
    """

    model_config = ConfigDict(extra="forbid")

    temp_c: float | None = None
    rain: bool | None = None


class RecommendRequest(BaseModel):
    """Body of POST /recommend. Carries no user_id — see the module docstring."""

    model_config = ConfigDict(extra="forbid")

    occasion: str = Field(min_length=1)
    context: RequestContext = Field(default_factory=RequestContext)


class OutfitItemOut(BaseModel):
    """One garment in a returned outfit, with the role it fills."""

    garment_id: UUID
    role: str


class OutfitOut(BaseModel):
    """A single ranked outfit.

    `outfit_id` is the handle POST /feedback needs; without it the client cannot
    rate anything. `confidence` derives from the engine score, not the LLM, and
    `weakest_factor` names the factor that capped it.
    """

    outfit_id: UUID
    rank: int = Field(ge=1, le=3)
    confidence: int = Field(ge=0, le=100)
    items: list[OutfitItemOut]
    reasons: list[str]
    weakest_factor: str | None = None


class RecommendResponse(BaseModel):
    """Body of POST /recommend.

    `degraded=True` means the stylist fell back to templated reasons built from
    the per-factor score breakdown. The shape is identical either way, so the
    client cannot structurally tell the difference — but it belongs in the logs.
    """

    recommendation_id: UUID
    latency_ms: int
    degraded: bool
    outfits: list[OutfitOut]


class FeedbackRequest(BaseModel):
    """Body of POST /feedback."""

    model_config = ConfigDict(extra="forbid")

    outfit_id: UUID
    signal: FeedbackSignal


class FeedbackResponse(BaseModel):
    """Updated Style DNA, returned so the UI can reflect learning immediately."""

    descriptors: list[str]


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
