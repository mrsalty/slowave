# 04 — Graph Manager (Prototype Edges)

## Overview

The graph manager maintains a **sparse directed graph** over semantic prototypes. Each edge has three independent component weights (similarity, transition, coactivation) plus a fused composite weight used for retrieval. Edges are built from three signal sources — cosine similarity of prototype centroids, temporal transition probabilities from replay-ordered sequences, and coactivation counts from batch co-occurrence — plus a fourth episodic-memory-driven reinforcement path (self-supervise graph tightening) that runs in the replay engine.

The graph is the backbone of spreading activation (see 06-retrieval.md): activated prototypes propagate through outgoing edges to activate neighbors, enabling multi-hop associative recall that cosine-direct lookup cannot achieve.

## Data Flow

```
                  ┌──────────────────────┐
                  │   ReplayEngine        │
                  │  (orchestrator)       │
                  └──────┬───────┬───────┘
                         │       │
          ┌──────────────┤       ├──────────────────┐
          ▼              ▼       ▼                   ▼
   set_similarity   apply_transition   apply_coact   self_supervise
   _edges()         _counts()          _counts()     (ReplayEngine)
          │              │       │                   │
          ▼              ▼       ▼                   ▼
   ┌──────────────────────────────────────────────────┐
   │              GraphManager                         │
   │  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
   │  │similarity│  │transition│  │ coactivation  │  │
   │  │  edges   │  │  edges   │  │    edges      │  │
   │  │(overwrite)│ │ (EMA)   │  │ (EMA + top-k) │  │
   │  └────┬─────┘  └────┬─────┘  └───────┬───────┘  │
   │       └──────────────┴───────────────┘           │
   │                      │                           │
   │               _upsert_edge()                      │
   │         w = λ₁·sim + λ₂·trans + λ₃·coact         │
   │                      │                           │
   │        homeostatic_normalize() / prune_edges()   │
   └──────────────────────┬───────────────────────────┘
                          │
                          ▼
   ┌──────────────────────────────────────────────────┐
   │           RetrievalPipeline._spread()             │
   │     neighbors(src, top_k=neighbor_top_k)          │
   │     → propagation over outgoing edges             │
   └──────────────────────────────────────────────────┘
```

## Mathematical Formulation

### Phase 1: Edge Weight Fusion (`_upsert_edge`)

Every edge stores three component weights AND a fused composite weight in the
`prototype_edges` table:

\[
w_{pq} = \lambda_1 \cdot w_{\text{sim}} + \lambda_2 \cdot w_{\text{trans}} + \lambda_3 \cdot w_{\text{coact}}
\]

Where:
- \( w_{\text{sim}} \) = cosine similarity (overwritten each pass, **not** EMA-accumulated)
- \( w_{\text{trans}} \) = transition probability \( P(\text{dst} \mid \text{src}) \), EMA-accumulated
- \( w_{\text{coact}} \) = coactivation count, EMA-accumulated
- \( \lambda_1 = 0.3 \), \( \lambda_2 = 0.5 \), \( \lambda_3 = 0.3 \)

**Logical concept**: The fused weight \( w \) is the only value retrieval
consumes. Components are stored separately so they can be updated independently —
similarity is recomputed fresh each replay pass (reflecting current embedding
space), while transition/coactivation accumulate over time via EMA (reflecting
learned history). \( \lambda_1 = 0.3 \) was reduced from 1.0 after the graph
quality deep-dive found 89% of edges were pure cosine on a live DB — at 0.3,
similarity is on par with learned signals rather than drowning them out.

### Phase 2: Similarity Edges (`set_similarity_edges`)

\[
\forall p \in \text{prototype\_ids}: \text{edge}(p \rightarrow q) \text{ for top-}k \text{ by } \cos(\mathbf{c}_p, \mathbf{c}_q)
\]

Where \( k = \text{top\_k\_similarity} \) (default: `8`).

- Similarity edges are **recomputed from scratch** each call — `w_similarity` is overwritten (no EMA).
- Transition/coactivation components for existing edges are preserved via `_get_components` read-back.
- After writing, `prune_edges()` runs (absolute threshold only, NOT homeostatic normalization).
- Self-edges (\( p = q \)) are excluded.
**Logical concept**: Similarity edges provide the "static" structure — which
prototypes are semantically close right now. They are NOT EMA-accumulated
because centroids evolve slowly. If we accumulated similarity, stale centroid
positions would haunt the graph. Instead, each pass gets a fresh snapshot.

### Phase 3: Transition Accumulation (`apply_transition_counts`)

The caller (ReplayEngine) computes transition probabilities \( P(q \mid p) \). GraphManager accumulates via EMA:

\[
w_{\text{trans}}^{\text{new}} = w_{\text{trans}}^{\text{old}} \cdot \alpha_d + P(q \mid p)_{\text{current}} \cdot (1 - \alpha_d)
\]

Where \( \alpha_d = \text{accumulate\_decay} \) (default: `0.3`).

- **No top-k filter** — ALL transition pairs from the replay batch are accumulated.
- After accumulation: `_homeostatic_normalize()` if enabled, else `prune_edges()`.
**Logical concept**: Transition edges capture temporal adjacency — "after prototype A,
the replay engine next activated prototype B." With α_d=0.3, 70% of stored weight
comes from the current pass. A single exposure gives 0.7·P(q|p), but after a second
pass without reinforcement it decays to 0.21·P(q|p). Traces fade fast unless
reinforced — biologically analogous to hippocampal LTP requiring repeated co-firing.
This prevents one-off random adjacencies from permanently polluting the graph.

### Phase 4: Coactivation Accumulation (`apply_coactivation_counts`)

\[
w_{\text{coact}}^{\text{new}} = w_{\text{coact}}^{\text{old}} \cdot \alpha_d + \text{count}_{\text{current}} \cdot (1 - \alpha_d)
\]

- **Top-k filter**: Only top \( k = \text{top\_k\_coactivation} \) (default: `6`) pairs per source pass through.
- Self-edges (\( p = q \)) are skipped.
- Same EMA decay as transitions.
- After accumulation: same homeostatic/prune post-processing.
**Logical concept**: Coactivation captures "these prototypes fired together" — a
Hebbian "cells that fire together wire together" signal. Unlike transitions
(which encode order), coactivation is symmetric: if A and B are in the same
replay batch, both directions get the same count. The top-k filter is critical
for scalability — with 128 prototypes per replay, without it every prototype
would grow 127 new edges per pass, overwhelming the graph with quadratic density.

### Phase 5: Homeostatic Normalization (`_homeostatic_normalize`)

For each source prototype \( p \) with outgoing edges \( \{(q_i, w_{pq_i})\} \):

\[
w_{pq_i} \leftarrow w_{pq_i} \cdot \frac{T}{\sum_j w_{pq_j}}, \quad T = \text{homeostatic\_target}
\]

Then inside the same pass, prune if:

\[
w_{pq_i} < \max(\text{prune\_ratio} \cdot \max_j w_{pq_j}, \; \text{prune\_below})
\]

- Only the `weight` column is updated; component columns are NOT rescaled.
- Surviving edges are batch-updated; pruned edges are batch-deleted.
**Logical concept**: Hebbian learning has a problem — "fire together → wire together"
increases weights monotonically. Without a counterforce, super-hubs emerge:
frequently active prototypes develop strong connections to everything, starving
weaker edges. The brain solves this via synaptic scaling — neurons compete for a
fixed metabolic budget. Here, T=0.5 caps each prototype's total outgoing activation
at 0.5, forcing competition. Strong edges steal budget from weak edges, which then
fall below the pruning threshold and die. Components (w_sim, w_trans, w_coact) are
NOT rescaled — only the fused weight is. This means components drift from the fused
weight after normalization, but since retrieval only consumes the fused weight and
components exist for diagnostics, this is harmless.

### Phase 6: Absolute Pruning (`prune_edges`)

When `homeostatic_enabled=False`, or after `set_similarity_edges`, or after `self_supervise`:

\[
\text{DELETE FROM prototype\_edges WHERE weight} < \text{prune\_below}
\]
**Logical concept**: Even without homeostatic competition, some edges are too weak to
matter. At λ₁=0.3, a pure similarity edge with cosine 0.1 gets weight 0.3×0.1=0.03,
which is below prune_below=0.05 — pruned. This keeps the graph from storing edges
that would contribute negligible activation during spreading.

### Phase 7: Self-Supervise Graph Tightening (`ReplayEngine.self_supervise`)

**⚠ NOT in GraphManager — lives in ReplayEngine but reads/writes `prototype_edges`.**

1. Select top-N prototypes by member count (≥ `self_supervise_min_members` episodes, default: `3`).
2. For each: use the most recent member episode as a probe embedding.
3. Retrieve top-k episodes via full RetrievalPipeline.
4. **Misses**: expected siblings NOT in results → add `self_supervise_miss_reward` (default: `0.5`) to coactivation component of proto→sibling_proto (both directions).
5. **Confusers**: foreign-prototype episodes in results → subtract `self_supervise_confuser_penalty` (default: `0.25`).
6. Updates are **additive** — they bypass EMA accumulation. Coactivation clamped ≥ 0.
7. After all deltas applied, `prune_edges()` runs.
**Logical concept**: This is episodic-memory-driven graph learning. The system probes
its own retrieval, finds what it missed, and strengthens the graph edges that would
have helped. "I expected to recall X when probing with Y, but I didn't → strengthen
Y→X." Conversely, "I retrieved Z but Z isn't related to Y → weaken Y→Z." Additive
(not EMA) updates are deliberate: self-supervise provides a targeted correction
signal, not a running estimate. The dentate gyrus gate skips prototypes whose schemas
have contradiction evidence — the brain pattern-separates conflicting traces rather
than reinforcing them.

### Phase 8: Neighbor Retrieval (`neighbors`)

\[
\mathcal{N}(p, k) = \{(q, w_{pq}) \mid q \in \text{top-}k \text{ by weight DESC}\}
\]

Where \( k \) = `neighbor_top_k` from `RetrievalConfig` (default: `6`). The method default is `8`, but the consumer (`_spread`) always passes an explicit value.
**Logical concept**: This is the read path — the only way retrieval interacts with
the graph. A simple top-k lookup by precomputed fused weight. No normalization
happens here; that's the consumer's job in Phase 9.

### Phase 9: Activation Propagation (`RetrievalPipeline._spread`)

See 06-retrieval.md. Summary — weights are L1-normalized per-source at query time (independent of stored homeostatic normalization):

\[
a_{t+1}[p] = \alpha \cdot a_t[p] + (1-\alpha) \cdot \sum_{q \in \mathcal{N}(p,k)} \frac{w_{qp}}{\sum_r w_{qr}} \cdot a_t[q]
\]

Where \( \alpha = \text{spread\_decay} = 0.6 \).

**Logical concept**: Each spreading step retains 60% of a prototype's activation
(self-reinforcement) and redistributes 40% to neighbors proportional to edge weights.
The L1 normalization at query time (independent of stored homeostatic normalization)
ensures fair propagation — a prototype with 2 strong edges and one with 10 weak edges
both propagate the same total activation budget. Two-step spreading means activation
reaches 2-hop neighbors, enabling transitive recall: "A reminds me of B, which
reminds me of C."

## Configuration

### `GraphConfig` (in `slowave/latent/graph_manager.py`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `top_k_similarity` | `int` | `8` | Max similarity edges per prototype (recomputed fresh each pass) |
| `top_k_coactivation` | `int` | `6` | Max coactivation pairs per source retained after top-k filter |
| `prune_below` | `float` | `0.05` | Absolute pruning threshold |
| `lambda_similarity` (λ₁) | `float` | `0.3` | Weight for cosine similarity in fused weight (reduced from 1.0, see graph quality deep-dive) |
| `lambda_transition` (λ₂) | `float` | `0.5` | Weight for transition probability in fused weight |
| `lambda_coactivation` (λ₃) | `float` | `0.3` | Weight for coactivation count in fused weight |
| `accumulate_decay` (α_d) | `float` | `0.3` | EMA decay factor — lower = faster adaptation |
| `homeostatic_enabled` | `bool` | `True` | Enable L1 homeostatic normalization + relative pruning |
| `homeostatic_target` (T) | `float` | `0.5` | Target L1 sum per source prototype |
| `prune_ratio` | `float` | `0.2` | Relative pruning fraction of max weight |

### `ReplayConfig` (graph-relevant fields, in `slowave/latent/replay_engine.py`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `self_supervise` | `bool` | `True` | Enable self-supervised graph tightening |
| `self_supervise_max_prototypes` | `int` | `32` | Max prototypes to probe per pass |
| `self_supervise_min_members` | `int` | `3` | Min members a prototype must have to be probed |
| `self_supervise_top_k` | `int` | `8` | Top-k for retrieval probe |
| `self_supervise_miss_reward` | `float` | `0.5` | Coactivation boost for missed sibling bridges |
| `self_supervise_confuser_penalty` | `float` | `0.25` | Coactivation penalty for confuser edges |

## Caller Table

| Caller | Method | What It Writes | When |
|--------|--------|----------------|------|
| `ReplayEngine.replay_once()` | `apply_coactivation_counts` | Coactivation (EMA + top-k filter) | Every replay pass |
| `ReplayEngine.replay_once()` | `apply_transition_counts` | Transition probabilities (EMA, no top-k) | Every replay pass |
| `ReplayEngine.replay_once()` | `set_similarity_edges` | Cosine similarity (overwrite, no EMA) | Every replay pass |
| `ReplayEngine.self_supervise()` | `_upsert_edge` (direct) | Coactivation deltas (additive, not EMA) | End of consolidation |
| `ReplayEngine.self_supervise()` | `prune_edges` | Deletes edges below prune_below | After additive updates |
| `RetrievalPipeline._spread()` | `neighbors` | **Read-only** — fetches top-k | Every retrieval |

## Key Invariants

1. **Edges are directed**: \( w_{pq} \neq w_{qp} \) in general. Transition edges are inherently directional.
2. **The fused weight \( w \) is used in retrieval; component weights are stored for diagnostics.** Components update independently.
3. **Similarity edges are recomputed fresh each pass** (no EMA). They reflect current centroid positions.
4. **Transition edges have NO top-k filter; coactivation edges DO** (top_k_coactivation=6). Asymmetry deliberate: transitions are rarer.
5. **Homeostatic normalization runs after `apply_transition_counts` and `apply_coactivation_counts`** (when enabled), NOT after `set_similarity_edges` or `self_supervise`.
6. **Homeostatic normalization modifies only `weight`**, not component columns.
7. **`accumulate_decay = 0.3`** → each pass contributes 70% of stored weight. Single-exposure traces fade to ~9% after two unreinforced passes.
8. **Self-supervise uses additive coactivation updates** (not EMA) — direct Hebbian reinforcement.
9. **`neighbors()` L1-normalizes at read time** independently of homeostatic normalization.
10. **No `top_k_similarity` equivalent for transitions** — transition edges grow unbounded per source until pruned.

## Diagnostic Hooks

| Metric | What It Measures | How to Instrument |
|--------|-----------------|-------------------|
| `edge_weight_decomposition` | Fraction from similarity vs transition vs coactivation | For each edge: λᵢ·wᵢ / w; report distribution |
| `edge_count_distribution` | Per-source edge count (identify super-hubs) | `SELECT src_prototype_id, COUNT(*) FROM prototype_edges GROUP BY 1` |
| `symmetry_index` | Directionality: `1 − |w_pq − w_qp| / (w_pq + w_qp)` | Compare reciprocal pairs |
| `similarity_dominance_pct` | % of edges where similarity > 80% of fused weight | Edge decomposition then threshold count |
| `prune_survival_rate` | % of edges that survive homeostatic pruning | Count before/after `_homeostatic_normalize` |
| `self_supervise_effect_size` | Mean Δ coactivation per reinforced edge | Track `coact_delta` in ReplayEngine |
| `graph_spread_contribution` | Graph-only episodes in retrieval | Already via `graph_only_saves` in retrieval diagnostics |

## Parameter Sensitivity

| Parameter | Direction | Effect | Sweep Range |
|-----------|-----------|--------|-------------|
| `lambda_similarity` | ↑ | More cosine-dominated edges → noisy neighbor list | 0.0, 0.3, 0.5, 0.7, 1.0 |
| `lambda_transition` | ↑ | More temporal-sequence signal | 0.0, 0.3, 0.5, 1.0, 2.0 |
| `lambda_coactivation` | ↑ | More batch-co-occurrence signal | 0.0, 0.3, 0.5, 1.0, 2.0 |
| `accumulate_decay` | ↑ | Slower adaptation, old evidence persists | 0.0, 0.1, 0.3, 0.5, 0.7, 0.9 |
| `homeostatic_enabled` | bool | OFF = denser graph, super-hubs | True, False |
| `homeostatic_target` | ↑ | More activation budget → more surviving edges | 0.1, 0.3, 0.5, 1.0, 2.0 |
| `prune_ratio` | ↑ | More aggressive relative pruning | 0.05, 0.1, 0.2, 0.5 |
| `prune_below` | ↑ | More aggressive absolute pruning | 0.01, 0.03, 0.05, 0.10, 0.20 |
| `self_supervise` | bool | OFF = no failure-driven learning | True, False |
| `top_k_similarity` | ↑ | Denser similarity neighborhood | 4, 8, 16, 32 |
| `top_k_coactivation` | ↑ | More coactivation edges retained per source | 3, 6, 12, 24 |

## Known Failure Modes

| Symptom | Likely Cause | Diagnostic Signal |
|---------|-------------|-------------------|
| Spreading offers no benefit over cosine-direct | >80% edge weight is similarity → graph IS cosine | `similarity_dominance_pct` > 80% |
| Graph densification → all-to-all connectivity | `homeostatic_enabled=False` AND `prune_below` too low | Edge count grows without bound |
| Super-hubs dominate spreading | Homeostatic normalization too weak (target too high) | Per-source L1 sum long-tail distribution |
| Self-supervise makes graph worse | Confuser penalty too aggressive vs miss reward | Negative benchmark delta |
| Edge count near zero after pruning | `prune_below` too high or `prune_ratio` too aggressive | `prune_survival_rate` near 0% |
| Transition edges contribute nothing | Batch not temporally ordered | Transition component ≈ 0 across all edges |
| Coactivation edges all symmetric | Cosine similarity dominates both directions | `symmetry_index` ≈ 1.0 for majority |

## Relationship to Other Modules

| Module | Relationship |
|--------|-------------|
| `06-retrieval.md` | Primary consumer — `_spread()` reads `neighbors()` for activation propagation |
| `03-replay.md` | Primary producer — writes all three edge types + self-supervise |
| `05-salience.md` | Indirect — salience weights determine which episodes replay, affecting counts |
| `07-consolidation.md` | Indirect — prototype creation determines which prototypes have edges |
| `02-vsa.md` | No direct relationship (VSA is write-only in production) |

## Implementation Files

| File | What It Implements |
|------|-------------------|
| `slowave/latent/graph_manager.py` | `GraphConfig` dataclass, `GraphManager` (all edge ops) |
| `slowave/latent/replay_engine.py` | `ReplayConfig.self_supervise*`, replay loop calling graph methods |
| `slowave/latent/retrieval.py` | `RetrievalPipeline._spread()` — consumer; `RetrievalConfig.neighbor_top_k` |
| `slowave/storage/schema.sql` | `prototype_edges` table (lines 51-63) |
| `tests/unit/test_graph_accumulation.py` | 8 tests: EMA accumulation + homeostatic normalization |
| `tests/unit/test_spreading_path_completion.py` | Micro-benchmark: A→B→C 2-hop graph path |
| `tests/experiments/grid_search_graph.py` | Grid search over accumulate_decay, homeostatic_target, prune_ratio |
