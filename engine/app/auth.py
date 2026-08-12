"""Caller authentication for the engine.

Every route except GET /health requires two credentials, per
docs/04-architecture-api.md:

    Authorization: Bearer <supabase_jwt>   the end user's identity
    X-Service-Token: <shared_secret>       proves the caller is the Next.js BFF

The second exists because the first is not enough on its own: anyone who obtained
a user JWT could otherwise reach the engine directly. Defence in depth.

`user_id` is derived from the verified JWT and from nothing else. It never appears
in a request body or query string — a body-supplied user_id is a spoofing hole,
and the request models in `app.schemas` cannot express one.

STATUS
------
Header handling below is real and testable. Signature verification and claim
extraction are NOT implemented; see the TODO in `require_caller`.

The dependency raises rather than returning a placeholder identity. That is
deliberate: an auth dependency that hands back a plausible-looking user_id without
verifying anything is exactly the code that reaches production by accident. The
consequence is that /recommend, /feedback and /metrics return 500 for a
well-formed request until JWT verification lands, and their 501 stubs are
unreachable until then.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated, Final

from fastapi import Depends, Header, HTTPException, status

from app.config import settings

BEARER_PREFIX: Final[str] = "bearer "


@dataclass(frozen=True)
class Caller:
    """The authenticated end user behind a request.

    This is the only channel by which a user_id reaches a route handler.
    """

    user_id: str


def _unauthorised(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def require_caller(
    authorization: Annotated[str | None, Header()] = None,
    x_service_token: Annotated[str | None, Header()] = None,
) -> Caller:
    """Authenticate the caller and return their identity.

    Raises 401 for a missing or wrong service token, and 401 for a missing or
    malformed Authorization header. Both paths are implemented.
    """
    # Service token first: reject anything that is not the BFF before looking at
    # user credentials at all. compare_digest keeps the comparison constant-time,
    # so a wrong token cannot be recovered byte-by-byte from response timings.
    if x_service_token is None or not secrets.compare_digest(
        x_service_token, settings.service_shared_token
    ):
        raise _unauthorised("missing or invalid X-Service-Token")

    if authorization is None or not authorization.lower().startswith(BEARER_PREFIX):
        raise _unauthorised("missing or malformed Authorization header")

    token = authorization[len(BEARER_PREFIX) :].strip()
    if not token:
        raise _unauthorised("empty bearer token")

    # TODO: verify `token` against settings.supabase_jwt_secret (HS256), reject
    # expired / wrong-audience / wrong-issuer tokens with 401, and return
    # Caller(user_id=claims["sub"]). Until that exists this raises rather than
    # returning an unverified identity.
    raise NotImplementedError(
        "JWT verification is not implemented. Verify the bearer token against "
        "SUPABASE_JWT_SECRET and derive user_id from the `sub` claim before "
        "treating this dependency as anything but scaffolding."
    )


CallerDep = Annotated[Caller, Depends(require_caller)]
"""Inject the authenticated caller into a route handler."""
