"""Typed adapters for every external dependency.

One module per dependency, each exposing a Protocol the pipeline depends on and a
concrete implementation carrying an explicit timeout and retry policy. The
Protocol is what lets the pipeline be tested without network access.
"""

from __future__ import annotations

from adapters.base import AdapterError, AdapterTimeout, RetryPolicy
from adapters.bgremove import (
    DEFAULT_BGREMOVE_RETRY,
    BackgroundRemover,
    PassthroughBackgroundRemover,
    RemovalResult,
)
from adapters.color import Hsl, hex_to_hsl, rgb_to_hsl, to_hsl
from adapters.cv import (
    DEFAULT_CV_RETRY,
    CvTaggingAdapter,
    GeminiCvAdapter,
    TaggingResult,
)
from adapters.llm import (
    DEFAULT_INTENT_RETRY,
    DEFAULT_STYLIST_RETRY,
    IntentAdapter,
    LLMIntentAdapter,
    LLMStylistAdapter,
    ModificationRequest,
    RankedOutfit,
    ResolvedIntent,
    StylistAdapter,
    StylistRequest,
    StylistVerdict,
    fallback_intent,
)
from adapters.weather import (
    DEFAULT_WEATHER_RETRY,
    HttpWeatherAdapter,
    WeatherAdapter,
    WeatherReading,
)

__all__ = [
    "DEFAULT_BGREMOVE_RETRY",
    "DEFAULT_CV_RETRY",
    "DEFAULT_INTENT_RETRY",
    "DEFAULT_STYLIST_RETRY",
    "DEFAULT_WEATHER_RETRY",
    "AdapterError",
    "AdapterTimeout",
    "BackgroundRemover",
    "CvTaggingAdapter",
    "GeminiCvAdapter",
    "Hsl",
    "HttpWeatherAdapter",
    "IntentAdapter",
    "LLMIntentAdapter",
    "LLMStylistAdapter",
    "ModificationRequest",
    "PassthroughBackgroundRemover",
    "RankedOutfit",
    "RemovalResult",
    "ResolvedIntent",
    "RetryPolicy",
    "StylistAdapter",
    "StylistRequest",
    "StylistVerdict",
    "TaggingResult",
    "WeatherAdapter",
    "WeatherReading",
    "fallback_intent",
    "hex_to_hsl",
    "rgb_to_hsl",
    "to_hsl",
]
