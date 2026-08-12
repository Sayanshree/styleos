"""Typed adapter for the bounded LLM stylist.

The stylist's role is narrow: rerank and explain a candidate set that is already
scored and already valid. It cannot add garments the user does not own and cannot
override hard constraints, because the deterministic pipeline runs to completion
before it is called and it only ever sees outfits from that output.

It sits on the critical path of the one moment the product exists to deliver, so
it must fail soft. On timeout, transport failure, or output that does not parse,
the caller falls back to the deterministic top 3 with reasons generated
mechanically from the per-factor score breakdown, and sets `degraded=True` on the
response. The client sees the same shape either way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Protocol
from uuid import UUID

from adapters.base import RetryPolicy

DEFAULT_STYLIST_RETRY: Final[RetryPolicy] = RetryPolicy(
    timeout_s=8.0,
    max_attempts=2,
    backoff_s=0.5,
)
"""Two attempts, not more.

A third retry costs more than the fallback is worth: templated reasons in 9
seconds beat LLM prose in 25.
"""


@dataclass(frozen=True)
class StylistRequest:
    """What the stylist is given: the scored shortlist and the user's context."""

    occasion: str
    context: dict[str, Any]
    style_descriptors: list[str]
    candidates: list[dict[str, Any]]


@dataclass(frozen=True)
class RankedOutfit:
    """One reranked outfit with its explanation."""

    outfit_id: UUID
    rank: int
    reasons: list[str]
    tweak: str | None = None


@dataclass(frozen=True)
class StylistVerdict:
    """Structured JSON output, parsed. Never free text."""

    outfits: list[RankedOutfit]


class StylistAdapter(Protocol):
    """Interface the pipeline depends on, so the LLM can be swapped or faked."""

    async def rerank(self, request: StylistRequest) -> StylistVerdict:
        """Rerank the candidates and explain the top 3."""
        ...


class LLMStylistAdapter:
    """Concrete stylist adapter. Not implemented."""

    def __init__(self, retry: RetryPolicy = DEFAULT_STYLIST_RETRY) -> None:
        self.retry = retry

    async def rerank(self, request: StylistRequest) -> StylistVerdict:
        """Call the LLM and parse its structured response.

        TODO: implement. Requirements that are not optional:

        * Request structured JSON output and validate it before use.
        * Reject any outfit_id not present in `request.candidates` — that is the
          check that keeps the model from inventing garments.
        * Raise AdapterTimeout / AdapterError on failure so the caller degrades
          rather than 500s.
        """
        raise NotImplementedError("LLMStylistAdapter.rerank is not implemented")
