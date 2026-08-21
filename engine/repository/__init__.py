"""The single point of database access for the engine.

Every query the engine makes goes through this package. No module outside it may
import the Supabase client or build a query — ad-hoc access elsewhere is exactly
how a tenant boundary slips without anyone noticing.

WHY THIS MATTERS HERE SPECIFICALLY
The engine connects with the Supabase **service-role key**, which bypasses row
level security entirely. The policies in supabase/migrations/0002_rls_policies.sql
do not protect these calls — they protect the web app's direct reads with a user
token. Tenant isolation on this side is therefore this package's own
responsibility, and it is enforced by one convention:

    every public function takes `user_id` as its first required argument,
    and every query it builds filters on that value.

It is never defaulted, never optional, and never read from a request body — it
arrives from the verified JWT via `app.auth.Caller`.

See docs/04-architecture-api.md, "Trust boundary".
"""

from __future__ import annotations

from repository.garments import (
    GarmentInUse,
    GarmentNotFound,
    GarmentRow,
    delete_garment,
    delete_image,
    find_by_image_hash,
    get_garment,
    insert_garment,
    list_garments,
    signed_url,
    update_garment,
    upload_image,
)
from repository.profile import (
    get_body_profile,
    get_style_dna,
    list_garments_for_scoring,
    update_style_dna,
    upsert_body_profile,
)
from repository.queries import (
    OutfitInsert,
    create_recommendation,
    get_outfits_more,
    insert_outfits,
    record_feedback,
    update_recommendation_latency,
)

__all__ = [
    # garments
    "GarmentInUse",
    "GarmentNotFound",
    "GarmentRow",
    "delete_garment",
    "delete_image",
    "find_by_image_hash",
    "get_garment",
    "insert_garment",
    "list_garments",
    "signed_url",
    "update_garment",
    "upload_image",
    # profile + style DNA
    "get_body_profile",
    "get_style_dna",
    "list_garments_for_scoring",
    "update_style_dna",
    "upsert_body_profile",
    # recommendations + outfits
    "OutfitInsert",
    "create_recommendation",
    "get_outfits_more",
    "insert_outfits",
    "record_feedback",
    "update_recommendation_latency",
]
