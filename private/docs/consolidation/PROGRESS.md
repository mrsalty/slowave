# Slowave — Algorithmic Deep Dive Progress

This is the pick-up point for every new session.
For strategy and prioritization: `iteration-strategy.md`.
For algorithm specs: `core/NN-module.md`.
For active improvement plans: `plans/NN-module.md`.
For completed work notes: `outcomes/NN-module.md`.

---

## Module Status

| # | Module | Core Doc | Plan | Outcome | Status | Benchmark Δ |
|---|--------|----------|------|---------|--------|-------------|
| 1 | **Retrieval** | ✅ updated | ✅ done | ✅ done | **COMPLETE** | LoCoMo +3.7pp, Temporal +6.7pp, DMR +2.2pp |
| 2 | Salience | ✅ updated | ✅ done | ✅ done | **COMPLETE** | LoCoMo +0.8pp (79.5%) |
| 3 | Graph | ✅ generated | — | — | not started | — |
| 4 | Consolidation | ✅ generated | — | — | not started | — |
| 5 | Temporal | ✅ generated | — | — | not started | — |
| 6 | Feedback | ✅ generated | — | — | not started | — |
| 7 | Context | ✅ generated | — | — | not started | — |
| 8 | VSA | ✅ generated | — | — | deferred (not wired) | — |

**Current benchmarks (2026-07-08):**
- LoCoMo: 79.5% | LongMemEval: 87.8% | DMR: 95.6% | Temporal: 80.0% | StaleMemory: 45.2%

---

## What Was Done: Retrieval (2026-07-08)

Full session log: `outcomes/01-retrieval.md`

**Root problem found:** `spread_episode_weight=0.15` placed graph episodes on an incommensurable score scale vs cosine-direct (0.56+). Graph contributed nothing.

**Fix implemented:** Spread-projection FAISS — `q_spread = normalize(Σ a(P)*centroid(P))`, second FAISS search in same cosine space, `spread_score_weight=0.85`. Eliminated the score-scale mismatch.

**Evidence:**
- `test_spreading_path_completion.py` — graph path A→B→C wired correctly
- `test_retrieval_pipeline_plumbing.py` — spreading and temporal components show differential
- `graph_only_saves > 0` for 10/18 wiki scenarios (was 0/18)
- Benchmark improvements confirmed above

---

## What Was Done: Salience doc rewrite (2026-07-08)

`core/02-salience.md` fully rewritten from the generated stub. Key changes vs prior version:

**Gaps filled:**
- Added predictive-surprise term: `s₀ = max(0.01, novelty + 0.3 * surprise)` — surprise was completely missing
- Added remember-event boost (`min(1.5, s + 0.6)`) and macro-episode haircut (`max(s * 0.8, 0.05)`)
- Documented schema salience as a second parallel track (creation, feedback deltas, sigmoid normalization)
- Fixed recall reinforcement: actual amount is `RetrievalConfig.salience_weight` (0.3), not `SalienceConfig.recall_reinforcement` (0.2) — the latter is dead code
- Documented lazy decay (replay-triggered, not continuous)
- Added all missing template sections: Data Flow, Implementation Files, Diagnostic Hooks, Parameter Sensitivity, Known Failure Modes, Relationships

**Open questions / plan candidates:**
- `SalienceConfig.recall_reinforcement` is dead code — remove it or wire it up?
- `tau_seconds=3600` half-life is 41 min — likely too aggressive for daily-use patterns
- `0.3 * surprise` coefficient is hardcoded — should it be a config param?
- Does Spearman ρ(salience, recalled_count) > 0.5 on real data?

## Next Session: Pick Up at Salience (Module 2) — Plan Phase

**Starting point:**
1. Review `core/02-salience.md` open questions above
2. Decide which to address in the plan (dead code cleanup vs calibration vs config exposure)
3. Write `plans/02-salience.md`
4. Run diagnostics: `spearman_rho(salience, recalled_count)` across benchmark episodes
5. Check salience distribution at t=0, t=1h, t=7d — verify decay calibration
