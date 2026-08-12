"""Typed adapters for every external dependency.

One module per dependency, each exposing a Protocol the pipeline depends on and a
concrete implementation carrying an explicit timeout and retry policy. The
Protocol is what lets the pipeline be tested without network access.
"""

from __future__ import annotations

from adapters.base import AdapterError, AdapterTimeout, RetryPolicy
from adapters.llm import (
    DEFAULT_STYLIST_RETRY,
    LLMStylistAdapter,
    RankedOutfit,
    StylistAdapter,
    StylistRequest,
    StylistVerdict,
)
from adapters.weather import (
    DEFAULT_WEATHER_RETRY,
    HttpWeatherAdapter,
    WeatherAdapter,
    WeatherReading,
)

__all__ = [
    "DEFAULT_STYLIST_RETRY",
    "DEFAULT_WEATHER_RETRY",
    "AdapterError",
    "AdapterTimeout",
    "HttpWeatherAdapter",
    "LLMStylistAdapter",
    "RankedOutfit",
    "RetryPolicy",
    "StylistAdapter",
    "StylistRequest",
    "StylistVerdict",
    "WeatherAdapter",
    "WeatherReading",
]
