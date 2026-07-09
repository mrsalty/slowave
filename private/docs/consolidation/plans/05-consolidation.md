# 05 — Consolidation Improvement Plan

**Status:** planning
**Created:** 2026-07-09
**Depends on:** `core/05-consolidation.md` (rewritten 2026-07-09, Phase 2 complete)

## What's Already Done

Unlike Graph/Salience, consolidation already has substantial micro-benchmark
coverage from prior work (Phase 7 is partially pre-satisfied):

| Test file | Lines | Covers |
|-----------|-------|--------|
| `test_contradiction_support_gate.py` | 162 | support gate, recency gate, full contradiction path, default config values |
| `test_missing_embedding_supersession.py` | 191 | `None` embedding short-circuit (consolidation + `remember()` paths) |
| `test_latent_schema.py` | 484 | `LatentSchemaBuilder` — facets, confidence, temporal anchor |
| `test_contrastive_tfidf.py` | 134 | lexical signature scoring |
| `test_schema_utility.py` | 274 | schema utility score, decay |
| `test_engine_consolidate.py` | 225 | end-to-end `consolidate_once()` |

**Gap:** No diagnostic instrumentation exists. `ConsolidationStats` has 5 raw
counters (`schemas_created/reinforced/contradicted/skipped`, `prototypes_processed`)
but no verdict-distribution breakdown, no near-dup-vs-judge split, and no
benchmark wires these into its summary JSON (unlike the `diagnostics` block
`iteration-strategy.md` specifies). Phase 4 starts from zero here.

## Priority Finding (motivates Q1 below)

The near-duplicate guard (Phase 3a, cosine ≥ 0.92) runs **before** the
geometric judge (Phase 4) is ever reached, and `reinforce_schema()` never
overwrites `content_text` — it only merges evidence/salience/confidence
(`schema_store.py:475-513`). If an old and new claim about the *same slot*
(e.g. a preference value that changed) happen to embed at cosine ≥ 0.92 —
plausible when only one or two tokens differ ("budget is $50/month" →
"budget is $80/month") — the update is silently absorbed as reinforcement
of the **stale** claim, and the geometric judge never sees it. This is a
structural risk specifically for the StaleMemory benchmark's drift scenarios
(pre-drift and post-drift statements about the same attribute are often
near-paraphrases). Nothing in the current design or tests establishes
whether this actually happens on real data — it's untested, not confirmed.

## Diagnostic Questions

| # | Question | Why It Matters |
|---|----------|-----------------|
| Q1 | On StaleMemory drift scenarios, what fraction of post-drift statements are intercepted by the near-dup guard (cosine ≥ 0.92) before reaching the geometric judge? | If non-trivial, the near-dup guard is silently defeating contradiction detection — architectural fix (e.g. route near-dups through the judge too when the two texts differ lexically) needed, not tuning |
| Q2 | What is the full verdict distribution (unrelated / reinforces / refines / contradicts) on LoCoMo + StaleMemory? | `ConsolidationStats` only tracks `schemas_contradicted`; "reinforces" vs "refines" vs "unrelated" is currently invisible. If contradicts ≈ 0 across both, the judge's contradiction path is dead weight on real data (only exercised by synthetic unit tests) |
| Q3 | Of verdicts that reach `"contradicts"`, what fraction are downgraded to `"reinforced"` by the support gate (`min_support_to_supersede=2`) vs the recency gate (`min_time_delta_to_supersede_s=3600`)? | Tells us which gate is actually load-bearing on real ingestion cadence — session-spaced data may never trip the recency gate, making it decorative |
| Q4 | Does StaleMemory `detection_rate` (post-drift recall) improve when the near-dup guard is disabled (cosine → 1.01, i.e. never fires) vs default 0.92? | Direct behavioral test of the Priority Finding — isolates whether near-dup absorption vs. judge accuracy is the bottleneck |
| Q5 | Is `variance_floor=1e-2` calibrated correctly on *real* prototype clusters (not just the synthetic ones in `test_latent_schema.py`)? What's the actual confidence histogram from a live LoCoMo run? | Doc claims tight clusters → conf≈0.97, loose → conf=0.0, but this was derived analytically, never measured on live data (mirrors the salience `tau_seconds` lesson — hand-picked constants that were never swept) |
| Q6 | Does `same_topic_cosine=0.75` correctly gate StaleMemory's paired (pre-drift, post-drift) statements into the judge rather than "unrelated"? | If pre/post drift centroids fall below 0.75 (topic drifted further than expected), the judge never even considers them — schemas are just created side-by-side with no relation edge, and retrieval must disambiguate unaided |
| Q7 | Does `contradicts_facet_dist=0.35` separate genuine contradictions from `"refines"` on real (not synthetic) facet axes, given facets require ≥3 members and most consolidated prototypes may have fewer? | `min_members_for_facets=3` — if the median prototype has <3 members, facet distance is always 0.0 and the judge can never route to `"contradicts"` via Step 3, only via the ≥0.95 reinforce/< 0.75 unrelated bounds |

## Threshold Ablation Matrix

No boolean flags exist in this module (see `core/05-consolidation.md`
Configuration) — every knob is a continuous threshold. "Ablation" here means
pushing each threshold to an extreme that functionally disables the gate it
implements, run on LoCoMo limit=3 (structure) + StaleMemory limit=50/attribute
(contradiction behavior, per Q4/Q6):

| # | near_dup_cos | related_cos | same_topic_cos | reinforce_cos | facet_dist | support_gate | time_gate_s | Eval | Disables |
|---|------|------|------|------|------|------|------|------|----------|
| B1 | 0.92 | 0.72 | 0.75 | 0.95 | 0.35 | 2 | 3600 | LoCoMo+StaleMemory | **baseline** |
| B2 | 1.01 | 0.72 | 0.75 | 0.95 | 0.35 | 2 | 3600 | StaleMemory | near-dup guard (Q1/Q4) |
| B3 | 0.92 | 1.01 | — | — | — | 2 | 3600 | LoCoMo | related-schema lookup → geometric judge never reached |
| B4 | 0.92 | 0.72 | 0.99 | 0.95 | 0.35 | 2 | 3600 | StaleMemory | topic gate → everything "unrelated" (Q6) |
| B5 | 0.92 | 0.72 | 0.75 | 1.01 | 0.35 | 2 | 3600 | LoCoMo | reinforce band → more schemas reach facet-distance test |
| B6 | 0.92 | 0.72 | 0.75 | 0.95 | 0.99 | 2 | 3600 | StaleMemory | contradiction path → everything "refines" |
| B7 | 0.92 | 0.72 | 0.75 | 0.95 | 0.35 | 1 | 3600 | StaleMemory | support gate (Q3) |
| B8 | 0.92 | 0.72 | 0.75 | 0.95 | 0.35 | 2 | 1 | StaleMemory | recency gate (Q3) |

Run B1–B4 first (answers Q1/Q4/Q6, the priority finding). B5–B8 only if B1–B4
show the judge path is reachable and meaningfully exercised (Q2 non-trivial).

**UPDATE (2026-07-09, after B1/B2 ran):** B1 and B2 are done (`near_dup_guard_cosine`
now exposed via `SlowaveConfig.judge`, see `PROGRESS.md`) — Priority Finding
refuted, near-dup guard was never the bottleneck. Separately, found and fixed
the actual root cause of `contradicts`=0: the old schema's facet axes were
never persisted retrievably, so `_write_latent_schema` always reconstructed
an empty placeholder, making `contradicts` provably unreachable regardless
of `contradicts_facet_dist`. **Fixed** — facet axes are now persisted
(`schema.sql`, `SchemaStore`), and `contradicts` fires on real data (79/447
on LoCoMo, 41/13,124 on StaleMemory). **B6 (`facet_dist` sweep) is meaningful
again** now that the underlying mechanism actually works — no longer
pointless. B3/B4/B5/B7/B8 (near_dup_cos already covered; related_cos,
same_topic_cos, reinforce_cos, support/recency gates) are still valid and
untried.

## Grid Search

Only after Threshold Ablation confirms a gate matters (Δ > 1pp on its target
benchmark):

- `near_dup_guard_cosine`: **done** — B1 (0.92) vs B2 (1.01/disabled) on StaleMemory limit=15/attribute; see PROGRESS.md. Guard toggling had no effect on detection_rate/stale_rate.
- `same_topic_cosine`: {0.60, 0.70, 0.75, 0.80, 0.85} on StaleMemory — still open
- `contradicts_facet_dist`: {0.20, 0.30, 0.35, 0.40, 0.50} on StaleMemory — now meaningful (facet-axis persistence fixed 2026-07-09, `contradicts` is reachable); still open, and worth prioritizing given StaleMemory's 0pp behavioral impact from the fix at the default threshold
- `min_time_delta_to_supersede_s`: {300, 1800, 3600, 7200, 86400} on StaleMemory (session spacing dependent — check actual inter-session gaps in the dataset first, per Q3) — still open, now meaningful since `contradicts` is reachable
- `variance_floor`: {1e-3, 5e-3, 1e-2, 5e-2, 1e-1} — needs Q5's live histogram before picking a range — still open

Script pattern: `private/docs/consolidation/scripts/grid_search_spread_weight.sh` (adapt for consolidation thresholds — new script, e.g. `grid_search_consolidation_thresholds.sh`).

## Diagnostic Instrumentation Spec (Phase 4)

Add to `ConsolidationStats` (or a parallel debug dict, matching the pattern
already used for `_record_debug()`):

```python
verdict_counts: dict[str, int]       # {"unrelated": n, "reinforces": n, "refines": n, "contradicts": n}
near_dup_intercepts: int             # schemas absorbed by 3a before reaching 3b/Phase 4
gate_downgrades: dict[str, int]      # {"support_gate": n, "recency_gate": n}
confidence_histogram: list[float]    # per-prototype conf values, for Q5
```

Wire into `stalememory_eval.py` and `locomo_eval.py` summary JSON under a
`"consolidation"` diagnostics key, mirroring the `iteration-strategy.md`
Layer-1 spec.

## Micro-Benchmark Gap (Phase 7)

Existing 1,470 lines of tests cover the *unit* mechanics (gates, builder
math, TF-IDF, end-to-end wiring) with synthetic fixtures. Missing, and worth
adding once Q1/Q4 are answered:

- `test_near_dup_intercepts_contradiction` — construct two near-duplicate
  (cosine ≥ 0.92) embeddings with *different* claim text representing an
  update; assert whether the guard reinforces the stale one (documents
  current behavior — turns the Priority Finding into a regression-locked
  fact, whichever way it resolves)
- `test_verdict_distribution_bounds` — deterministic fixture with 4 known
  pairs (one per verdict type); assert `judge()` returns the expected
  verdict for each, confirming the doc's threshold boundaries end-to-end
  (currently only support/recency gates have this; reinforces/refines/unrelated
  boundaries are implicitly covered inside `test_latent_schema.py` but not
  asserted as a verdict-distribution table)

Keep new tests deterministic, <5s total, no external data — same bar as
`test_graph_edge_quality.py`.

## Decision Thresholds

| Observed | Action |
|----------|--------|
| Q1: near-dup intercept rate > 10% on StaleMemory pairs | Priority Finding confirmed — route near-dup hits through a lightweight text-diff check before reinforcing; escalate to architecture fix before any threshold tuning |
| Q2: `contradicts` verdict rate ≈ 0 on both LoCoMo and StaleMemory | Judge's contradiction path is real-data dead weight — document and deprioritize further tuning of `contradicts_facet_dist` |
| Q3: recency gate never trips (all Δt > 3600s in real sessions) | Gate is decorative for current data cadence — lower priority for sweeping, note as "safety net for rapid-fire sessions only" |
| Q4: StaleMemory `detection_rate` improves ≥ 2pp with near-dup guard disabled | Confirms guard actively harms drift detection — proceed to grid search on `near_dup_guard_cosine`, considering a lower default |
| Q5: median prototype has < 3 members in live LoCoMo run | Facet axes rarely compute — `contradicts_facet_dist` boundary is rarely reached; contradiction routing is effectively binary (unrelated vs reinforces) most of the time |
| Q6: pre/post-drift centroid cosine falls below 0.75 for > 20% of pairs | `same_topic_cosine` too high for real drift magnitude — lower and re-check Q4 |

## Implementation Order

```
Step 1: Add diagnostic instrumentation (verdict_counts, near_dup_intercepts, gate_downgrades)  [45 min]
Step 2: Wire into stalememory_eval.py + locomo_eval.py summary JSON                            [30 min]
Step 3: Run B1 (baseline) on StaleMemory limit=50/attribute + LoCoMo limit=3                   [10 min]
         ** Q1, Q2, Q3, Q5 answered from one run **
Step 4: Run B2 (near-dup disabled) on StaleMemory                                              [10 min]
         ** Q4 answered — GO/NO-GO gate for Priority Finding **
         -- If Q4 confirms harm → escalate architecture fix, treat as blocking
         -- If Q4 shows ~0pp → Priority Finding is a non-issue, proceed to B3-B8
Step 5: Run B4, B6 (topic gate, facet-dist gate) on StaleMemory                                 [15 min]
         ** Q6, Q7 answered **
Step 6: Run B7, B8 (support/recency gates) on StaleMemory                                       [15 min]
         ** Q3 confirmed with ablation, not just observation **
Step 7: Grid search on whichever threshold(s) showed Δ > 1pp in Steps 3-6                       [30-60 min]
Step 8: Write test_near_dup_intercepts_contradiction + test_verdict_distribution_bounds          [1 hr]
Step 9: Update core/05-consolidation.md defaults + Parameter Sensitivity if anything changed     [15 min]
```

## Phase Execution

| # | Task | Status |
|---|------|--------|
| 1 | Implementation audit | ✅ |
| 2 | Core doc rewrite | ✅ |
| 3 | Plan document | ✅ |
| 4 | Diagnostic instrumentation | ▶ next |
| 5 | Threshold ablation matrix (B1-B4 priority, B5-B8 conditional) | pending |
| 6 | Parameter tuning | pending |
| 7 | Micro-benchmark gap-fill (2 new tests; 6 files already exist) | pending |
| 8 | Outcome document + PROGRESS | pending |
