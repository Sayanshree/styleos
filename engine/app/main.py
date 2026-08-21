"""FastAPI application for the StyleOS recommendation engine.

Server-side only — this service is never called from a browser and has no public
route in the app's DNS. Every route except GET /health requires both a Supabase
user JWT and the BFF shared token; see `app.auth`.

No CORS middleware is configured, deliberately. The only client is the Next.js BFF
calling server-to-server, so there is no browser origin to allow. Adding
permissive CORS here would quietly undo the trust boundary.

Importing this module loads and validates configuration (`app.config`), so a
missing environment variable fails the process at startup rather than on the first
request.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.routers import feedback, garments, health, metrics, recommend

app = FastAPI(
    title="StyleOS Engine",
    version="0.1.0",
    description=(
        "Recommendation, preference learning and evaluation service. "
        "Called only by the Next.js BFF, never from a browser."
    ),
)

app.include_router(health.router)
app.include_router(garments.router)
app.include_router(recommend.router)
app.include_router(feedback.router)
app.include_router(metrics.router)
