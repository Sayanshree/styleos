-- 0003_app_user_signup.sql — create app_user rows automatically at signup
--
-- THE GAP
-- Supabase auth writes to auth.users on signup, but nothing created the matching
-- public.app_user row. body_profile.user_id, style_dna.user_id, garment.user_id,
-- recommendation.user_id and feedback_event.user_id all reference app_user(id),
-- so a freshly signed-up user held an auth identity that could not own any
-- application data — their first garment upload or recommendation would fail on
-- the foreign key.
--
-- WHY A TRIGGER RATHER THAN THE NEXT.JS AUTH CALLBACK
-- The trigger runs inside the same transaction as the auth.users insert, on every
-- signup path — dashboard, admin API, OAuth, magic link, the client SDK — with no
-- client involvement and nothing to forget or bypass. A BFF callback covers only
-- the paths the BFF happens to handle.
--
-- WHY SECURITY DEFINER, AND WHY THAT IS SAFE HERE
-- It is required, for two independent reasons:
--   1. The trigger fires as whichever role inserted into auth.users — normally
--      supabase_auth_admin (GoTrue), which does not own public.app_user and has
--      no INSERT privilege on it.
--   2. app_user has RLS enabled, and 0002's app_user_insert policy checks
--      auth.uid() = id. At signup there is no JWT yet, so auth.uid() is NULL and
--      the WITH CHECK would fail. SECURITY DEFINER runs the body as the function
--      owner (postgres), who owns the table and is therefore not subject to its
--      RLS policies.
--
-- SECURITY DEFINER is normally the risky choice; it is safe in this specific
-- function because:
--   * It takes no arguments. The only values it reads are new.id and new.email
--     from the trigger row, both produced by GoTrue, never supplied by a client.
--     There is no input a caller could bend to make it write something else.
--   * It cannot forge another user's row: the id it writes is the id of the
--     auth.users row that just fired the trigger.
--   * It writes one row to one table and nothing else. No dynamic SQL, no
--     branching on caller-controlled data.
--   * ON CONFLICT DO NOTHING means it can never overwrite or clobber an existing
--     app_user row — the worst it can do to existing data is nothing at all.
--   * set search_path = '' closes the classic SECURITY DEFINER escalation, where
--     an attacker creates a same-named table or function in a schema earlier in
--     the search path and gets the elevated function to call it instead. With an
--     empty search_path every reference must be schema-qualified, and this body
--     qualifies public.app_user explicitly.
--   * EXECUTE is revoked from public/anon/authenticated below, so it is not
--     callable directly by any client role — only the trigger invokes it.
--
-- NOTE ON app_user.email
-- 0001 declares app_user.email as NOT NULL. auth.users.email is nullable for
-- phone-only and anonymous sign-ins. If either is ever enabled on this project,
-- this trigger will raise and abort the signup transaction. v1 is email auth
-- only, so this holds today; the fix when that changes is to make app_user.email
-- nullable in a later migration, not to weaken this trigger.

-- Re-runnable: drop before recreating.
drop trigger if exists on_auth_user_created on auth.users;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  -- app_user.email is NOT NULL (0001), but auth.users.email is nullable — it is
  -- empty for phone-only and anonymous sign-ins. If either auth method is ever
  -- enabled, this insert raises; and because the trigger runs inside the signup
  -- transaction, that aborts the signup itself, not merely the app_user row.
  -- Email/password is all this project uses today, so it holds.
  --
  -- The fix at that point is to make app_user.email nullable in a new migration.
  -- Do not weaken this trigger instead: a coalesce to '' or to new.id::text would
  -- keep signups working while quietly filling the column with values that are
  -- not addresses, which every consumer of app_user.email would then have to
  -- defend against.
  insert into public.app_user (id, email, created_at)
  values (new.id, new.email, now())
  on conflict (id) do nothing;
  return new;
end;
$$;

comment on function public.handle_new_user() is
  'Creates the public.app_user row for a new auth.users row. SECURITY DEFINER so '
  'it can insert past RLS at signup time, when auth.uid() is still NULL. Takes no '
  'arguments and writes only the triggering row''s own id.';

create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.handle_new_user();

-- Not callable by clients. Trigger functions are invoked by the system, and
-- EXECUTE is only checked when the trigger is created, so this does not stop the
-- trigger firing. If signup ever breaks, this is the first line to try removing.
revoke execute on function public.handle_new_user() from public, anon, authenticated;

-- Backfill: users who signed up before this migration have no app_user row and
-- are still broken. Idempotent, and a no-op on a fresh database.
insert into public.app_user (id, email, created_at)
select u.id, u.email, now()
from auth.users u
where u.email is not null
on conflict (id) do nothing;
