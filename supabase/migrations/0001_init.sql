-- 0001_init.sql — initial StyleOS schema
--
-- Source of truth: docs/02-data-model.md
--
-- Deviations from that doc, all deliberate:
--   * `user` is renamed `app_user` — `user` is a reserved keyword in Postgres.
--   * Value domains stated in the doc's notes column are enforced as CHECK constraints.
--   * RLS is enabled on every table with no policies yet (deny-by-default). The engine
--     is unaffected: it connects with the service-role key, which bypasses RLS.
--   * FKs cascade along the user-ownership chain only. outfit_item.garment_id is
--     RESTRICT so outfit history cannot be silently rewritten by a garment delete.
--   * outfit_item gets a composite primary key; the doc specifies no key for it.

create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- app_user  (doc: `user`)
-- ---------------------------------------------------------------------------
create table app_user (
  id         uuid primary key references auth.users (id) on delete cascade,
  email      text        not null,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- body_profile — one per user. An aid to scoring, never a hard filter.
-- ---------------------------------------------------------------------------
create table body_profile (
  user_id       uuid primary key references app_user (id) on delete cascade,
  height_cm     int,
  body_type     text,
  preferred_fit text,
  notes         text
);

-- ---------------------------------------------------------------------------
-- style_dna — one per user. Learned preference weights + display descriptors.
-- ---------------------------------------------------------------------------
create table style_dna (
  user_id     uuid primary key references app_user (id) on delete cascade,
  weights     jsonb       not null default '{}'::jsonb,
  descriptors text[]      not null default '{}',
  updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- garment
-- color_primary / color_secondary are numeric jsonb ({h,s,l} or LAB), never
-- color-name strings — colour-harmony scoring is arithmetic on these values.
-- ---------------------------------------------------------------------------
create table garment (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid        not null references app_user (id) on delete cascade,
  image_url       text        not null,
  category        text        not null
                  check (category in ('top', 'bottom', 'outerwear', 'shoes', 'accessory')),
  subcategory     text,
  color_primary   jsonb       not null,
  color_secondary jsonb,
  material        text,
  fit             text,
  pattern         text,
  formality       int         not null check (formality between 1 and 5),
  seasons         text[]      not null default '{}',
  style_tags      text[]      not null default '{}',
  occasion_tags   text[]      not null default '{}',
  tag_source      text        not null check (tag_source in ('ai', 'user_corrected')),
  embedding       vector,
  created_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- recommendation — one row per POST /recommend. This is the "shown" record:
-- the denominator of acceptance_rate = accepted / shown.
--
-- seq_no is assigned server-side by the engine inside the insert transaction
-- as max(seq_no) + 1 for that user; the unique constraint below is what makes
-- that safe. It is never client-supplied.
--
-- latency_ms is nullable by design: the engine writes this row *before* the
-- pipeline runs (so the row survives an engine error) and fills latency in
-- afterwards.
-- ---------------------------------------------------------------------------
create table recommendation (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid        not null references app_user (id) on delete cascade,
  occasion   text        not null,
  context    jsonb       not null default '{}'::jsonb,
  seq_no     int         not null,
  latency_ms int,
  created_at timestamptz not null default now(),
  unique (user_id, seq_no)
);

create index recommendation_user_created_idx on recommendation (user_id, created_at);

-- ---------------------------------------------------------------------------
-- outfit
-- No user_id, occasion or context here — they belong to the parent
-- recommendation and are reached by join. Two copies would disagree.
-- ---------------------------------------------------------------------------
create table outfit (
  id                uuid primary key default gen_random_uuid(),
  recommendation_id uuid   not null references recommendation (id) on delete cascade,
  rank              int    not null check (rank between 1 and 3),
  score             double precision not null,
  confidence        int    not null check (confidence between 0 and 100),
  weakest_factor    text,
  reasons           jsonb  not null default '[]'::jsonb,
  unique (recommendation_id, rank)
);

-- ---------------------------------------------------------------------------
-- outfit_item
-- garment_id is RESTRICT: deleting a garment that appears in a past outfit is
-- refused, so recommendation history stays intact for the evaluation queries.
-- `role` gets no CHECK — the doc's list of roles is open-ended.
-- ---------------------------------------------------------------------------
create table outfit_item (
  outfit_id  uuid not null references outfit (id) on delete cascade,
  garment_id uuid not null references garment (id) on delete restrict,
  role       text not null,
  primary key (outfit_id, garment_id)
);

-- ---------------------------------------------------------------------------
-- feedback_event — append-only. Never updated, never deleted; the timeline is
-- what makes before/after learning analysis possible.
--
-- There is no 'ignored' signal. An ignored recommendation is one with zero
-- feedback events, derived at query time. Writing an 'ignored' row would need
-- a timer to decide when "no answer yet" becomes "no".
--
-- unique (outfit_id, signal): a user may both like and accept the same outfit,
-- but cannot accept it twice.
-- ---------------------------------------------------------------------------
create table feedback_event (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid        not null references app_user (id) on delete cascade,
  outfit_id  uuid        not null references outfit (id) on delete cascade,
  signal     text        not null check (signal in ('accepted', 'liked', 'disliked')),
  created_at timestamptz not null default now(),
  unique (outfit_id, signal)
);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- Enabled with no policies: deny-by-default for the anon and authenticated
-- keys. The engine's service-role key bypasses RLS entirely, so the engine is
-- unaffected. Policies for direct web-app reads land in a later migration.
-- ---------------------------------------------------------------------------
alter table app_user       enable row level security;
alter table body_profile   enable row level security;
alter table style_dna      enable row level security;
alter table garment        enable row level security;
alter table recommendation enable row level security;
alter table outfit         enable row level security;
alter table outfit_item    enable row level security;
alter table feedback_event enable row level security;
