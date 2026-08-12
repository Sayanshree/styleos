"""Typed adapter for weather lookup.

SCOPE NOTE
docs/04-architecture-api.md assigns weather/context lookup to the **Next.js BFF**,
not the engine: `POST /api/recommend` gathers context server-side and passes it in
the request body, which is why `RecommendRequest.context` exists. This adapter is
therefore not on the primary path today. It is here for the case where the engine
needs to refresh or fill in context itself, and so that the failure shape is
defined in one place.

On failure the engine proceeds with a neutral context, drops `weatherFit` from the
score, and renormalises the remaining weights — it does not fail the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

from adapters.base import RetryPolicy

DEFAULT_WEATHER_RETRY: Final[RetryPolicy] = RetryPolicy(
    timeout_s=2.0,
    max_attempts=2,
    backoff_s=0.25,
)
"""Short and cheap.

Weather is a nice-to-have input with a defined fallback, so it gets a fraction of
the stylist's budget. Anything slower should be abandoned rather than waited on.
"""


@dataclass(frozen=True)
class WeatherReading:
    """Current conditions at the point of the request."""

    temp_c: float
    rain: bool


class WeatherAdapter(Protocol):
    """Interface the pipeline depends on, so the provider can be swapped or faked."""

    async def fetch(self, *, lat: float, lon: float) -> WeatherReading:
        """Return current conditions for a coordinate."""
        ...


class HttpWeatherAdapter:
    """Concrete weather adapter over HTTP. Not implemented."""

    def __init__(self, retry: RetryPolicy = DEFAULT_WEATHER_RETRY) -> None:
        self.retry = retry

    async def fetch(self, *, lat: float, lon: float) -> WeatherReading:
        """Look up current conditions.

        TODO: implement. Raise AdapterTimeout / AdapterError on failure; the
        caller is responsible for substituting a neutral context and dropping
        weatherFit rather than surfacing an error to the user.
        """
        raise NotImplementedError("HttpWeatherAdapter.fetch is not implemented")
