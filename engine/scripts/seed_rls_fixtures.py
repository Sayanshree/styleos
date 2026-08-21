#!/usr/bin/env python3
"""Seed the fixture rows that test_rls_isolation.py asserts against.

Why this exists as a separate script:

0002_rls_policies.sql gives `recommendation`, `outfit` and `outfit_item`
SELECT-only policies — there is deliberately no INSERT policy, so that a browser
token cannot forge seq_no or feedback history. A user JWT therefore cannot create
the rows the isolation test needs. They are created here instead, with the
service-role key, exactly as the FastAPI engine does in production.

test_rls_isolation.py stays strictly anon-key + user JWT and never reads the
service-role key. Keeping the two concerns in separate files is the point.

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, TEST_USER_PASSWORD

Idempotent-ish: re-running creates one additional recommendation for user A
rather than failing on the unique (user_id, seq_no) constraint. Users, app_user
rows and the test garment are reused if they already exist.
"""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("python-dotenv is not installed. Run: pip install python-dotenv")

try:
    from supabase import create_client
except ImportError:
    sys.exit("supabase-py is not installed. Run: pip install supabase")

USER_A = "test-a@example.com"
USER_B = "test-b@example.com"

# This file lives at <repo>/engine/scripts/, so the repo root is two levels up.
# Resolving from __file__ rather than the cwd means the script finds .env no
# matter which directory it is invoked from.
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_env():
    """Load .env from the repo root. Returns a one-line status for logging.

    Variables already exported in the shell win — load_dotenv does not override
    them by default. A missing .env is not an error; the script falls back to the
    exported environment and only fails if a required variable is absent.
    """
    if load_dotenv(ENV_PATH):
        return f"loaded {ENV_PATH}"
    if ENV_PATH.exists():
        return f"{ENV_PATH} present but set nothing"
    return f"no {ENV_PATH}; using exported environment only"


def env(name):
    value = os.environ.get(name)
    if not value:
        if ENV_PATH.exists():
            hint = f"{ENV_PATH} exists, but {name} is blank there. Fill it in."
        else:
            hint = (
                f"No .env at {ENV_PATH}. Copy .env.example there and fill it in, "
                f"or export {name} yourself — the scripts do not read .env.example."
            )
        sys.exit(f"Missing required environment variable: {name}\n  {hint}")
    return value


def find_user_by_email(sb, email):
    """Return the auth user with this email, or None."""
    result = sb.auth.admin.list_users()
    # supabase-py has returned both a bare list and an object with .users
    users = result if isinstance(result, list) else getattr(result, "users", [])
    for user in users:
        if (user.email or "").lower() == email.lower():
            return user
    return None


def ensure_user(sb, email, password):
    """Create the auth user pre-confirmed, or return the existing one.

    email_confirm=True matters: without it, a project with email confirmation
    enabled hands back a user with no session, and the isolation test cannot
    sign in.
    """
    existing = find_user_by_email(sb, email)
    if existing:
        print(f"  user exists    {email}  {existing.id}")
        return existing.id

    created = sb.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user = getattr(created, "user", created)
    print(f"  user created   {email}  {user.id}")
    return user.id


def ensure_app_user(sb, user_id, email):
    """recommendation.user_id references app_user(id), and signup only writes
    auth.users — nothing in 0001 creates the app_user row."""
    rows = sb.table("app_user").select("id").eq("id", user_id).execute().data
    if rows:
        return
    sb.table("app_user").insert({"id": user_id, "email": email}).execute()
    print(f"  app_user row   {email}")


def ensure_garment(sb, user_id):
    """outfit_item.garment_id is NOT NULL and FK-constrained, so the fixture
    needs a real garment to point at."""
    rows = (
        sb.table("garment")
        .select("id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
    )
    if rows:
        return rows[0]["id"]

    row = (
        sb.table("garment")
        .insert(
            {
                "user_id": user_id,
                "image_url": "https://example.invalid/rls-test-garment.png",
                "category": "tops",
                "color_primary": {"h": 210, "s": 40, "l": 55},
                "formality": 3,
                "seasons": ["summer"],
                "style_tags": ["minimal"],
                "occasion_tags": ["test"],
                "tag_source": "ai",
            }
        )
        .execute()
        .data[0]
    )
    print(f"  garment        {row['id']}")
    return row["id"]


def next_seq_no(sb, user_id):
    rows = (
        sb.table("recommendation")
        .select("seq_no")
        .eq("user_id", user_id)
        .order("seq_no", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return rows[0]["seq_no"] + 1 if rows else 1


def main():
    env_status = load_env()

    url = env("SUPABASE_URL")
    service_key = env("SUPABASE_SERVICE_ROLE_KEY")
    password = env("TEST_USER_PASSWORD")

    sb = create_client(url, service_key)

    print("Seeding RLS fixtures (service-role key)")
    print(f"  env: {env_status}")
    print("\nusers:")
    uid_a = ensure_user(sb, USER_A, password)
    ensure_user(sb, USER_B, password)

    print("\nuser A rows:")
    ensure_app_user(sb, uid_a, USER_A)
    garment_id = ensure_garment(sb, uid_a)

    rec = (
        sb.table("recommendation")
        .insert(
            {
                "user_id": uid_a,
                "occasion": "test",
                "context": {},
                "seq_no": next_seq_no(sb, uid_a),
            }
        )
        .execute()
        .data[0]
    )
    print(f"  recommendation {rec['id']}  seq_no={rec['seq_no']}")

    outfit = (
        sb.table("outfit")
        .insert(
            {
                "recommendation_id": rec["id"],
                "rank": 1,
                "score": 1.0,
                "confidence": 50,
                "reasons": [],
            }
        )
        .execute()
        .data[0]
    )
    print(f"  outfit         {outfit['id']}")

    sb.table("outfit_item").insert(
        {"outfit_id": outfit["id"], "garment_id": garment_id, "role": "top"}
    ).execute()
    print(f"  outfit_item    outfit={outfit['id']} garment={garment_id}")

    # user B is created but deliberately left with no rows of its own
    print("\nDone. Now run: python engine/scripts/test_rls_isolation.py")


if __name__ == "__main__":
    main()
