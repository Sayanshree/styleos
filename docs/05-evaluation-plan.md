# StyleOS — Evaluation Plan

This is the doc that turns "I called an API" into "I can build ML into a product." Keep it small, but build it in from the start — it depends entirely on `recommendation` and `feedback_event` being logged from day one.

## Metrics

- **Acceptance rate** — recommendations with at least one accepted outfit ÷ total recommendations. The headline number. Measured per *recommendation*, not per outfit: the user is shown three options, and picking any one of them is a success.
- **Like rate** — liked vs disliked among rated outfits.
- **Learning improvement** — acceptance rate over the user's *first N* recommendations vs their *later* ones. This is the proof the system adapts.
- **Recommendation latency** — `recommendation.latency_ms`, written by the engine on every call (shows you care about performance).
- **CV correction rate** — share of garments where the user edited an AI tag (`tag_source='user_corrected'` / total). A perception-quality signal.

## How it's measured

Every `POST /recommend` writes a `recommendation` row carrying `seq_no` (the nth recommendation for that user) and `latency_ms`. Every user response writes a timestamped `feedback_event` against an `outfit_id`. Because `seq_no` is assigned at write time and `feedback_event` is append-only, the before/after comparison is a `WHERE` clause, not extra instrumentation:

```
early  = acceptance_rate(recommendations where seq_no <= N)
later  = acceptance_rate(recommendations where seq_no >  N)
improvement = later - early
```

Ignored recommendations need no special handling: a recommendation with no feedback events is an ignored one, counted in the denominator and not the numerator. Nothing writes an `ignored` row, so no timer or cron job is required to decide when "no answer yet" becomes "no."

See the data model doc for the concrete SQL.

Exposed via the FastAPI `GET /metrics` endpoint, authenticated and scoped to the calling user.

## The demo moment
A small **metrics view** in the app (or the README) that shows acceptance rate and the early-vs-later improvement, ideally as one simple chart. During a portfolio review this is the 20-second moment that says the personalization is real, not decorative. Seed the sample account with enough feedback history that the improvement is visible on first load — that means seeding `recommendation` rows with sensible `seq_no` values, not just feedback events.

## Scope discipline
No A/B framework, no offline eval harness, no fancy statistics. One honest, visible before/after number plus latency is exactly right for a portfolio — it demonstrates the *instinct* to measure your own system, which is the signal that matters.

State the sample size next to the number. With a handful of recommendations per window the improvement is noise, and a reviewer who notices you claimed a trend from n=6 will trust the rest of the project less. "Acceptance up from 41% to 68% (n=22 / n=31)" is honest and costs you nothing.
