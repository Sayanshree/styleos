# StyleOS — Architecture & API

## Components

- **Next.js + TypeScript app** — frontend (mobile-first responsive) + API routes acting as the backend-for-frontend. Owns auth, wardrobe CRUD, CV orchestration, image storage, and calling the engine service.
- **FastAPI service (Python)** — owns the recommendation engine, preference learning, and evaluation metrics. Stateless except for reading/writing via the DB.
- **Supabase** — Postgres, object storage (garment images), and auth in one.
- **CV APIs (off-the-shelf)** — a multimodal model for garment tagging + a hosted background-removal API. Wrapped in a thin adapter.
- **LLM API** — the bounded stylist (structured JSON output).

## Trust boundary

The engine is **server-side only**. It is never called from the browser, has no public route in the app's DNS, and every request to it carries two credentials:

| Header | Purpose |
|---|---|
| `Authorization: Bearer <supabase_jwt>` | The end user's identity. The engine verifies it against `SUPABASE_JWT_SECRET` and derives `user_id` from the claims. |
| `X-Service-Token: <shared_secret>` | Proves the caller is the Next.js BFF, not an arbitrary client that got hold of a user JWT. Defence in depth. |

**`user_id` never appears in a request body or query string.** A body-supplied `user_id` is a spoofing hole: anyone who reaches the service could read or write another user's wardrobe. Identity comes from the verified token or the request is rejected with 401.

The engine authenticates to Postgres with the Supabase **service-role key**, which bypasses RLS. That is acceptable for a trusted service, but it makes tenant isolation the engine's own responsibility: all engine DB access goes through a single `repository` module whose every function takes `user_id` as its first required argument. No ad-hoc queries elsewhere. RLS policies remain in force for everything the web app reads directly with the user's own token.

## Two flows

**Wardrobe maintenance:** client uploads photo → Next.js sends it to the background-removal + tagging adapter → structured attributes returned → saved as a `garment` (with `tag_source='ai'`) → correction UI lets the user fix tags. Updates state only; no recommendation fired.

**Recommendation:** client sends a request (occasion + optional context) → Next.js gathers weather/context, attaches the user's JWT and the service token, and calls the FastAPI `POST /recommend` → engine writes a `recommendation` row, generates and scores candidates, calls the LLM stylist to rerank → returns top 3 outfits → rendered with confidence + reasons → user feedback posts back to `POST /feedback` → preference weights + Style DNA update.

Refer to the two-flow diagram for the shared-engine view.

## Degradation

The LLM sits on the critical path of the one moment the product exists to deliver. It must fail soft, from the first version:

- **LLM call fails or exceeds its timeout** → return the deterministic top 3, with reasons generated from the per-factor score breakdown. The engine already has every number needed to write "strong colour match, slightly warm for the fabric" mechanically. The response is degraded, not absent, and the client can't tell the difference structurally.
- **Weather lookup fails** → proceed with a neutral context and drop `weatherFit` from the score, renormalizing the remaining weights.
- **Wardrobe too small to fill the required roles** → return fewer than 3 outfits with an explicit reason, never a 500.

Every external call (CV, LLM, weather) goes through a typed adapter with an explicit timeout and retry policy.

## Ownership split

| Concern | Owner |
|---|---|
| Auth, sessions, JWT issuance | Next.js + Supabase |
| JWT verification, tenant isolation | FastAPI |
| Garment upload, storage, CRUD, correction | Next.js |
| CV tagging / background removal | Next.js (adapter → CV APIs) |
| Weather/context lookup | Next.js |
| Candidate generation, scoring, rerank, confidence | FastAPI |
| Preference learning / Style DNA update | FastAPI |
| Evaluation metrics | FastAPI |

## API sketch

### Next.js (app / BFF)
- `POST /api/garments` — upload image → CV tag → save. Returns the garment.
- `GET /api/garments` — list wardrobe.
- `PATCH /api/garments/:id` — correct tags (sets `tag_source='user_corrected'`).
- `DELETE /api/garments/:id` — **can fail by design.** `outfit_item.garment_id` is `on delete restrict`, so a garment that has appeared in any past outfit cannot be deleted; recommendation history must not be rewritten by a wardrobe edit. Return a conflict rather than a 500, and have the wardrobe UI surface it instead of assuming success. (A soft-delete flag on `garment` is the natural fix if users find this too restrictive.)
- `GET /api/profile` · `PUT /api/profile` — body profile.
- `GET /api/style-dna` — descriptors + weights for display.
- `POST /api/recommend` — thin proxy: gathers context, forwards credentials, calls FastAPI, returns outfits.
- `POST /api/feedback` — proxy to FastAPI.
- `POST /api/demo/load-sample` — seed the one-click sample closet.

### FastAPI (engine)
- `GET /health` — unauthenticated liveness check. Used by the platform health check and the cold-start ping.
- `POST /recommend`
- `POST /feedback`
- `GET /metrics` — evaluation numbers (see evaluation plan). Authenticated; scoped to the caller.

### Key shapes

`POST /recommend` request — note the absence of `user_id`:
```json
{
  "occasion": "date",
  "context": { "temp_c": 31, "rain": false }
}
```
Response:
```json
{
  "recommendation_id": "uuid",
  "latency_ms": 840,
  "degraded": false,
  "outfits": [
    {
      "outfit_id": "uuid",
      "rank": 1,
      "confidence": 92,
      "items": [
        { "garment_id": "uuid", "role": "top" },
        { "garment_id": "uuid", "role": "bottom" },
        { "garment_id": "uuid", "role": "shoes" }
      ],
      "reasons": [
        "Balances proportions for your body profile",
        "Breathable for a warm evening",
        "Smart-casual, right for a date"
      ],
      "weakest_factor": null
    }
  ]
}
```

`outfit_id` is required in the response — it's the handle the feedback call needs. `degraded: true` signals the stylist fell back to templated reasons; the UI can ignore it, but it belongs in the logs.

`POST /feedback` request:
```json
{ "outfit_id": "uuid", "signal": "accepted" }
```
`signal` is one of `accepted`, `liked`, `disliked`. There is no `ignored` — absence of feedback is the signal. Response: updated Style DNA descriptors so the UI can reflect learning immediately.

## Deployment
- Next.js → **Vercel**
- FastAPI → **Fly.io**, with `min_machines_running = 1`
- Postgres + storage + auth → **Supabase**
- One public URL for the app; the engine service is called server-side only (not exposed to the browser directly).

The always-on machine is deliberate. Render and Railway free tiers spin down after idle and cold-start in 40–60 seconds, which alone breaks the success criterion of an explained recommendation within ~15 seconds — and it would break it precisely when a reviewer opens the link cold. A GitHub Actions cron pinging `/health` every 10 minutes is a workable fallback if Fly's pricing becomes a problem, but pick one and verify it before demo day rather than after.
