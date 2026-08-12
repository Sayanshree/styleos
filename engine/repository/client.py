"""Service-role Supabase client.

This client bypasses RLS. Nothing outside `repository` should import it — see the
package docstring for why that rule carries the tenant boundary.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Return the process-wide service-role client, building it on first use.

    Cached rather than constructed at module scope so that merely importing this
    module does not reach for the network — which keeps linting, type checking and
    unit tests from needing a live Supabase project.
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
