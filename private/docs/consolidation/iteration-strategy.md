# Slowave Iteration Strategy — Benchmarking & Component Improvement Plan

## Problem

Existing 6 benchmarks (wiki, temporal_eval, locomo, longmemeval, dmr, stalememory) measure end-to-end recall proxies — binary "did the right fact appear?" signals that conflate ~8 independent mechanisms into one number. A regression in consolidation can be masked by an improvement in temporal scoring; a broken graph can be hidden by cosine-direct fallback.

**What can't be answered today:**
- Does spreading activation ever surface an episode that cosine-direct misses?
- Are prototypes coherent clusters or random groupings?
- Does negative feedback actually suppress the right schemas over time?
- Does the temporal anchor estimator fire when it shouldn't?
- Does homeostatic normalization keep the graph sparse or kill useful edges?

## Strategy: Three-Layer Evaluation Pyramid

### Layer 1 — Component Diagnostics (zero new data, instrument existing code)

For each component, emit a scalar or distribution measuring internal quality. No ground truth needed — these measure structure, not accuracy.

| Component | Diagnostic | What It Tells You |
|-----------|-----------|-------------------|
| **Salience** | Spearman ρ(salience, recall_frequency) | Do high-salience episodes actually get retrieved more? |
| **Salience** | Fraction of episodes with salience > 0.1 at varying ages | Is decay calibrated to actual session cadence? |
| **Replay** | Mean cosine within-cluster vs between-cluster (silhouette) | Are prototypes coherent? |
| **Replay** | Centroid drift per replay pass | Have prototypes converged or are they still forming? |
| **Graph** | Edge count distribution per prototype (histogram) | Super-hubs? Normalization working? |
| **Graph** | Fraction of prototypes in largest connected component | Single blob or structured? |
| **Retrieval** | % of top-k from cosine-direct vs graph-harvest | Is spreading activation pulling its weight? |
| **Retrieval** | Activation depth: #prototypes active at step 0, 1, 2 | Does propagation spread or die immediately? |
| **Temporal** | Distribution of temporal_score / total_score per query | Temporal signal dominating or invisible? |
| **Temporal** | Anchor offset from "now" per query type | Anchor estimator triggering on atemporal queries? |
| **Consolidation** | Cosine(schema_embedding, source_prototype_centroid) | Is consolidation preserving prototype meaning? |
| **Supersession** | Supersession rate (#superseded / #new schemas) | Too aggressive or too passive? |
| **Feedback** | Δsalience per schema after N feedback events | Learning accumulating or one-shot? |
| **Context** | MMR dedup rate, budget utilization % | Wasting token budget? |

### Layer 2 — Targeted Ablation Matrix (uses existing benchmarks)

For every boolean config flag, run full suite with ON and OFF, measure Δ per benchmark.

| Flag | Default | What Disabling Tests |
|------|---------|---------------------|
| `use_spreading` | True | Does pattern completion help beyond cosine? |
| `use_temporal` | True | Does temporal context improve recall? |
| `salience_gate` | True | Does Hebbian support-count boosting help? |
| `self_supervise` | True | Does rehearsal improve graph quality? |
| `homeostatic_enabled` | True | Does normalization prevent graph degradation? |
| `use_pattern_separation` | False | Would DG separation help on your data? |
| `apply_learning` | True | Does the feedback loop matter at all? |
| `apply_negative_learning` | True | Does suppressing bad memories improve recall? |

If a flag's ON→OFF delta is ~0pp across all benchmarks, that component is dead weight — either the benchmark doesn't test that mechanism, or the mechanism is broken.

### Layer 3 — Synthetic Micro-Benchmarks (targeted, controllable)

Small (50–200 example) deterministic datasets isolating one mechanism. Run in seconds, regression immediately traceable to one module.

| Micro-Bench | What It Tests | How |
|-------------|--------------|-----|
| `test_supersession` | Update detection accuracy | Inject 100 (old, new) pairs with ground-truth: supersede / reinforce / unrelated. Measure precision/recall per threshold. |
| `test_temporal_chain` | Temporal anchor precision | Inject facts at t−7d, t−3d, t−1d, t_now. Query with "last week", "yesterday", "today". Measure rank of correct fact. |
| `test_cross_scope_bridge` | Graph generalization | Inject related facts in scope:A and scope:B. Query from scope:A; measure whether scope:B fact appears in top-k. |
| `test_graph_quality` | Edge weight ranking | Create prototypes with known relatedness. Measure Spearman ρ(edge_weight, ground_truth_relatedness). |
| `test_feedback_suppression` | Negative feedback efficacy | Inject fact, surface it, mark it `wrong` 3 times. Measure whether salience and retrieval rank actually decay. |
| `test_salience_calibration` | Decay curve fit | Inject 100 episodes at t=0, run time forward. Measure whether salience distribution matches expected exponential at each timestep. |
| `test_consolidation_fidelity` | Schema-prototype alignment | Consolidate after N replay passes. Measure cosine between schema embedding and source prototype. |
| `test_context_noise_penalty` | Irrelevant schema suppression | Surface a schema as irrelevant 5 times. Measure whether context ranking drops below useful schemas. |

---

## Prioritized Iteration Order

### 1. Retrieval (cosine + spreading activation)
**Why first**: User-facing output; all other improvements are invisible if retrieval doesn't surface them.

**Key question**: Is spreading activation ever the reason a correct memory appears in top-k that cosine-direct would have missed? If not, either queries don't require pattern completion, or graph edges are noise.

### 2. Salience
**Why second**: Drives replay sampling AND retrieval re-ranking. Poorly calibrated salience corrupts both paths.

**Key question**: Does `tau_seconds = 3600` match actual session cadence? If sessions are hours apart, memories decay before reinforcement. If seconds apart, nothing ever decays.

### 3. Graph Quality
**Why third**: Backbone of spreading activation. Bad edges → bad propagation → spreading activation becomes noise.

**Key question**: Are `λ₁=1.0, λ₂=0.5, λ₃=0.3` producing edges reflecting actual semantic/temporal relationships? Or is similarity dominating everything?

### 4. Consolidation + Supersession
**Why fourth**: Determines what schemas exist. Garbage schemas cap retrieval quality regardless of how good retrieval is.

**Key question**: Are `SAME_SCOPE_COS_THRESHOLD=0.85` and `DIRECTION_THRESHOLD=0.10` correctly separating "this is an update" from "this is a new fact"?

### 5. Temporal
**Why fifth**: Secondary signal — important for time-sensitive queries but subordinate to semantic match.

**Key question**: Is `temporal_weight=0.25` strong enough to surface "yesterday's fact" over "last month's fact" without drowning semantic relevance?

### 6. Feedback Loop
**Why sixth**: Requires many sessions to accumulate signal. Can't measure efficacy in a single benchmark run.

**Key question**: After 5 consecutive `irrelevant` labels on the same schema, does its context ranking actually drop?

### 7. Context Gating
**Why seventh**: Token efficiency matters for production but doesn't affect retrieval quality per se.

### 8. VSA
**Why last**: Not connected to any retrieval path — premature to benchmark.

---

## Per-Component Iteration Loop

For each component, in priority order:

1. **Look at the diagnostic** → identify the problem
2. **Run an ablation** (ON vs OFF) → confirm it matters
3. **Tune parameters** via grid search → optimize
4. **Write a micro-benchmark** → lock in the gain, prevent regressions

---

## Concrete First Step: Diagnostics Block

Add to every benchmark run summary JSON, alongside existing metrics:

```json
{
  "diagnostics": {
    "retrieval": {
      "cosine_direct_pct": 0.82,
      "graph_harvest_pct": 0.18,
      "graph_only_saves": 3,
      "activation_depth": [6, 14, 8]
    },
    "salience": {
      "salience_recall_rho": 0.43,
      "mean_salience": 0.31,
      "below_01_pct": 0.22
    },
    "graph": {
      "edges_total": 1847,
      "edges_per_proto_p50": 4,
      "edges_per_proto_p95": 18,
      "connected_component_pct": 0.91
    },
    "temporal": {
      "anchor_offset_median_sec": 0,
      "temporal_score_contribution_p50": 0.12
    },
    "consolidation": {
      "schema_proto_alignment_p50": 0.87,
      "supersession_rate": 0.03
    }
  }
}
```

Run the 6-benchmark suite once with defaults, then read the diagnostics. The numbers immediately identify which components are working and which are decorative. A component with `graph_only_saves = 0` across 1000 queries indicates dead weight. A component with `schema_proto_alignment_p50 = 0.45` indicates information loss during consolidation.