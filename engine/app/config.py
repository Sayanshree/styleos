"""Engine configuration, read from the environment.

Values come from the process environment, topped up from the repo-root `.env` via
python-dotenv — the same pattern `engine/scripts/` uses. Variables already exported
in the shell win; a missing `.env` is not an error on its own.

Validation is deliberately **eager**: an incomplete environment aborts at import,
before the app can bind a port. A misconfigured deploy should fail to boot rather
than accept traffic and fail on the first real request.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# engine/app/config.py -> parents[2] is the repo root, the same depth as
# engine/scripts/*.py. Resolving from __file__ rather than the cwd keeps this
# correct no matter which directory uvicorn is started from.
ENV_PATH: Final[Path] = Path(__file__).resolve().parents[2] / ".env"

REQUIRED_VARS: Final[tuple[str, ...]] = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET",
    "SERVICE_SHARED_TOKEN",
)


class ConfigError(RuntimeError):
    """The environment is missing something the engine cannot run without."""


@dataclass(frozen=True)
class Settings:
    """Everything the engine reads from the environment.

    `supabase_service_role_key` bypasses RLS entirely and `service_shared_token`
    is the BFF's proof of identity — neither may ever be logged or returned in a
    response body.
    """

    supabase_url: str
    supabase_service_role_key: str
    supabase_jwt_secret: str
    service_shared_token: str


def load_settings() -> Settings:
    """Load and validate configuration, reporting *every* missing variable at once."""
    load_dotenv(ENV_PATH)

    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        found = "found" if ENV_PATH.exists() else "not found"
        raise ConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + f"\n  .env looked for at: {ENV_PATH} ({found})"
            + "\n  Set them there, or export them, before starting the engine."
        )

    return Settings(
        supabase_url=os.environ["SUPABASE_URL"],
        supabase_service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        supabase_jwt_secret=os.environ["SUPABASE_JWT_SECRET"],
        service_shared_token=os.environ["SERVICE_SHARED_TOKEN"],
    )


settings: Final[Settings] = load_settings()
