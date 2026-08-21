"""Caller authentication for the engine.

Every route except GET /health requires two credentials, per CLAUDE.md:

    Authorization: Bearer <supabase_jwt>   the end user's identity
    X-Service-Token: <shared_secret>       proves the caller is the Next.js BFF

The second exists because the first is not enough on its own: anyone who
obtained a user JWT could otherwise reach the engine directly.

`user_id` is derived from the verified JWT and from nothing else. It never
appears in a request body or query string — the request models in
`app.schemas` cannot express one.

JWT verification delegates to Supabase Auth (`GET /auth/v1/user`). We send
the token to Supabase; they validate the signature, expiry, and audience on
their side and return the user object if valid. This is simpler and more
reliable than mirroring Supabase's key-rotation logic in the engine: no JWKS
URL to get wrong, no crypto library to configure, no 404 on a missing
endpoint.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Annotated, Final

import httpx
from fastapi import Depends, Header, HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

BEARER_PREFIX: Final[str] = "bearer "


@dataclass(frozen=True)
class Caller:
    """The authenticated end user behind a request.

    This is the only channel by which a user_id reaches a route handler.
    """

    user_id: str


def _unauthorised(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def _verify_with_supabase(token: str) -> str:
    """Ask Supabase Auth to validate the JWT; return the user_id.

    Supabase's /auth/v1/user endpoint validates the token fully — signature,
    expiry, audience — and returns the user object. We extract the user id
    from there. A 401 from Supabase means the token is bad; any other non-200
    is treated as a transient failure.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    # Kong API gateway requires apikey on every route.
                    "apikey": settings.supabase_service_role_key,
                },
            )
    except httpx.TimeoutException:
        raise _unauthorised("auth check timed out") from None
    except Exception as exc:
        logger.warning("Supabase auth check failed: %s", exc)
        raise _unauthorised("could not verify token") from exc

    if r.status_code == 401:
        raise _unauthorised("invalid bearer token")
    if r.status_code != 200:
        logger.warning("Supabase auth returned %d: %s", r.status_code, r.text[:200])
        raise _unauthorised("could not verify token")

    data = r.json()
    user_id = data.get("id")
    if not isinstance(user_id, str) or not user_id:
        raise _unauthorised("token carries no subject claim")
    return user_id


async def require_caller(
    authorization: Annotated[str | None, Header()] = None,
    x_service_token: Annotated[str | None, Header()] = None,
) -> Caller:
    """Authenticate the caller and return their identity.

    Every rejection is a 401, never a 500: a bad credential is the caller's
    problem, not a server fault.
    """
    # Service token first: reject anything that is not the BFF before looking
    # at user credentials at all. compare_digest keeps the comparison
    # constant-time so a wrong token cannot be recovered byte-by-byte.
    if x_service_token is None or not secrets.compare_digest(
        x_service_token, settings.service_shared_token
    ):
        raise _unauthorised("missing or invalid X-Service-Token")

    if authorization is None or not authorization.lower().startswith(BEARER_PREFIX):
        raise _unauthorised("missing or malformed Authorization header")

    token = authorization[len(BEARER_PREFIX) :].strip()
    if not token:
        raise _unauthorised("empty bearer token")

    user_id = await _verify_with_supabase(token)
    return Caller(user_id=user_id)


CallerDep = Annotated[Caller, Depends(require_caller)]
"""Inject the authenticated caller into a route handler."""
