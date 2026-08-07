#!/usr/bin/env python3
"""Verify cross-user RLS isolation with the anon key + a real user JWT.

This script never reads SUPABASE_SERVICE_ROLE_KEY, and refuses to run if the key
it is given turns out to be a service-role key — the whole point is testing what
the anon key plus a user token can actually see. The service-role key bypasses RLS
entirely, so using it here would make every assertion meaningless.

Fixture rows for `recommendation`, `outfit` and `outfit_item` must already exist,
created by seed_rls_fixtures.py. They cannot be created here: 0002_rls_policies.sql
gives those tables SELECT-only policies, so a user JWT is (correctly) refused. If
no fixtures are found this script exits non-zero as INCONCLUSIVE rather than
reporting a pass — "user B saw zero rows" proves nothing against an empty table.

Env: SUPABASE_URL, SUPABASE_ANON_KEY, TEST_USER_PASSWORD

Exit codes: 0 all checks passed · 1 a check failed or fixtures were missing
"""

import base64
import json
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

RESULTS = []


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


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    return ok


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


def key_role(key):
    """Best-effort identification of a Supabase key's role.

    Legacy keys are JWTs carrying a `role` claim, so the claim can be read
    directly. Newer keys (sb_publishable_... / sb_secret_...) are opaque, so the
    documented prefix is the only signal available — which is enough for the one
    case that matters here, catching a secret key handed in as the anon key.
    Returns None when the role genuinely cannot be determined.
    """
    if key.startswith("sb_secret_"):
        return "service_role"
    if key.startswith("sb_publishable_"):
        return "anon"

    parts = key.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload)).get("role")
    except Exception:
        return None


def sign_in_or_up(client, email, password):
    """Sign in, falling back to sign-up for a first run. Returns the user id."""
    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
        if res.session:
            return res.user.id
    except Exception:
        pass

    try:
        res = client.auth.sign_up({"email": email, "password": password})
    except Exception as exc:
        sys.exit(f"Could not sign in or sign up {email}: {exc}")

    if not getattr(res, "session", None):
        # Email confirmation is probably enabled, so sign-up yields no session.
        try:
            res = client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
        except Exception:
            pass

    if not getattr(res, "session", None):
        sys.exit(
            f"Signed up {email} but got no session — email confirmation is likely "
            "enabled on this project.\nRun engine/scripts/seed_rls_fixtures.py "
            "first; it creates both test users pre-confirmed."
        )
    return res.user.id


def ensure_app_user(client, user_id, email):
    """app_user has an INSERT policy scoped to auth.uid() = id, so a user may
    create their own row. Nothing in 0001 does this automatically at signup."""
    rows = client.table("app_user").select("id").eq("id", user_id).execute().data
    if not rows:
        client.table("app_user").insert({"id": user_id, "email": email}).execute()


def rows_of(client, table, columns="*"):
    return client.table(table).select(columns).execute().data


def main():
    env_status = load_env()

    url = env("SUPABASE_URL")
    anon_key = env("SUPABASE_ANON_KEY")
    password = env("TEST_USER_PASSWORD")

    role = key_role(anon_key)
    if role == "service_role":
        sys.exit(
            "SUPABASE_ANON_KEY holds a service-role key. That key bypasses RLS, "
            "so every assertion here would pass regardless of policy. Refusing to run."
        )

    print("RLS cross-user isolation test")
    print(f"  env      : {env_status}")
    print(f"  url      : {url}")
    print(f"  key role : {role or 'unknown (opaque publishable key)'}\n")

    client = create_client(url, anon_key)

    # ---------------------------------------------------------------- user A
    uid_a = sign_in_or_up(client, USER_A, password)
    ensure_app_user(client, uid_a, USER_A)
    print(f"signed in as A ({uid_a})")

    rec_a = rows_of(client, "recommendation", "id")
    outfit_a = rows_of(client, "outfit", "id")
    item_a = rows_of(client, "outfit_item", "outfit_id,garment_id")
    garment_a = rows_of(client, "garment", "id")

    print(
        f"  fixtures visible to A: recommendation={len(rec_a)} "
        f"outfit={len(outfit_a)} outfit_item={len(item_a)} garment={len(garment_a)}"
    )

    if not (rec_a and outfit_a and item_a):
        sys.exit(
            "\nINCONCLUSIVE: user A owns no recommendation/outfit/outfit_item rows, "
            "so the isolation assertions below would pass against empty tables and "
            "prove nothing.\nRun engine/scripts/seed_rls_fixtures.py first."
        )

    rec_ids = [r["id"] for r in rec_a]
    outfit_ids = [r["id"] for r in outfit_a]
    item_outfit_ids = [r["outfit_id"] for r in item_a]
    garment_ids = [r["id"] for r in garment_a]

    # Confirms the SELECT-only design, and documents why the seeder is needed.
    print("\nas user A — engine tables must reject writes:")
    try:
        client.table("recommendation").insert(
            {"user_id": uid_a, "occasion": "test", "context": {}, "seq_no": 999999}
        ).execute()
        check("recommendation insert rejected", False, "insert unexpectedly succeeded")
    except Exception:
        check("recommendation insert rejected", True)

    # ---------------------------------------------------------------- user B
    client.auth.sign_out()
    uid_b = sign_in_or_up(client, USER_B, password)
    ensure_app_user(client, uid_b, USER_B)
    print(f"\nsigned out, signed in as B ({uid_b})")

    if uid_a == uid_b:
        sys.exit("User A and B resolved to the same id — check the test accounts.")

    print("\nas user B — unfiltered reads must not contain A's rows:")
    leaked = [r["id"] for r in rows_of(client, "recommendation", "id") if r["id"] in rec_ids]
    check("recommendation  unfiltered", not leaked, f"leaked {leaked}" if leaked else "")

    leaked = [r["id"] for r in rows_of(client, "outfit", "id") if r["id"] in outfit_ids]
    check("outfit          unfiltered", not leaked, f"leaked {leaked}" if leaked else "")

    leaked = [
        r["outfit_id"]
        for r in rows_of(client, "outfit_item", "outfit_id")
        if r["outfit_id"] in item_outfit_ids
    ]
    check("outfit_item     unfiltered", not leaked, f"leaked {leaked}" if leaked else "")

    print("\nas user B — targeted reads by A's exact ids must return nothing:")
    got = client.table("recommendation").select("id").in_("id", rec_ids).execute().data
    check("recommendation  by id", not got, f"returned {len(got)} rows" if got else "")

    got = client.table("outfit").select("id").in_("id", outfit_ids).execute().data
    check("outfit          by id", not got, f"returned {len(got)} rows" if got else "")

    got = (
        client.table("outfit_item")
        .select("outfit_id")
        .in_("outfit_id", item_outfit_ids)
        .execute()
        .data
    )
    check("outfit_item     by outfit_id", not got, f"returned {len(got)} rows" if got else "")

    if garment_ids:
        got = client.table("garment").select("id").in_("id", garment_ids).execute().data
        check("garment         by id", not got, f"returned {len(got)} rows" if got else "")

    client.auth.sign_out()

    # ---------------------------------------------------------------- summary
    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
        sys.exit(1)
    print("All RLS isolation checks passed.")


if __name__ == "__main__":
    main()
