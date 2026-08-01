# StyleOS — User Flows & Screens

The v1 surface is small on purpose. Six screens, two signature interactions. This doc is also the brief for the UI design.

## Core screens

**1. Onboarding**
Purpose: get a wardrobe fast, or skip straight to the demo.
Elements: brief value line, "upload wardrobe photos", "load sample closet" (one-click demo), optional body-profile step (skippable).
Actions: upload · load sample · skip.

**2. Wardrobe (with add-clothes maintenance)**
Purpose: view and maintain the closet. This is Flow 2's home — adding clothes updates state, it does **not** trigger a recommendation.
Elements: garment grid/cards, add button, per-item detail with editable tags (the correction UI).
Actions: add garment · edit tags · delete.

**3. Home / "Today"**
Purpose: the landing surface — feels alive.
Elements: greeting, current weather, a prompt to ask for an outfit, entry to recommendations. (Calendar/morning-push are vision, not v1 — keep this simple.)
Actions: start a request.

**4. Request → Recommendation**
Purpose: the product moment. Flow 1.
Elements: occasion input (chips + free text), then top 3 outfit cards — each with the garments, a confidence score, and per-item "why" reasons. Optional "visualize".
Actions: pick occasion · view outfits · accept/like/dislike.

**5. Feedback (inline on recommendations)**
Purpose: capture the signal that drives learning.
Elements: thumbs up/down / accept on each outfit; a subtle confirmation that Style DNA updated.
Actions: rate outfit.

**6. Style DNA / lightweight analytics**
Purpose: show personalization is real.
Elements: human-readable style descriptors (e.g. minimal, monochrome), most-worn colors, and the evaluation moment — acceptance rate improving after feedback (one small chart).
Actions: view.

## Signature interactions

**"AI is thinking"** — instead of a blank spinner on recommendation, show reasoning progress: reading context → checking weather → matching body profile → scoring outfits → applying Style DNA → done. Increases perceived intelligence and trust. (Steps can be parallel internally.)

**Memory-card wardrobe** — display garments as timeline cards ("Beige blazer · added from shopping trip · July") so the closet feels alive and each item has a story, rather than a flat grid.

## Design priorities
Invest visual polish in the two hero screens — **Home/Today** and **Request → Recommendation** — plus the two signature interactions. The rest can be clean and functional. Mobile-first responsive; ship as web.
