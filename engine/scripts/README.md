# engine/scripts

Operational scripts for the StyleOS engine. Not part of the FastAPI app.

## RLS isolation test

Verifies that `0002_rls_policies.sql` actually isolates users from each other —
specifically that user B cannot read user A's `recommendation`, `outfit` or
`outfit_item` rows. The `outfit` and `outfit_item` policies reach the owner through
a join (`outfit → recommendation.user_id`, `outfit_item → outfit → recommendation.user_id`)
rather than a direct `user_id` column, which makes them the most likely thing in
that migration to be subtly wrong. This is the test that catches it.

### Setup

```bash
pip install supabase python-dotenv
cp .env.example .env    # then fill in real values
```

Required variables (see `.env.example` at the repo root):

| variable | used by | notes |
|---|---|---|
| `SUPABASE_URL` | both | project URL |
| `SUPABASE_ANON_KEY` | test only | the key under test |
| `TEST_USER_PASSWORD` | both | password for the two throwaway accounts |
| `SUPABASE_SERVICE_ROLE_KEY` | **seeder only** | never read by the test |

Both scripts load `.env` from the **repo root** automatically, resolving the path
from the script's own location (`Path(__file__).resolve().parents[2] / ".env"`) so
they work regardless of which directory you invoke them from.

Variables already exported in your shell take precedence — `load_dotenv` does not
override them. A missing `.env` is not an error either: the scripts fall back to
the exported environment and only fail if a required variable is absent, naming
the one that's missing. Each prints which `.env` it used on startup.

### Running

Order matters. Seed first, then test:

```bash
python engine/scripts/seed_rls_fixtures.py
python engine/scripts/test_rls_isolation.py
```

The test exits `0` if every check passes and `1` if any check fails or if the
fixtures are missing.

### Why there are two scripts

`0002_rls_policies.sql` gives `recommendation`, `outfit` and `outfit_item`
**SELECT-only** policies — there is deliberately no INSERT policy, so a browser
token cannot forge `seq_no` or rewrite feedback history. A user JWT therefore
cannot create the rows the isolation test needs to assert against.

So `seed_rls_fixtures.py` creates them with the **service-role key**, which
bypasses RLS, exactly as the FastAPI engine does in production.
`test_rls_isolation.py` then runs with **only** the anon key and a real user JWT,
and refuses to start if the key it is handed turns out to be a service-role key.
Mixing the two into one script would quietly invalidate every assertion.

The seeder also creates both test accounts with `email_confirm=True`. Without
that, a project with email confirmation enabled returns a user with no session and
the test cannot sign in.

### Reading the output

`PASS`/`FAIL` is printed per table, for two different query shapes: an unfiltered
read (does A's data show up in a bare `select`?) and a targeted read by A's exact
row ids (does it show up when B asks for it specifically?). Both must pass — an
empty unfiltered result alone would not rule out a policy that leaks on direct
lookup.

If user A owns no fixture rows the script exits **INCONCLUSIVE** with a non-zero
code rather than printing a pass. "User B saw zero rows" is meaningless against an
empty table, and a security test that always passes is worse than no test.

### What these scripts write

Both operate on real data in whatever project `SUPABASE_URL` points at. The seeder
creates two auth users, their `app_user` rows, one garment for user A, and one
recommendation/outfit/outfit_item chain per run. Point them at a local
(`supabase start`) or throwaway project — never production.

Nothing is cleaned up afterwards. Re-running the seeder appends another
recommendation for user A rather than replacing the existing one; use
`supabase db reset` to start clean.
