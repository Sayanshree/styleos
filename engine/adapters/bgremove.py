"""Typed adapter for background removal.

STATUS: DEFERRED — STUBBED ON PURPOSE.

`PassthroughBackgroundRemover.remove()` returns the input image unchanged. The
upload path stores the raw photo, and the wardrobe renders it as-is.

The interface and retry shape exist now so that wiring a real provider later is a
one-class change with no call-site churn: the upload path already awaits this
adapter and already treats failure as non-fatal.

TODO (deferred): implement against a hosted background-removal API. When doing so,
keep the failure behaviour below — a background that did not get removed is a
cosmetic problem, and must never cost the user their upload.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final, Protocol

from adapters.base import RetryPolicy

logger = logging.getLogger(__name__)

DEFAULT_BGREMOVE_RETRY: Final[RetryPolicy] = RetryPolicy(
    timeout_s=10.0,
    max_attempts=2,
    backoff_s=0.5,
)


@dataclass(frozen=True)
class RemovalResult:
    """The image to store, and whether the background was actually removed."""

    image: bytes
    mime_type: str
    removed: bool
    detail: str | None = None


class BackgroundRemover(Protocol):
    """Interface the upload path depends on."""

    async def remove(self, image: bytes, mime_type: str) -> RemovalResult:
        """Return the image to store. Never raises."""
        ...


class PassthroughBackgroundRemover:
    """Deferred implementation: hands the original image straight back.

    `removed=False` is reported honestly rather than claiming success, so nothing
    downstream can mistake a raw photo for a cut-out one.
    """

    def __init__(self, *, retry: RetryPolicy = DEFAULT_BGREMOVE_RETRY) -> None:
        self.retry = retry

    async def remove(self, image: bytes, mime_type: str) -> RemovalResult:
        return RemovalResult(
            image=image,
            mime_type=mime_type,
            removed=False,
            detail="background removal is deferred; original image stored unchanged",
        )
