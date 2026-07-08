# 03 — Graph Quality Improvement Plan

**Status:** in progress
**Created:** 2026-07-08

## Diagnostic Questions

These 7 questions must be answered in Phase 4 before any parameter tuning:

1. **What fraction of edge weight is similarity vs transition vs coactivation?**
   Compute for each edge: `λ₁·w_sim / w`, `λ₂·w_trans / w`, `λ₃·w_coact / w`. Report mean/median/p90.
   **Go/No-Go**: If >80% of edge weight is similarity at median → architectural fix needed, not tuning.

2. **Are λ weights optimal?** Ablate each λ=0 on LoCoMo limit=3.

3. **Does homeostatic normalization help or hurt?** ON vs OFF on LoCoMo + Temporal.

4. **Is `prune_below=0.05` too aggressive?** Test {0.01, 0.03, 0.05, 0.10, 0.20}.

5. **Does `self_supervise()` improve edge quality?** ON vs OFF on LoCoMo.

6. **Are edges directional or symmetric?** Symmetry index: `1 − |w_pq − w_qp| / (w_pq + w_qp)`. If median > 0.9 → edges are cosine.

7. **Edge count distribution? Super-hubs?** Per-source degree: mean, median, max, p95.
## Ablation Matrix

| # | homeo | λ₁ | λ₂ | λ₃ | self_sup | Eval | Expected |
|---|-------|-----|-----|-----|----------|------|----------|
| A1 | True | 1.0 | 0.5 | 0.3 | True | LoCoMo+Temporal | **baseline** |
| A2 | False | 1.0 | 0.5 | 0.3 | True | LoCoMo+Temporal | denser graph, super-hubs |
| A3 | True | 0.0 | 0.5 | 0.3 | True | LoCoMo+Temporal | transition+coact only |
| A4 | True | 1.0 | 0.0 | 0.3 | True | LoCoMo+Temporal | similarity+coact only |
| A5 | True | 1.0 | 0.5 | 0.0 | True | LoCoMo+Temporal | similarity+transition only |
| A6 | True | 0.0 | 1.0 | 1.0 | True | LoCoMo+Temporal | no similarity at all |
| A7 | True | 1.0 | 0.5 | 0.3 | False | LoCoMo+Temporal | no self-supervise |

All 7 on LoCoMo limit=3. Promote top-2 + baseline to full run.

## Grid Search

### λ orthogonal sweep: 13 runs at limit=3
### accumulate_decay: {0.0, 0.1, 0.3, 0.5, 0.7, 0.9} (6 runs)
### prune_below: {0.01, 0.03, 0.05, 0.10, 0.20} (5 runs)

Script pattern: `private/docs/consolidation/scripts/grid_search_spread_weight.sh`

## Micro-Benchmark Spec (Phase 7)

`tests/unit/test_graph_edge_quality.py` — deterministic, <5s, no external data:

1. Edge rank reflects ground-truth relatedness (Spearman ρ > 0.8)
2. Directional edges: λ₁=0, λ₂=1.0 → A→B ≠ B→A
3. Homeostatic normalization respects target L1 sum
4. Pruning removes edges below prune_below
5. EMA convergence: after ~5 passes weight → count within 5%
6. Weight decomposition: verify λ₁·sim / λ₂·trans / λ₃·coact fractions
7. Coactivation top-k filter: exactly top_k edges survive per source
8. Similarity overwrite: two calls don't accumulate

## Phase Execution

| # | Task | Status |
|---|------|--------|
| 1 | Implementation audit | ✅ |
| 2 | Core doc rewrite | ✅ |
| 3 | Plan document | ✅ |
| 4 | Diagnostic instrumentation | ▶ next |
| 5 | Ablation matrix | pending |
| 6 | Parameter tuning | pending |
| 7 | Micro-benchmark tests | pending |
| 8 | Outcome document + PROGRESS | pending |