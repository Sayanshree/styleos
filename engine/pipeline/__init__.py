"""Recommendation pipeline.

Stages (docs/03-recommendation-engine.md):

    0. Intent extraction (LLM call #1)     pipeline.intent
    1. Resolve target profile              — intent object from step 0
    2. Candidate generation                pipeline.candidates
    3. Score each candidate                pipeline.scoring
    4. Top N                               — slice in the router
    5. MMR diversity                       pipeline.diversity
    6. LLM stylist (call #2)               pipeline.stylist
    7. Engine applies modifications        pipeline.stylist.apply_modifications
    8. Persist + return                    — repository + router

Each stage is a separate module with a clear interface. The router in
app/routers/recommend.py orchestrates them.
"""
