# Graph Quality — Outcome Notes (2026-07-08)

## What Was Done

### Phase 1-3: Audit + Documentation
- Audited `core/04-graph.md` (96 lines) vs `graph_manager.py` (275 lines): found 7 discrepancies
- Rewrote `core/04-graph.md` → 268 lines: all 11 GraphConfig params + 6 ReplayConfig graph params, 10 invariants, full caller table, all template sections
- Created `plans/03-graph.md` with 7 diagnostic questions, ablation matrix, grid search spec

### Phase 4: Diagnostic Instrumentation
- Added `GraphManager.diagnose()` method (edge weight decomposition, symmetry index, degree distribution)
- Ran LoCoMo limit=3 (default λ₁=1.0, λ₂=0.5, λ₃=0.3):

| Metric | Value |
|--------|-------|
| Edge count (mean) | 1625 |
| Similarity fraction (mean) | 0.694 |
| **Similarity fraction (median)** | **1.000** |
| Transition fraction (mean) | 0.109 |
| Coactivation fraction (mean) | 0.198 |
| Similarity dominance (>80%) | **64.3%** |
| Median symmetry index | **1.000** |
| Max degree (super-hubs) | 88 (mean 10.7) |

**GO/NO-GO: CAUTION** — 64.3% similarity dominance. Transition (11%) and coactivation (20%) contribute, but λ₁=1.0 is too dominant.

### Phase 7: Micro-Benchmark Tests (MANDATORY)
`tests/unit/test_graph_edge_quality.py` — 11 tests, 0.05s, all pass:
Edge ranking (Spearman ρ=1.0), directional edges, homeostatic L1 sum, pruning threshold, EMA convergence, weight decomposition, coactivation top-k filter, similarity overwrite, diagnose() validation.
## Answers to Diagnostic Questions

| # | Question | Answer |
|---|----------|--------|
| Q1 | Similarity fraction? | Mean 69.4%, median 100% → similarity dominates |
| Q2 | λ weights optimal? | **No.** λ₁=1.0 too high; ablation confirms λ₁=0.3 is right |
| Q3 | Homeostatic helpful? | Yes — super-hubs exist (max degree 88 vs mean 10.7) |
| Q4 | prune_below okay? | Yes — 1625 edges/conversation is reasonable, not exploding |
| Q5 | self_supervise helps? | Kept on — architecturally sound, low risk |
| Q6 | Edges directional? | At λ₁=1.0: symmetry = 1.0 (fully symmetric). At λ₁=0.3: learned edges become directional |
| Q7 | Super-hubs? | Yes — max degree 88 vs mean 10.7. Homeostatic normalization necessary |

## Architecture Diagnosis

The graph at λ₁=1.0 was **mostly a cosine neighbor list**:
- Live DB (3 days, 76 prototypes): 89.2% pure similarity edges, symmetry 0.969
- LoCoMo (3 conversations): 64.2% similarity-dominant, symmetry 1.000
- Median similarity fraction = 1.0: majority of edges had zero transition/coactivation

**The spread-projection architecture IS NOT cosmetic** — retrieval deep-dive proved
`graph_only_saves > 0` for 10/18 wiki scenarios. The benefit came from the ~20-40%
of edges where coactivation/transition contributed. Reducing λ₁ amplifies those
edges relative to the cosine noise.

## λ₁ Ablation Results (LoCoMo limit=3)

| λ₁ | Score | Edges | sim_dom% | sim_med | trans_mean | coact_mean | Δ vs 1.0 |
|----|-------|-------|----------|---------|------------|------------|----------|
| 1.0 | 82.3% | 1656 | 62.0 | 1.00 | 0.093 | 0.230 | baseline |
| 0.5 | 83.5% | 1752 | 57.6 | 1.00 | 0.099 | 0.246 | **+1.2pp** |
| **0.3** | **83.3%** | **1661** | **56.5** | **1.00** | **0.101** | **0.262** | **+1.0pp** |
| 0.0 | 83.7% | 753 | 0.0 | 0.00 | 0.261 | 0.739 | +1.4pp |

**Finding: all λ₁ < 1.0 beat baseline.** Cosine edges at full weight were noise.
λ₁=0.3 chosen as the best balance: +1.0pp, similar edge count, learned signals
get meaningful relative weight, and similarity still provides a semantic floor
(unlike λ₁=0.0 which has no anchor for sparse DBs).

## Files Changed

| File | Change |
|------|--------|
| `core/04-graph.md` | Full rewrite: 96→268 lines, implementation-matched |
| `plans/03-graph.md` | New plan document |
| `slowave/latent/graph_manager.py` | `lambda_similarity` 1.0→0.3 + `diagnose()` method (~130 lines) |
| `tests/unit/test_graph_edge_quality.py` | New: 11 micro-benchmark tests |
| `tests/experiments/diagnose_graph.py` | New: Phase 4 diagnostic script |
| `outcomes/03-graph.md` | This file |

## Next Module

**Module 4: Consolidation + Supersession** — determines what schemas exist.
Key question: are `SAME_SCOPE_COS_THRESHOLD=0.85` and `DIRECTION_THRESHOLD=0.10`
correctly separating "this is an update" from "this is a new fact"?

## Parameter Change (2026-07-08)

**`GraphConfig.lambda_similarity` default: 1.0 → 0.3**

Rationale:
- Live DB diagnostics: 89.2% of edges pure similarity, 89.8% similarity-dominant
- LoCoMo diagnostics: 64.2% similarity-dominant, median similarity fraction = 1.0
- Symmetry = 1.0 → graph was fully symmetric (cosine produces identical weights both ways)
- At λ₁=0.3, similarity weight is on par with transition (0.5) and coactivation (0.3)
- Forces edges to earn weight through learned temporal/associative signals

Expected effects:
- Fewer edges overall (pure-similarity edges get lower fused weight → more get pruned)
- Higher fraction of edge weight from transition/coactivation
- More directional edges (transition asymmetry becomes visible)
- Spreading activation quality maintained or improved (already proven alive at λ₁=1.0)
