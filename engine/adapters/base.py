"""Shared shape for external-service adapters.

Every external call the engine makes — LLM, weather, CV — goes through a typed
adapter carrying an explicit timeout and retry policy. No bare network call
anywhere else: an unbounded call on the critical path is how a recommendation
request turns into a hung browser tab.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """Timeout and retry shape for one external dependency.

    `timeout_s` is per attempt, not for the call as a whole, so the worst-case
    wall time is roughly `max_attempts * timeout_s` plus backoff. Size it against
    the ~15 second budget for an explained recommendation.
    """

    timeout_s: float
    max_attempts: int
    backoff_s: float

    @property
    def worst_case_s(self) -> float:
        """Upper bound on total time spent, useful for budgeting the request."""
        return self.max_attempts * self.timeout_s + (self.max_attempts - 1) * self.backoff_s


class AdapterError(RuntimeError):
    """An external dependency failed after exhausting its retry policy.

    Callers are expected to catch this and degrade rather than propagate a 5xx —
    see docs/04-architecture-api.md, "Degradation".
    """


class AdapterTimeout(AdapterError):
    """The dependency did not answer within its timeout."""
