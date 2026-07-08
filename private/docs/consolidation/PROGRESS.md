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
| 2 | Salience | ✅ generated | — | — | not started | — |
| 3 | Graph | ✅ generated | — | — | not started | — |
| 4 | Consolidation | ✅ generated | — | — | not started | — |
| 5 | Temporal | ✅ generated | — | — | not started | — |
| 6 | Feedback | ✅ generated | — | — | not started | — |
| 7 | Context | ✅ generated | — | — | not started | — |
| 8 | VSA | ✅ generated | — | — | deferred (not wired) | — |

**Current benchmarks (2026-07-08):**
- LoCoMo: 78.7% | LongMemEval: 87.8% | DMR: 95.6% | Temporal: 80.0% | StaleMemory: 45.2%

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

## Next Session: Pick Up at Salience (Module 2)

**Key questions (from iteration-strategy.md):**
- Does `tau_seconds = 3600` match actual session cadence?
- Is `salience_weight=0.4` calibrated (raw salience range 0.01–4.0+)?
- Does Spearman ρ(salience, recall_frequency) > 0.5?

**Starting point:**
1. Read `core/02-salience.md` — check alignment with implementation
2. Run diagnostics: `spearman_rho(salience, recalled_count)` across benchmark episodes
3. Check salience distribution at t=0, t=7d, t=30d — is decay calibrated?
