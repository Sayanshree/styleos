# StyleOS — Project Plan

**Type:** Full-stack / product portfolio project
**Goal:** Ship a deployed, working app with one genuinely deep system inside it (the recommendation engine + learning loop), demonstrating full-stack product skill *and* the judgment to build ML into a product.
**Stack (frozen):** Next.js + TypeScript (app) · FastAPI (recommendation + evaluation service) · Supabase (Postgres + object storage + auth) · off-the-shelf multimodal CV APIs · bounded LLM stylist · deployed on Vercel + a Python host (Railway/Render/Fly).

---

## Part A — Vision (north star)

StyleOS is framed not as a fashion chatbot but as a self-maintaining wardrobe *platform* that behaves like a personal stylist — an "operating system for personal fashion." It is built on four independent intelligence layers:

- **Perception** — computer vision understands the user's clothes from photos and keeps the wardrobe current.
- **Reasoning** — a deterministic algorithm generates *practically valid* outfits (never an LLM).
- **Styling** — an LLM reranks the valid candidates, explains them, and suggests tweaks, in a bounded role.
- **Personalization** — every interaction updates a higher-level "Style DNA," so recommendations become uniquely the user's over time.

The long-term roadmap (explicitly beyond v1) adds a proactive lifestyle assistant and advanced AI: weather + calendar awareness, morning outfit notifications, packing assistant, wardrobe analytics, gap analysis, shopping suggestions, trend intelligence, outfit visualization, and re-identifying existing garments from mirror selfies.

This vision doc exists to show ambition and direction. It is **not** the build scope.

---

## Part B — v1 build scope (what actually gets built)

v1 proves the full four-layer loop end to end, once, through **two flows** sharing one engine.

**Flow 1 — Recommendation (the product):**
Request ("I have a date tonight") → weather + occasion context → recommendation engine → AI stylist → top 3 outfits with confidence + explanations → feedback.

**Flow 2 — Wardrobe maintenance (perception):**
Photo uploaded → CV pipeline (tag, background-removal, dedupe-check) → saved to the self-updating wardrobe / structured database. This updates shared state only; **it does not trigger a recommendation.** (Adding clothes and asking for an outfit are separate intents.)

Feedback from Flow 1 loops into preference learning and the Style DNA the engine reads from.

### In scope
- Garment upload + automatic tagging (off-the-shelf multimodal API) + a correction UI
- Structured wardrobe database
- Self-reported body profile feeding the engine
- Algorithmic recommendation engine with real multi-factor scoring
- Bounded LLM stylist: reranks candidates, explains picks, returns a confidence score
- Thumbs up/down feedback → per-attribute preference weights → visible Style DNA
- **Lightweight evaluation:** acceptance rate + before/after-learning improvement (the "I build ML into products" proof)
- Two signature UI touches: "AI is thinking" progress and the memory-card wardrobe
- Deployed, public demo with a one-click "load sample closet"

### Explicit non-goals (deferred to the vision)
Re-identifying garments from mirror selfies · duplicate detection at scale · calendar integration · morning push notifications · packing assistant · analytics beyond Style DNA · wardrobe gap analysis · shopping assistant · trend intelligence · outfit visualization/generation · native mobile apps · training any CV model.

---

## Success criteria (v1)

1. A reviewer opens the live link and gets an explained recommendation within ~15 seconds using the sample closet.
2. Recommendations are visibly *reasoned* — every pick has a defensible explanation and a confidence score.
3. The feedback loop produces a *measurable* change: acceptance rate improves after learning, shown in a small metrics view.
4. The README leads with the four-layer architecture and the two-flow diagram, live demo linked at the top.
