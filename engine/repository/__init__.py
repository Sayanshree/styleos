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

from repository.queries import create_recommendation, get_garments, record_feedback

__all__ = ["create_recommendation", "get_garments", "record_feedback"]
