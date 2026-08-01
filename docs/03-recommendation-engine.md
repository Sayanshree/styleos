# StyleOS — Recommendation Engine Design

The centerpiece. Lives in the **FastAPI service**. Split cleanly: a deterministic algorithm produces *valid, scored* outfits (Reasoning), then a bounded LLM reranks and explains (Styling). The LLM never invents outfits from scratch.

## Pipeline

```
Request (occasion + context)
        ↓
1. Resolve target profile        → formality range, seasons, style vibe
        ↓
2. Generate candidate outfits    → one item per required role, pruned
        ↓
3. Score each candidate          → weighted multi-factor score
        ↓
4. Take top N (~15–20)
        ↓
5. LLM stylist rerank + explain  → top 3, per-item reasons, confidence
        ↓
Return top 3 outfits
```

## 1. Target profile
Map the occasion to a target: `{ formality_range, allowed_seasons, style_vibe }`. Merge in live context (temperature, rain) so weather can shift fabric/layer preferences. Occasions are a small config table so they're easy to tune.

## 2. Candidate generation
Cartesian combination of one garment per required role (top, bottom, shoes, + optional outerwear/accessory), **pruned early**:
- drop garments failing hard constraints (wrong season for the weather, category absent).
- cap combinations; if the closet is large, sample or greedily pre-filter per role by single-item fit to the target before combining.

For portfolio-scale wardrobes brute force + pruning is fine; document the cutoff where you'd switch to sampling.

## 3. Scoring
Each candidate gets a normalized weighted score:

```
score = w_color   * colorHarmony(items)
      + w_formal  * formalityCoherence(items, target)
      + w_occasion* occasionFit(items, target)
      + w_weather * weatherFit(items, context)
      + w_season  * seasonFit(items, target)
      + w_body    * bodyCompatibility(items, bodyProfile)
      + w_pref    * personalization(items, styleDNA.weights)
```

- **colorHarmony** — computed in HSL/LAB: reward analogous / complementary / neutral pairings, penalize clashes. This is the factor that most rewards storing color numerically.
- **formalityCoherence** — penalize mixing a formality-1 item with a formality-5 item; reward a tight spread near the target.
- **occasionFit / seasonFit** — overlap between item tags and the target.
- **weatherFit** — penalize e.g. suede in rain, heavy layers in heat.
- **bodyCompatibility** — a soft nudge from the body profile (aid, not filter).
- **personalization** — dot product of item attributes with the user's learned Style DNA weights.

Weights `w_*` start as sensible constants and are documented; body/personalization deliberately weighted *below* occasion + weather so the system stays practical and doesn't over-personalize into repetition.

## 4. LLM stylist (bounded)
Input: the top ~15–20 scored candidates (as structured data) + the request + Style DNA descriptors.
Output: **structured JSON only** — the reranked top 3, each with a short per-item reason and any tweak suggestion.

The LLM's role is bounded to *rerank + explain within the valid set*. It cannot add garments the user doesn't own or override hard constraints. This keeps outputs always-valid and testable.

## 5. Confidence
`confidence` (0–100) is derived from the engine, not the LLM: how well the chosen outfit's score meets the target across factors. Surface the weakest factor so "why only 61%?" has a real answer (e.g. "warmer than ideal for the fabric"). This complements explainability directly.

## Preference learning (the Style DNA update)
On each `feedback_event`:
- **accepted / liked** → nudge up the weights of the attributes present in that outfit (colors, style tags, fits, formality band).
- **disliked** → nudge down.
- **ignored** → small decay signal.

Keep it lightweight and explainable — per-attribute weights with a small learning rate; the UI shows the descriptors shifting. Framed formally this is a lightweight contextual bandit; no heavy ML required. Every update is loggable so improvement is measurable (see the evaluation plan).

## Service boundary
The FastAPI service owns: candidate generation, scoring, the LLM rerank call, confidence, preference-weight updates, and the `/metrics` evaluation endpoint. The Next.js app calls it via `POST /recommend` and `POST /feedback`.
