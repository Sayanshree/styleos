"""Step 0: Intent extraction.

Wraps LLM call #1. On failure falls back to `adapters.llm.fallback_intent`
so the pipeline always has a ResolvedIntent to work with.
"""

from __future__ import annotations

import logging
from typing import Any

from adapters.base import AdapterError, AdapterTimeout
from adapters.llm import (
    LLMIntentAdapter,
    ResolvedIntent,
    fallback_intent,
)
from app.schemas import QuizInput

logger = logging.getLogger(__name__)

_adapter = LLMIntentAdapter()


async def extract_intent(
    occasion: str,
    free_text: str | None,
    quiz: QuizInput,
    body_profile: dict[str, Any] | None,
    style_descriptors: list[str],
) -> tuple[ResolvedIntent, bool]:
    """Return (intent, degraded).

    `degraded=True` when the LLM call failed and we fell back to rule-based
    extraction. The router propagates this flag to the response.
    """
    quiz_dict = quiz.model_dump(exclude_none=True)
    try:
        intent = await _adapter.extract(
            occasion=occasion,
            free_text=free_text,
            quiz=quiz_dict,
            body_profile=body_profile,
            style_descriptors=style_descriptors,
        )
        return intent, False
    except (AdapterError, AdapterTimeout) as exc:
        logger.warning("intent extraction failed, using fallback: %s", exc)
        return fallback_intent(occasion, quiz_dict, body_profile), True
