-- 0002_rls_policies.sql — owner-only RLS policies
--
-- 0001_init.sql enabled RLS on all eight tables and created zero policies, leaving
-- everything locked to the anon and authenticated keys. This migration opens the
-- minimum needed for the trust boundary in docs/04-architecture-api.md.
--
-- No new roles, no admin bypass, no public-read. `authenticated` is Supabase's
-- built-in role, not one invented here.
--
-- VERB COVERAGE
--   select          — all eight tables, owner-scoped (defence in depth).
--   insert / update — app_user, body_profile, style_dna, garment.
--   delete          — body_profile, style_dna, garment. Deliberately NOT app_user:
--                     account deletion goes through the service role only, never
--                     self-serve from a browser token.
--
-- recommendation, outfit, outfit_item and feedback_event deliberately get NO write
-- policies. The engine writes them with the service-role key, which bypasses RLS
-- entirely, so it is unaffected. Withholding these grants is what keeps
-- feedback_event append-only and recommendation.seq_no unforgeable from a browser
-- token — both stated invariants in docs/02-data-model.md.
--
-- OWNERSHIP PATHS
--   app_user                       auth.uid() = id   (this table keys on `id`, not `user_id`)
--   body_profile / style_dna /
--   garment / recommendation /
--   feedback_event                 direct user_id column
--   outfit                         -> recommendation.user_id            (1 hop)
--   outfit_item                    -> outfit -> recommendation.user_id  (2 hops)
--
-- outfit_item is reached through its parent outfit rather than through garment.
-- garment is a reference, not a parent: keying off it would make a row's visibility
-- depend on the item it points at instead of the outfit it belongs to, and would
-- expose another user's outfit_item rows the moment their outfit referenced one of
-- your garments. Both hops are index-backed — outfit.recommendation_id by
-- unique (recommendation_id, rank), outfit_item.outfit_id as the leading column of
-- the composite primary key.
--
-- RULE FOR FUTURE INSERT GRANTS
-- If insert is ever granted on a table that references another user-owned row, the
-- `with check` must also verify that referenced row belongs to the caller — a
-- user_id-only check would let a caller attach their row to someone else's outfit
-- or garment. This bites on feedback_event.outfit_id and outfit_item.garment_id.
-- It is stated rather than written because no insert granted below references a
-- foreign user-owned row, so there is currently nothing for it to check.
--
-- auth.uid() is wrapped as (select auth.uid()) so Postgres evaluates it once per
-- statement instead of once per row.

-- ---------------------------------------------------------------------------
-- app_user — keys on `id`, not `user_id`
--
-- There is deliberately no delete policy here. Deleting an app_user row cascades
-- away the user's wardrobe, recommendations, outfits and entire feedback history,
-- and leaves an orphaned auth.users row behind (the FK points app_user ->
-- auth.users, not the reverse). That is too large a blast radius to reach from a
-- browser token, so account deletion is service-role only.
-- ---------------------------------------------------------------------------
create policy app_user_select on app_user
  for select to authenticated
  using ((select auth.uid()) = id);

create policy app_user_insert on app_user
  for insert to authenticated
  with check ((select auth.uid()) = id);

create policy app_user_update on app_user
  for update to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

-- ---------------------------------------------------------------------------
-- body_profile
-- ---------------------------------------------------------------------------
create policy body_profile_select on body_profile
  for select to authenticated
  using ((select auth.uid()) = user_id);

create policy body_profile_insert on body_profile
  for insert to authenticated
  with check ((select auth.uid()) = user_id);

create policy body_profile_update on body_profile
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy body_profile_delete on body_profile
  for delete to authenticated
  using ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- style_dna
-- The engine writes this on every feedback event via the service-role key; these
-- policies exist so the UI can read descriptors and weights with the user's token.
-- ---------------------------------------------------------------------------
create policy style_dna_select on style_dna
  for select to authenticated
  using ((select auth.uid()) = user_id);

create policy style_dna_insert on style_dna
  for insert to authenticated
  with check ((select auth.uid()) = user_id);

create policy style_dna_update on style_dna
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy style_dna_delete on style_dna
  for delete to authenticated
  using ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- garment — the one table with full CRUD from the browser (wardrobe maintenance)
--
-- The `with check` on update is what stops a garment being reassigned to another
-- user by rewriting user_id.
-- ---------------------------------------------------------------------------
create policy garment_select on garment
  for select to authenticated
  using ((select auth.uid()) = user_id);

create policy garment_insert on garment
  for insert to authenticated
  with check ((select auth.uid()) = user_id);

create policy garment_update on garment
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy garment_delete on garment
  for delete to authenticated
  using ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- recommendation — read-only to the user token.
-- seq_no is assigned server-side by the engine and must not be client-settable.
-- ---------------------------------------------------------------------------
create policy recommendation_select on recommendation
  for select to authenticated
  using ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- outfit — read-only. No user_id column; ownership resolves through the parent
-- recommendation.
-- ---------------------------------------------------------------------------
create policy outfit_select on outfit
  for select to authenticated
  using (
    exists (
      select 1
      from recommendation r
      where r.id = outfit.recommendation_id
        and r.user_id = (select auth.uid())
    )
  );

-- ---------------------------------------------------------------------------
-- outfit_item — read-only. Ownership resolves through outfit -> recommendation,
-- deliberately not through garment. See the header note.
-- ---------------------------------------------------------------------------
create policy outfit_item_select on outfit_item
  for select to authenticated
  using (
    exists (
      select 1
      from outfit o
      join recommendation r on r.id = o.recommendation_id
      where o.id = outfit_item.outfit_id
        and r.user_id = (select auth.uid())
    )
  );

-- ---------------------------------------------------------------------------
-- feedback_event — read-only, and read-only is load-bearing. This table is
-- append-only by design (docs/02-data-model.md): granting update or delete here
-- would let a user retract a dislike and rewrite their own learning history.
-- Inserts go through the engine via POST /api/feedback.
--
-- user_id is denormalized onto this table on purpose, so no join is needed.
-- ---------------------------------------------------------------------------
create policy feedback_event_select on feedback_event
  for select to authenticated
  using ((select auth.uid()) = user_id);
