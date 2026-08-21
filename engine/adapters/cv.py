"""Typed adapter for CV garment tagging, backed by Google Gemini.

Perception layer: turns a photo into the structured attributes the wardrobe and
the scoring pipeline need. Off-the-shelf model, no training.

FAILURE IS NOT AN ERROR HERE
Tagging is best-effort. If the model times out, errors, or returns something that
does not satisfy the schema, this adapter returns a result with
`status="tagging_failed"` and safe defaults rather than raising. The upload then
still succeeds and the user fixes the tags by hand through the correction UI.
An upload must never 500 because a third-party model had a bad minute.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Final, Literal, Protocol

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

from adapters.base import RetryPolicy
from adapters.color import NEUTRAL_GREY, Hsl, to_hsl

logger = logging.getLogger(__name__)

MODEL: Final[str] = "gemini-2.5-flash"

DEFAULT_CV_RETRY: Final[RetryPolicy] = RetryPolicy(
    timeout_s=20.0,
    max_attempts=2,
    backoff_s=1.0,
)
"""One retry, then give up and let the user correct by hand.

Image analysis is slower than text, hence the 20s per-attempt budget. Retrying
further would trade a longer upload spinner for a marginal quality gain the user
can supply themselves in two taps.
"""

# fmt: off
Category = Literal[
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

#: Applied when tagging fails. `category` has to be *something* because the
#: column is NOT NULL; "tops" is the most common category and the correction
#: UI opens on it so the user can fix it immediately.
FALLBACK_CATEGORY: Final[Category] = "tops"
FALLBACK_FORMALITY: Final[int] = 3

#: Style tags the model is constrained to choose from. Aesthetic/vibe words
#: only — physical attributes (material, pattern, silhouette) have dedicated
#: fields and must not appear here.
APPROVED_STYLE_TAGS: Final[frozenset[str]] = frozenset({
    "elegant", "feminine", "romantic", "sophisticated",
    "minimal", "casual", "streetwear", "sporty",
    "athleisure", "bohemian", "classic", "chic",
    "glamorous", "edgy", "relaxed", "vintage",
    "festive", "ethnic",
})

PROMPT: Final[str] = """\
You are tagging a single garment for a personal wardrobe database.

Identify the one main garment in the image and describe it precisely.

────────────────────────────────────────
CATEGORY RULES (use exactly one of these values):
  tops                — T-shirt, blouse, shirt, camisole, sweater, hoodie, crop top, polo, tunic…
  bottoms             — jeans, trousers, skirt, shorts, leggings, culottes, joggers…
  one-piece           — dress, jumpsuit, romper, playsuit (NEVER use "tops" for a dress)
  outerwear           — blazer, jacket, coat, puffer, trench, vest, shrug, cape
  indian-ethnic       — saree, salwar suit, anarkali, kurta, kurti, lehenga, sharara, gharara, churidar, dupatta, dhoti pants
  fusion-indo-western — indo-western dress, kurti dress, saree gown, dhoti set, cape set, fusion set
  activewear          — sports bra, workout top, track pants, training shorts, tracksuit
  sleepwear-loungewear — pajama set, nightdress, robe, lounge pants, lounge top
  swimwear            — bikini, one-piece swimsuit, swim shorts, cover-up
  undergarments       — bra, bralette, slip, underwear, camisole (as undergarment)
  shoes               — sneakers, heels, flats, sandals, boots, loafers, mules, juttis, mojaris
  bags                — handbag, tote, shoulder bag, crossbody, clutch, backpack, sling bag
  accessories         — belt, scarf, hat, cap, sunglasses, watch, jewelry, hair accessories
  traditional-accessories — bindi, bangles, jhumka, maang tikka, anklet, waist chain
  sets-coords         — western co-ord, ethnic set, skirt set, pant set, short set

SUBCATEGORY: the specific type within the category, e.g. "Dress", "Blazer", "Saree", "Sneakers".

GARMENT TYPE: optional further specificity, e.g. "Slip Dress", "Bodycon Dress", "Wrap Dress".
  Use this for type-within-subcategory. Leave blank for simple items (e.g. basic T-shirt).

────────────────────────────────────────
PRIMARY COLOR:
  primary_color_hex — dominant colour of the GARMENT as #rrggbb.
  Ignore background, shadows, hangers, skin, and accessories.

────────────────────────────────────────
PHYSICAL ATTRIBUTES (fill what is visible; use null/empty for what you cannot determine):
  material   — e.g. satin, cotton, denim, chiffon, silk, knit, leather, linen, velvet
  pattern    — e.g. solid, floral, striped, plaid, abstract, animal print, geometric
  fit        — e.g. fitted, relaxed, oversized, straight, A-line (the silhouette/cut)
  length     — e.g. mini, midi, maxi, knee-length, cropped, ankle-length (for relevant items)
  neckline   — e.g. cowl, V-neck, crew, square, halter, scoop, off-shoulder (for relevant items)
  sleeve     — e.g. spaghetti strap, sleeveless, short, long, off-shoulder, puff (for relevant items)

────────────────────────────────────────
DRESSINESS (formality):
  1 = Lounge / Very Casual
  2 = Casual
  3 = Smart Casual
  4 = Dressy
  5 = Formal / Black Tie

────────────────────────────────────────
SEASONS: list every season the garment is genuinely wearable in.

STYLE TAGS: choose 3–6 from this approved list ONLY — do not invent others:
  elegant, feminine, romantic, sophisticated, minimal, casual, streetwear, sporty,
  athleisure, bohemian, classic, chic, glamorous, edgy, relaxed, vintage, festive, ethnic
  These must represent the item's aesthetic/vibe, NOT physical attributes.
  Do NOT put material, colour, or silhouette words here.

OCCASION TAGS: 2–4 short lowercase words for when this is worn, e.g. work, date, party, brunch.

────────────────────────────────────────
Describe only what you can see. Do not guess a brand. Do not invent categories.
"""


class GeminiGarmentTags(BaseModel):
    """Exactly what the model is asked to return. Constrained so it cannot drift."""

    category: Category
    subcategory: str = Field(description="Specific type within the category, e.g. 'Dress', 'Blazer'")
    garment_type: str | None = Field(
        default=None,
        description="Optional further specificity, e.g. 'Slip Dress'. Leave null for simple items.",
    )
    primary_color_hex: str = Field(description="Dominant garment colour as #rrggbb")
    material: str | None = Field(default=None, description="e.g. satin, cotton, denim, chiffon")
    pattern: str | None = Field(default=None, description="e.g. solid, floral, striped, plaid")
    fit: str | None = Field(default=None, description="Silhouette/cut: fitted, relaxed, oversized, A-line…")
    length: str | None = Field(default=None, description="e.g. mini, midi, maxi, cropped — leave null for tops/shoes/bags")
    neckline: str | None = Field(default=None, description="e.g. cowl, V-neck, crew — leave null where not applicable")
    sleeve: str | None = Field(default=None, description="e.g. spaghetti strap, short, long — leave null where not applicable")
    formality: int = Field(ge=1, le=5, description="Dressiness: 1=lounge to 5=formal")
    seasons: list[Season]
    style_tags: list[str] = Field(description="3–6 aesthetic tags from the approved list only")
    occasion_tags: list[str] = Field(description="2–4 occasion words, e.g. work, date, party")


@dataclass(frozen=True)
class TaggingResult:
    """Adapter output, already normalised for the database.

    `color_primary` is HSL, never a colour word — the column is numeric jsonb and
    colour harmony is arithmetic on it.

    `formality` is the internal field name (DB column); the user-facing label is
    "Dressiness". The 1–5 scale is unchanged.
    """

    status: Literal["ok", "tagging_failed"]
    category: Category
    color_primary: Hsl
    formality: int
    subcategory: str | None = None
    garment_type: str | None = None
    material: str | None = None
    pattern: str | None = None
    fit: str | None = None
    length: str | None = None
    neckline: str | None = None
    sleeve: str | None = None
    seasons: list[str] = field(default_factory=list)
    style_tags: list[str] = field(default_factory=list)
    occasion_tags: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "ok"


def _failed(reason: str) -> TaggingResult:
    return TaggingResult(
        status="tagging_failed",
        category=FALLBACK_CATEGORY,
        color_primary=NEUTRAL_GREY,
        formality=FALLBACK_FORMALITY,
        error=reason,
    )


def _clean_str(value: str | None) -> str | None:
    """Strip whitespace; return None for blank strings."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class CvTaggingAdapter(Protocol):
    """Interface the upload path depends on, so the model can be faked in tests."""

    async def tag(self, image: bytes, mime_type: str) -> TaggingResult:
        """Describe the garment in `image`. Never raises."""
        ...


class GeminiCvAdapter:
    """Concrete CV tagging adapter over the Gemini API."""

    def __init__(
        self,
        api_key: str,
        *,
        retry: RetryPolicy = DEFAULT_CV_RETRY,
        model: str = MODEL,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._retry = retry
        self._model = model

    async def tag(self, image: bytes, mime_type: str) -> TaggingResult:
        last_error = "no attempt made"

        for attempt in range(1, self._retry.max_attempts + 1):
            try:
                raw = await asyncio.wait_for(
                    self._generate(image, mime_type),
                    timeout=self._retry.timeout_s,
                )
                return self._normalise(raw)
            except TimeoutError:
                last_error = f"timed out after {self._retry.timeout_s}s"
                logger.warning("cv tagging attempt %s timed out", attempt)
            except ValidationError as exc:
                last_error = f"model output failed schema validation: {exc.error_count()} errors"
                logger.warning("cv tagging attempt %s returned invalid output", attempt)
            except Exception as exc:  # deliberately broad, see below
                # Any third-party failure mode at all becomes a soft failure. This
                # adapter's whole contract is that an upload survives a bad model.
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("cv tagging attempt %s failed: %s", attempt, exc)

            if attempt < self._retry.max_attempts:
                await asyncio.sleep(self._retry.backoff_s)

        return _failed(last_error)

    async def _generate(self, image: bytes, mime_type: str) -> GeminiGarmentTags:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_bytes(data=image, mime_type=mime_type),
                PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiGarmentTags,
            ),
        )

        parsed: Any = response.parsed
        if isinstance(parsed, GeminiGarmentTags):
            return parsed
        # The SDK did not hand back a parsed object; fall back to the raw JSON so a
        # cosmetic SDK change does not become a tagging outage.
        return GeminiGarmentTags.model_validate_json(response.text or "")

    @staticmethod
    def _normalise(tags: GeminiGarmentTags) -> TaggingResult:
        # Style tags: keep only approved vibe words; at most 6.
        # The model is instructed to use only the approved list, but validate
        # defensively in case it drifts — a tag that names a physical attribute
        # would interfere with dedicated fields and confuse the UI.
        filtered_style_tags = [
            tag.strip().lower()
            for tag in dict.fromkeys(tags.style_tags)  # deduplicate, preserve order
            if tag.strip().lower() in APPROVED_STYLE_TAGS
        ][:6]

        occasion_tags = [
            tag.strip().lower()
            for tag in tags.occasion_tags
            if tag.strip()
        ][:4]

        seasons = list(dict.fromkeys(tags.seasons))  # deduplicate

        return TaggingResult(
            status="ok",
            category=tags.category,
            subcategory=_clean_str(tags.subcategory),
            garment_type=_clean_str(tags.garment_type),
            color_primary=to_hsl(tags.primary_color_hex),
            material=_clean_str(tags.material),
            pattern=_clean_str(tags.pattern),
            fit=_clean_str(tags.fit),
            length=_clean_str(tags.length),
            neckline=_clean_str(tags.neckline),
            sleeve=_clean_str(tags.sleeve),
            formality=tags.formality,
            seasons=seasons,
            style_tags=filtered_style_tags,
            occasion_tags=occasion_tags,
        )
