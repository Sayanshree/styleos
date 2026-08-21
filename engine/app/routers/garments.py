"""Wardrobe maintenance — Flow 2.

Photo uploaded -> CV tagging -> saved to the structured wardrobe.

**This flow updates shared state only. It never triggers a recommendation.**
Adding clothes and asking for an outfit are separate intents, and nothing in this
module calls the recommendation pipeline or writes to `recommendation`.

`user_id` comes from the verified JWT via `CallerDep` and from nowhere else. No
route here accepts it in a body, a query string or a path.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Annotated, Any, Final
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from adapters.bgremove import PassthroughBackgroundRemover
from adapters.color import hsl_to_dict
from adapters.cv import GeminiCvAdapter
from app.auth import CallerDep
from app.config import settings
from app.schemas import GarmentCreated, GarmentOut, GarmentUpdate
from repository import garments as repo

logger = logging.getLogger(__name__)

router = APIRouter(tags=["garments"])

ACCEPTED_MIME_TYPES: Final[frozenset[str]] = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic"}
)

#: Guard against a phone photo eating the request budget. 10 MB is generous for a
#: garment shot and small enough that tagging stays inside its timeout.
MAX_IMAGE_BYTES: Final[int] = 10 * 1024 * 1024

_cv_adapter = GeminiCvAdapter(api_key=settings.gemini_api_key)
_bg_remover = PassthroughBackgroundRemover()


def _to_out(user_id: str, row: repo.GarmentRow) -> GarmentOut:
    """Shape a DB row for the client, signing the image path on the way out."""
    image_path = row.get("image_url")
    url = repo.signed_url(user_id, path=image_path) if isinstance(image_path, str) else None
    return GarmentOut(
        id=UUID(str(row["id"])),
        image_url=url,
        category=row["category"],
        subcategory=row.get("subcategory"),
        garment_type=row.get("garment_type"),
        color_primary=row["color_primary"],
        material=row.get("material"),
        pattern=row.get("pattern"),
        fit=row.get("fit"),
        length=row.get("length"),
        neckline=row.get("neckline"),
        sleeve=row.get("sleeve"),
        formality=int(row["formality"]),
        seasons=list(row.get("seasons") or []),
        style_tags=list(row.get("style_tags") or []),
        occasion_tags=list(row.get("occasion_tags") or []),
        tag_source=row["tag_source"],
        created_at=str(row["created_at"]),
    )


@router.post("/garments", response_model=GarmentCreated, status_code=status.HTTP_201_CREATED)
async def create_garment(
    caller: CallerDep,
    file: Annotated[UploadFile, File()],
    force: bool = Query(
        default=False,
        description="Skip duplicate detection and save even if this image already exists in the wardrobe.",
    ),
) -> GarmentCreated:
    """Upload a photo, tag it, and save the garment.

    Tagging failure is not upload failure. If the CV adapter cannot read the
    photo, the garment is still saved with safe defaults and `tagging_status` says
    so, and the user fixes it in the correction UI. An upload must never 500
    because a third-party model had a bad minute.

    Duplicate detection: a SHA-256 hash of the raw image bytes is checked against
    existing garments for this user. If a match is found and `force` is False, the
    endpoint returns 409 {"message": "duplicate_garment", "existing_id": "...",
    "existing_label": "..."}. Passing `?force=true` skips the check.
    """
    mime_type = (file.content_type or "").lower()
    if mime_type not in ACCEPTED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"unsupported image type {mime_type!r}",
        )

    image = await file.read()
    if not image:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty upload")
    if len(image) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"image exceeds {MAX_IMAGE_BYTES // (1024 * 1024)}MB",
        )

    # Compute a hash before touching the model or storage — it is cheap and lets us
    # bail out early without burning a Gemini call on a photo the user already owns.
    image_hash = hashlib.sha256(image).hexdigest()

    if not force:
        existing = repo.find_by_image_hash(caller.user_id, image_hash)
        if existing is not None:
            label = existing.get("subcategory") or existing.get("category", "item")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "duplicate_garment",
                    "existing_id": str(existing["id"]),
                    "existing_label": str(label),
                },
            )

    # Deferred: returns the original bytes unchanged today.
    removal = await _bg_remover.remove(image, mime_type)
    tags = await _cv_adapter.tag(removal.image, removal.mime_type)

    garment_id = uuid4()
    image_path = repo.upload_image(
        caller.user_id,
        image=removal.image,
        mime_type=removal.mime_type,
        garment_id=garment_id,
    )

    row = repo.insert_garment(
        caller.user_id,
        garment_id=garment_id,
        image_path=image_path,
        category=tags.category,
        subcategory=tags.subcategory,
        garment_type=tags.garment_type,
        color_primary=hsl_to_dict(tags.color_primary),
        material=tags.material,
        pattern=tags.pattern,
        fit=tags.fit,
        length=tags.length,
        neckline=tags.neckline,
        sleeve=tags.sleeve,
        formality=tags.formality,
        seasons=tags.seasons,
        style_tags=tags.style_tags,
        occasion_tags=tags.occasion_tags,
        image_hash=image_hash,
    )

    return GarmentCreated(
        garment=_to_out(caller.user_id, row),
        tagging_status=tags.status,
        tagging_error=tags.error,
        background_removed=removal.removed,
    )


@router.get("/garments", response_model=list[GarmentOut])
async def list_garments(caller: CallerDep) -> list[GarmentOut]:
    """The caller's wardrobe, newest first."""
    return [_to_out(caller.user_id, row) for row in repo.list_garments(caller.user_id)]


@router.get("/garments/{garment_id}", response_model=GarmentOut)
async def get_garment(caller: CallerDep, garment_id: UUID) -> GarmentOut:
    try:
        row = repo.get_garment(caller.user_id, garment_id)
    except repo.GarmentNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "garment not found") from None
    return _to_out(caller.user_id, row)


@router.patch("/garments/{garment_id}", response_model=GarmentOut)
async def update_garment(
    caller: CallerDep,
    garment_id: UUID,
    payload: GarmentUpdate,
) -> GarmentOut:
    """Apply user corrections. Always flips `tag_source` to 'user_corrected'."""
    fields: dict[str, Any] = payload.model_dump(exclude_unset=True)
    if "color_primary" in fields and fields["color_primary"] is not None:
        fields["color_primary"] = dict(fields["color_primary"])
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no fields to update")

    try:
        row = repo.update_garment(caller.user_id, garment_id, fields=fields)
    except repo.GarmentNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "garment not found") from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _to_out(caller.user_id, row)


@router.delete("/garments/{garment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_garment(caller: CallerDep, garment_id: UUID) -> None:
    """Delete a garment.

    A garment that appears in a past outfit is FK-protected and cannot be removed;
    that is a 409, never a 500. Recommendation history has to stay intact for the
    evaluation queries.
    """
    try:
        repo.delete_garment(caller.user_id, garment_id)
    except repo.GarmentNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "garment not found") from None
    except repo.GarmentInUse:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this garment appears in a past outfit and cannot be deleted",
        ) from None
