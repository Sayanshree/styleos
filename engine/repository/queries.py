"""Placeholder query functions demonstrating the repository pattern.

Signatures are real; bodies are not implemented. What matters here is the shape
every function in this package follows:

    def name(user_id: str, *, ...) -> ...

`user_id` first, always required, never defaulted. Keyword-only arguments after it
so a caller cannot accidentally pass the wrong value positionally into the slot
that carries the tenant boundary.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.schemas import FeedbackSignal


def get_garments(user_id: str, *, categories: list[str] | None = None) -> list[dict[str, Any]]:
    """Return the user's wardrobe, optionally narrowed to certain categories.

    TODO: select from `garment` where user_id = the given value. `color_primary`
    comes back as numeric jsonb ({h,s,l} or LAB) and is scored arithmetically —
    never match colours as strings.
    """
    raise NotImplementedError("repository.get_garments is not implemented")


def create_recommendation(user_id: str, *, occasion: str, context: dict[str, Any]) -> UUID:
    """Insert the `recommendation` row and return its id.

    TODO: implement. Two constraints that are easy to get wrong:

    * This row is written *before* the scoring pipeline runs, so latency can be
      measured and the row still exists if the engine errors. `latency_ms` is
      filled in afterwards, which is why the column is nullable.
    * `seq_no` is assigned inside this insert's transaction as max(seq_no) + 1 for
      the user. It is never client-supplied; the unique (user_id, seq_no)
      constraint is what makes that safe under concurrency.
    """
    raise NotImplementedError("repository.create_recommendation is not implemented")


def record_feedback(user_id: str, *, outfit_id: UUID, signal: FeedbackSignal) -> None:
    """Append a `feedback_event` row.

    TODO: implement. This table is append-only — rows are never updated and never
    deleted, because the timeline is what makes the before/after learning
    comparison possible. There is no `ignored` signal: an ignored recommendation
    is one with no feedback events, derived at query time.

    `user_id` is denormalised onto this table on purpose (every metrics query
    filters by it), but it must still be verified against the outfit's owner
    rather than trusted — the caller's outfit_id is not proof of ownership.
    """
    raise NotImplementedError("repository.record_feedback is not implemented")
