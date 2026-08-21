"""Garment persistence and image storage.

Part of the repository package, so the rules there apply: `user_id` is the first
argument of every public function, it is never optional, and every query filters
on it. The engine holds the service-role key and bypasses RLS, so these filters
are the tenant boundary — not a convenience.
"""

from __future__ import annotations

import logging
from typing import Any, Final, cast
from uuid import UUID

from app.config import GARMENT_BUCKET
from repository.client import get_client

logger = logging.getLogger(__name__)

GarmentRow = dict[str, Any]

#: Signed URLs are minted per list call. An hour is long enough that a wardrobe
#: left open does not break, short enough that a leaked URL stops working.
SIGNED_URL_TTL_SECONDS: Final[int] = 3600

#: Postgres foreign-key violation. Raised when deleting a garment that appears in
#: a past outfit — outfit_item.garment_id is `on delete restrict`.
FK_VIOLATION: Final[str] = "23503"

#: Columns the correction UI is allowed to change. `tag_source` is deliberately
#: absent: it is set by this module, never supplied by a caller.
#:
#: Physical detail fields (garment_type, material, pattern, fit, length,
#: neckline, sleeve) are included so the tag editor can correct AI output.
#: `formality` is the internal name; the user-facing label is "Dressiness".
EDITABLE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "category",
        "subcategory",
        "garment_type",
        "color_primary",
        "material",
        "pattern",
        "fit",
        "length",
        "neckline",
        "sleeve",
        "formality",
        "seasons",
        "style_tags",
        "occasion_tags",
    }
)


class GarmentNotFound(LookupError):
    """No garment with that id belongs to this user."""


class GarmentInUse(RuntimeError):
    """The garment appears in a past outfit and cannot be deleted.

    Recommendation history must survive a wardrobe edit, so this is a conflict
    for the caller to surface — never a 500.
    """


def _extension(mime_type: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/heic": "heic",
    }.get(mime_type.lower(), "bin")


def storage_path(user_id: str, garment_id: UUID, mime_type: str) -> str:
    """`{user_id}/{garment_id}.{ext}` — ownership is readable from the path.

    That is what the storage policies in 0004 key on.
    """
    return f"{user_id}/{garment_id}.{_extension(mime_type)}"


def upload_image(user_id: str, *, image: bytes, mime_type: str, garment_id: UUID) -> str:
    """Store the image and return its object path.

    Returns a path, not a URL: the bucket is private, so a URL only exists once
    it has been signed. `garment.image_url` holds this path.
    """
    path = storage_path(user_id, garment_id, mime_type)
    get_client().storage.from_(GARMENT_BUCKET).upload(
        path=path,
        file=image,
        file_options={"content-type": mime_type, "upsert": "true"},
    )
    return path


def signed_url(user_id: str, *, path: str, ttl_seconds: int = SIGNED_URL_TTL_SECONDS) -> str | None:
    """Mint a short-lived readable URL for a stored object.

    Returns None rather than raising if signing fails — a broken thumbnail must
    not take down the whole wardrobe list.
    """
    if not path.startswith(f"{user_id}/"):
        # Defence in depth: never sign an object outside the caller's own prefix,
        # even if a bad row somehow points elsewhere.
        logger.warning("refusing to sign object outside user prefix: %s", path)
        return None
    try:
        result = get_client().storage.from_(GARMENT_BUCKET).create_signed_url(path, ttl_seconds)
    except Exception as exc:  # a signing failure is cosmetic, never fatal
        logger.warning("could not sign %s: %s", path, exc)
        return None

    if isinstance(result, dict):
        # The key has changed spelling across supabase-py versions.
        for key in ("signedURL", "signedUrl", "signed_url"):
            value = result.get(key)
            if isinstance(value, str):
                return value
    return None


def delete_image(user_id: str, *, path: str) -> None:
    """Remove a stored object. Best effort — a leftover object is not fatal."""
    if not path.startswith(f"{user_id}/"):
        return
    try:
        get_client().storage.from_(GARMENT_BUCKET).remove([path])
    except Exception as exc:  # a leftover object is not worth failing the delete
        logger.warning("could not delete object %s: %s", path, exc)


def find_by_image_hash(user_id: str, image_hash: str) -> GarmentRow | None:
    """Return the first garment whose image bytes match `image_hash`, or None.

    Used for duplicate detection on upload. A NULL image_hash (legacy rows) is
    never returned — the WHERE clause skips them via `eq("image_hash", ...)`.
    """
    response = (
        get_client()
        .table("garment")
        .select("id, category, subcategory")
        .eq("user_id", user_id)
        .eq("image_hash", image_hash)
        .limit(1)
        .execute()
    )
    rows = cast(list[GarmentRow], response.data)
    return rows[0] if rows else None


def insert_garment(
    user_id: str,
    *,
    garment_id: UUID,
    image_path: str,
    category: str,
    color_primary: dict[str, int],
    formality: int,
    subcategory: str | None = None,
    garment_type: str | None = None,
    material: str | None = None,
    pattern: str | None = None,
    fit: str | None = None,
    length: str | None = None,
    neckline: str | None = None,
    sleeve: str | None = None,
    seasons: list[str] | None = None,
    style_tags: list[str] | None = None,
    occasion_tags: list[str] | None = None,
    image_hash: str | None = None,
) -> GarmentRow:
    """Insert a garment tagged by the CV adapter.

    `tag_source` is hard-coded to 'ai' here rather than accepted as an argument.
    It is set to 'user_corrected' only by `update_garment`, which is what makes
    the CV correction rate a trustworthy quality signal.

    `formality` is the internal field name (DB column). The user-facing label is
    "Dressiness"; the 1–5 scale is unchanged.

    `image_hash` is the SHA-256 hex digest of the raw image bytes, used for
    duplicate detection on subsequent uploads. NULL is valid — legacy rows and
    force-duplicated rows can omit it.
    """
    payload: GarmentRow = {
        "id": str(garment_id),
        "user_id": user_id,
        "image_url": image_path,
        "category": category,
        "subcategory": subcategory,
        "garment_type": garment_type,
        "color_primary": color_primary,
        "material": material,
        "pattern": pattern,
        "fit": fit,
        "length": length,
        "neckline": neckline,
        "sleeve": sleeve,
        "formality": formality,
        "seasons": seasons or [],
        "style_tags": style_tags or [],
        "occasion_tags": occasion_tags or [],
        "tag_source": "ai",
        "image_hash": image_hash,
    }
    response = get_client().table("garment").insert(payload).execute()
    rows = cast(list[GarmentRow], response.data)
    if not rows:
        raise RuntimeError("garment insert returned no row")
    return rows[0]


def list_garments(user_id: str) -> list[GarmentRow]:
    """Every garment the user owns, newest first."""
    response = (
        get_client()
        .table("garment")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return cast(list[GarmentRow], response.data)


def get_garment(user_id: str, garment_id: UUID) -> GarmentRow:
    """One garment, scoped to its owner. Raises GarmentNotFound otherwise."""
    response = (
        get_client()
        .table("garment")
        .select("*")
        .eq("user_id", user_id)
        .eq("id", str(garment_id))
        .limit(1)
        .execute()
    )
    rows = cast(list[GarmentRow], response.data)
    if not rows:
        raise GarmentNotFound(str(garment_id))
    return rows[0]


def update_garment(user_id: str, garment_id: UUID, *, fields: GarmentRow) -> GarmentRow:
    """Apply user corrections and flip `tag_source` to 'user_corrected'.

    Unknown keys are dropped rather than forwarded, so a caller cannot rewrite
    user_id, image_url or tag_source through this path.
    """
    clean = {key: value for key, value in fields.items() if key in EDITABLE_FIELDS}
    if not clean:
        raise ValueError("no editable fields supplied")
    clean["tag_source"] = "user_corrected"

    response = (
        get_client()
        .table("garment")
        .update(clean)
        .eq("user_id", user_id)
        .eq("id", str(garment_id))
        .execute()
    )
    rows = cast(list[GarmentRow], response.data)
    if not rows:
        raise GarmentNotFound(str(garment_id))
    return rows[0]


def delete_garment(user_id: str, garment_id: UUID) -> None:
    """Delete a garment and its image.

    Raises GarmentInUse when the row is referenced by an outfit_item. That FK is
    `on delete restrict` on purpose: a garment that appeared in a past
    recommendation cannot be erased, because the evaluation queries depend on
    that history staying intact.
    """
    existing = get_garment(user_id, garment_id)

    try:
        response = (
            get_client()
            .table("garment")
            .delete()
            .eq("user_id", user_id)
            .eq("id", str(garment_id))
            .execute()
        )
    except Exception as exc:  # inspected and re-raised below
        if FK_VIOLATION in str(exc):
            raise GarmentInUse(str(garment_id)) from exc
        raise

    if not cast(list[GarmentRow], response.data):
        raise GarmentNotFound(str(garment_id))

    image_path = existing.get("image_url")
    if isinstance(image_path, str):
        delete_image(user_id, path=image_path)
