# Retrieval — Measurement & Improvement Plan

**Based on:** `iteration-strategy.md` (Layer 1 Diagnostics + Layer 2 Ablations) + `06-retrieval.md` code audit
**Status:** IMPLEMENTED (spread-projection architecture) + PARTIALLY MEASURED

---

## Architecture Decision: Spread-Projection (2026-07-08)

**Problem identified by instrumentation:** `graph_only_saves = 0` across all 18 wiki scenarios. Root cause: `spread_episode_weight=0.15` (graph-space score) was architecturally incommensurable with cosine-direct scores `[0.56, 0.85]`. Graph episodes could never compete regardless of graph quality.

**Root cause is deeper than a tuning issue:** The pre-trained embedding space and the prototype graph were learned by separate processes with no shared scale calibration. The brain avoids this because similarity and association are encoded by the same synaptic weights learned jointly from the same experiences. Arbitrary weights like `spread_episode_weight` are band-aids, not solutions.

**Implemented fix — spread-projection FAISS:**
Instead of harvesting episodes by prototype membership and scoring them with an arbitrary weight, project the spread activation back into embedding space:
```
q_spread = normalize( Σ a(P) * centroid(P) )
```
Then run a second FAISS search on `q_spread` in the same cosine scale as the direct query. The result is directly comparable to cosine-direct scores — no separate scale, no ceiling, no arbitrary weight. `spread_score_weight=0.85` applies a principled slight discount (direct recall fires stronger than associative spreading).

**Brain analog:** CA3 recurrent completion produces an activation pattern that projects through Schaffer collaterals back into the CA1 representation space, where it competes with direct EC input on equal footing.

**Verified by `test_spreading_path_completion`:** 4 micro-benchmark tests confirm the full chain wires correctly: graph path A→B→C, 2-hop vs 1-hop boundary, and no-spreading baseline.

**What was deprecated:** `spread_episode_weight`, `spread_score_ceiling` are superseded and no longer used in the retrieval path. `episodes_per_prototype` is retained for the multi-scale coarse-episode lookup.

---

## 0. Scope: What This Plan Covers

The retrieval pipeline path (current implementation):

```
query_embedding
  → cosine-direct (FAISS)                                   [always]
  → multi-scale (coarse+fine seeds)                          [use_multi_scale]
  → predictive completion (transition model → 2nd seed)      [use_transition]
  → spreading activation (graph propagation)                 [use_spreading]
  → spread-projection FAISS (q_spread second search)         [use_spreading]
  → merge + temporal boost + salience re-rank
  → reinforcement (cosine-direct only)
```

This feeds into `RetrievalService.recall()` → schemas → working-memory gating. We decompose end-to-end ("did the right schema rank?") into component-level questions.

---

## 1. Key Diagnostic Questions

| # | Question | Why It Matters |
|---|----------|---------------|
| Q1 | Does spreading activation ever surface an episode cosine-direct missed? | If zero across all benchmarks, spreading is dead weight — focus shifts to graph quality |
| Q2 | How many steps does activation propagate? | If it dies at step 0, graph edges are too sparse/weak |
| Q3 | What fraction of graph-harvested episodes survive into final top-k? | Harvest can add episodes but diversity cap might push them all out |
| Q4 | Is the transition model predicting a meaningfully different direction? | If q_pred_sim > 0.85 everywhere, predictive seeding is a no-op |
| Q5 | Which score component dominates? | If salience dominates, tune salience_weight; if temporal doesn't move anything, it's decorative |
| Q6 | Are cosine scores decaying into a tight band? | If all top-10 scores are 0.45–0.55, ranking is near-random |
| Q7 | Does multi-scale co-occurrence bonus fire often enough? | If <5% of episodes appear at both scales, the bonus is cosmetic |

---

## 2. Phase 1 — Instrumentation
### Step 2.1: Add `EpisodeDiagnostic` to `types.py`

Add a dataclass with fields: `episode_id`, `source` ("cosine_direct"|"graph_harvest"|"predictive"), `cosine_score`, `graph_activation`, `temporal_bonus`, `salience_bonus`, `final_score`, `is_in_final_head`. Attach `diagnostics: list[EpisodeDiagnostic]` to `RetrievedMemorySet`.

### Step 2.2: Collect per-query metrics inside `retrieve()`

Key fields to collect: `seed_prototypes_n`, `activated_after_spread_n`, `activation_depth` (list of |active_set| per step), `cosine_direct_n`, `graph_harvest_n`, `graph_only_saves` (THE key metric — graph episodes in final head that cosine missed), `cosine_score_band` [min, p25, p50, p75, max], `temporal_contribution_p50`, `salience_contribution_p50`, `dual_scale_episodes_pct`, `q_pred_sim`.

### Step 2.3: Plumb through benchmark JSON

Diagnostics ride on existing `RecallResult` → `ScenarioResult` → JSON paths. No benchmark schema changes needed.

---

## 3. Phase 2 — Ablation Matrix

Run wiki scenarios with each boolean flag OFF:

| Ablation | Flag OFF | Tests |
|----------|----------|-------|
| `full` | (none) | Baseline |
| `no_spreading` | `use_spreading` | Pattern completion |
| `no_temporal` | `use_temporal` | Temporal context |
| `no_salience_gate` | `salience_gate` | Hebbian boosting |
| `no_transition` | `use_transition` | Predictive completion |
| `no_multiscale` | `use_multi_scale` | Dual-scale |
| `cosine_only` | All above | Pure FAISS |

**Analysis:** `full == no_spreading` across families → spreading decorative. `full > no_spreading` only on `completion` → working as designed. `full < no_spreading` → actively harmful (noisy edges).
### Step 3.1: Create ablation runner

`tests/wiki_scenarios/run_ablations.py` — runs all 7 configs in one process, prints matrix, saves JSON.

---

## 4. Phase 3 — Parameter Tuning Sweeps

### Spreading
```python
grid = {"spread_decay": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85],
        "spread_steps": [1, 2, 3, 4],
        "spread_episode_weight": [0.05, 0.10, 0.15, 0.20, 0.30]}
```
Goal: maximize `graph_only_saves` without regressing cosine-direct.

### Temporal
```python
grid = {"temporal_weight": [0.0, 0.10, 0.20, 0.25, 0.35, 0.50]}
```
Focus: `decay` and `supersession` families.

### Salience
```python
grid = {"salience_weight": [0.0, 0.15, 0.25, 0.30, 0.40, 0.50]}
```
---

## 5. Phase 4 — Synthetic Micro-Benchmarks

### 5.1: `test_spreading_path_completion`

Ingest 3 facts: A+B same topic (same prototype, high cosine), A+C different topic (low cosine). B+C co-occur in same session → graph edge B↔C after consolidation. Query A's topic. Expected: C appears via spreading A→B→C (2-hop) only when `use_spreading=True` AND `spread_steps >= 2`.

### 5.2: `test_graph_signal_vs_noise`

Ingest 50 facts in 5 clusters + 10 noise. Query cluster centroids. Measure precision = (graph-harvested in-cluster) / (total graph-harvested). Success: > 0.5.

---

## 6. Implementation Order

```
Step 1: Add EpisodeDiagnostic to types.py                           [30 min]
Step 2: Instrument retrieve() with diagnostics + per-episode tags   [1 hr]
Step 3: Plumb through RetrievedMemorySet → RecallResult              [30 min]
Step 4: Expose in wiki scenario JSON output                          [30 min]
Step 5: RUN wiki scenarios → read diagnostics                        [10 min]
         ** CHECKPOINT: Q1-Q7 answered **
Step 6: Create run_ablations.py                                      [1 hr]
Step 7: Run ablation matrix → analyze                                [30 min]
Step 8: Grid-search top-2 parameters                                 [2 hr]
Step 9: Write two micro-benchmarks                                   [2 hr]
Step 10: Update 06-retrieval.md if defaults change                   [30 min]
```

**Step 5 go/no-go:** If `graph_only_saves = 0` everywhere, Steps 6-9 deprioritized — shift to graph quality (component 3 in iteration strategy). If > 0, full plan proceeds.

---

## 7. Decision Thresholds

| Observed | Action |
|----------|--------|
| `graph_only_saves = 0` all benchmarks | Spreading dead weight → skip tuning, focus graph quality |
| `graph_only_saves > 0` but `full == no_spreading` | Check if graph episodes cluster near score threshold |
| `graph_only_saves > 0` and `full > no_spreading` | Tune parameters to maximize delta |
| `q_pred_sim > 0.85` median | Transition model near-identity → check threshold/training |
| `cosine_score_band` span < 0.10 | Ranking near-random → increase `episodic_top_k` |
| `dual_scale_episodes_pct < 0.05` | Multi-scale bonus cosmetic → consider defaulting OFF |

---

## 8. Success Criteria

1. **Q1 answered:** `graph_only_saves` measured per query, per benchmark
2. **Every boolean flag Δ measured** via ablation matrix
3. **At least one parameter tuned** from diagnostic data
4. **Two micro-benchmarks pass** (deterministic, <5s each)
5. **06-retrieval.md reflects final tuned defaults**