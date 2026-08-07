# StyleOS — CLAUDE.md

## What this is
A full-stack wardrobe recommendation platform: Next.js BFF + FastAPI engine + Supabase (Postgres/storage/auth). Four intelligence layers: Perception (CV tagging), Reasoning (deterministic scoring), Styling (bounded LLM rerank), Personalization (Style DNA feedback loop).

---

## Non-negotiable invariants

### 1. `user_id` auth boundary
`user_id` never appears in a request body or query string going to the FastAPI engine. Identity is derived exclusively from the verified Supabase JWT (`Authorization: Bearer <jwt>`). A body-supplied `user_id` is a spoofing hole — reject with 401 if a caller tries it.

### 2. Repository module pattern
All engine DB access goes through a single `repository` module in `engine/`. Every function in that module takes `user_id` as its first required argument. No ad-hoc queries anywhere else in the engine. The engine uses the Supabase service-role key (bypasses RLS), so tenant isolation is the engine's own responsibility, enforced exclusively through this module.

### 3. Numeric color storage
Colors are stored as `{h, s, l}` or LAB triples in `jsonb` — never as color-name strings. Color-harmony scoring is arithmetic on these numbers. String matching is not a substitute.

### 4. LLM rerank-only role
The LLM receives the top ~15–20 already-scored, already-valid candidates and returns structured JSON: reranked top 3 + per-item reasons + tweak suggestions. It cannot add garments the user does not own and cannot override hard constraints. The deterministic pipeline runs fully before the LLM is called.

### 5. No `ignored` feedback signal
`feedback_event.signal` accepts `accepted`, `liked`, `disliked` only. An ignored recommendation is one with zero feedback events — derived at query time as the missing denominator entry. Never write an `ignored` row; that would require a timer to decide when "no answer yet" becomes "ignored", infrastructure v1 must not carry.

### 6. `seq_no` assignment
`recommendation.seq_no` is assigned server-side inside the insert transaction as `max(seq_no) + 1` for that user. It is never client-supplied. The `unique (user_id, seq_no)` constraint enforces this. Before/after learning comparison is `WHERE seq_no <= N` vs `WHERE seq_no > N` — stable even if rows are ever backfilled.

### 7. Degradation behavior
The LLM is on the critical path; it must fail soft:
- **LLM timeout/failure** → return the deterministic top 3 with mechanically-generated reasons from the per-factor score breakdown. Set `degraded: true` in the response. The client sees the same shape.
- **Weather lookup failure** → proceed with neutral context, drop `weatherFit` from scoring, renormalize remaining weights.
- **Wardrobe too small to fill required roles** → return fewer than 3 outfits with an explicit reason field. Never return a 500.

Every external call (CV, LLM, weather) goes through a typed adapter with an explicit timeout and retry policy.

---

## Data model essentials

| Table | Key constraint |
|---|---|
| `recommendation` | `unique(user_id, seq_no)` — the shown-record denominator for acceptance rate |
| `outfit` | `unique(recommendation_id, rank)` — no duplicate ranks |
| `feedback_event` | `unique(outfit_id, signal)` — append-only, never mutated |
| `garment` | `color_primary` always populated as jsonb numeric |

`outfit` does not duplicate `user_id` or `occasion` — those are on the parent `recommendation`. Reach them via join; two copies will disagree.

`feedback_event` is append-only. The timeline is what makes before/after analysis possible.

The users table is `app_user` — `user` is a reserved keyword in Postgres. Deletes cascade along user ownership only: `outfit_item.garment_id` is `on delete restrict`, so a garment appearing in any past outfit cannot be deleted. Recommendation history must stay intact for the evaluation queries.

---

## Acceptance rate query pattern

```sql
-- acceptance rate for user's first N recommendations
select count(*) filter (where accepted)::float / nullif(count(*), 0)
from (
  select r.id,
         exists (
           select 1 from outfit o
           join feedback_event f on f.outfit_id = o.id
           where o.recommendation_id = r.id and f.signal = 'accepted'
         ) as accepted
  from recommendation r
  where r.user_id = $1 and r.seq_no <= $2
) t;
```
Swap `<=` for `>` to get the later window. `improvement = later_rate - early_rate`. Always state n alongside the number.

---

## API contracts

### FastAPI engine (never called from the browser)
All routes except `GET /health` require both `Authorization: Bearer <supabase_jwt>` and `X-Service-Token: <shared_secret>`. The engine verifies the JWT against `SUPABASE_JWT_SECRET` and derives `user_id` from claims.

`POST /recommend` body — note no `user_id`:
```json
{ "occasion": "date", "context": { "temp_c": 31, "rain": false } }
```
Response must include `recommendation_id`, `latency_ms`, `degraded` (bool), and `outfit_id` per outfit (the feedback handle).

`POST /feedback` body: `{ "outfit_id": "uuid", "signal": "accepted" }`. Returns updated Style DNA descriptors immediately.

`GET /metrics` — authenticated, user-scoped. Returns acceptance rates and improvement.

### Next.js BFF
`POST /api/recommend` — thin proxy: gathers weather/context server-side, attaches JWT + service token, calls engine. Never exposes engine URL to the client.
`POST /api/feedback` — proxy to engine.
`PATCH /api/garments/:id` — sets `tag_source='user_corrected'` when user edits AI tags.

---

## Scoring weights (engine/scoring)
```
score = w_color * colorHarmony
      + w_formal * formalityCoherence
      + w_occasion * occasionFit
      + w_weather * weatherFit
      + w_season * seasonFit
      + w_body * bodyCompatibility
      + w_pref * personalization
```
`bodyCompatibility` and `personalization` are deliberately weighted below `occasion` + `weather` so the system stays practical. `confidence` (0–100) derives from the engine score, not the LLM. `weakest_factor` names the factor that capped confidence.

---

## Preference learning (Style DNA)
On each `feedback_event`: accepted/liked → nudge up attribute weights (colors, style tags, fits, formality band); disliked → nudge down; ignored (no event) → small passive decay applied at learning time. Small fixed learning rate. Every update is loggable.

---

## Conventions

### `web/` (Next.js + TypeScript)
- App Router. API routes are the BFF — they own auth, context gathering, and proxying to the engine.
- Never call the engine directly from client components. Never expose the engine URL or service token to the browser.
- CV tagging and background removal happen server-side in `POST /api/garments`.
- `tag_source` must be set to `'ai'` on upload and `'user_corrected'` on any user edit.
- `DELETE /api/garments/:id` can legitimately fail — a garment used in a past outfit is FK-protected. Return a conflict, never a 500, and surface it in the wardrobe UI.
- Mobile-first responsive. Visual polish budget goes to Home/Today and Request → Recommendation screens, plus the two signature interactions (AI-thinking progress, memory-card wardrobe).

### `engine/` (FastAPI + Python)
- All DB access through `repository/`. Functions are `def get_garments(user_id: str, ...) -> list[Garment]` — `user_id` always first.
- Candidate generation → scoring → LLM rerank is a pipeline; each stage is a separate module.
- LLM call is wrapped in a typed adapter with timeout. On failure, fall through to templated-reason fallback; set `degraded=True`.
- `recommendation` row is written before the engine pipeline runs (so latency can be measured and the row exists even if the engine errors). `latency_ms` is updated after.
- `feedback_event` rows are never updated or deleted.

### Supabase / migrations
- RLS policies apply to everything the web app reads with the user token. Engine bypasses RLS via service-role key.
- As of `0001_init.sql` RLS is enabled on all eight tables with **zero policies** — deny-by-default. The engine is unaffected; direct web-app reads return nothing until a follow-up migration adds policies.
- `embedding` column on `garment` is nullable — include it now, leave it null until pgvector "similar item" feature is added.
- Migrations go in `supabase/migrations/`. Never alter production tables outside a migration file.
