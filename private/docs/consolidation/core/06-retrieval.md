# 06 — Retrieval Pipeline

## Overview

The retrieval pipeline combines four complementary mechanisms, all operating in the same embedding space:

1. **Cosine-direct retrieval** — FAISS search over episodic embeddings against the query (literal recall).
2. **Spread-projection retrieval** — spreading activation propagates over the prototype graph; the resulting activation pattern is projected back into embedding space as a weighted centroid (`q_spread`); a second FAISS search on `q_spread` retrieves associatively-linked episodes in the same cosine scale as the direct query (pattern completion without score-scale mismatch).
3. **Predictive completion** — transition model foresees the next-state embedding as a third cosine seed (sequential reasoning).
4. **Multi-scale retrieval** — parallel fine (CA3) and coarse (CA1) prototype seeds with co-occurrence bonus (dual-level evidence).

All episode scores are in the same `[−1, 1]` cosine space. Results are merged, temporally boosted, salience-re-ranked, and diversity-capped.

---

## Mathematical Formulation

### Phase 1: Query Encoding

\[
\mathbf{q} = \text{encode}(query) \in \mathbb{R}^d, \quad \|\mathbf{q}\|_2 = 1
\]

The pipeline receives an already-encoded L2-normalized query vector.

### Phase 2: Cosine-Direct Retrieval

FAISS search over episodic embeddings:

\[
\mathcal{C} = \{ (i, s_i) \mid i \in \text{FAISS.search}(\mathbf{q}, k_e), \; s_i = \langle \mathbf{q}, \mathbf{e}_i \rangle \}
\]

Where \( k_e = \text{episodic\_top\_k} \) (default: `10`).

Fine-scale prototype search (CA3-like, narrow precise matches):

\[
\mathcal{P}_{\text{seed}} = \{ (j, s_j) \mid j \in \text{SemanticStore.search}(\mathbf{q}, k_s), \; s_j = \langle \mathbf{q}, \mathbf{c}_j \rangle \}
\]

Where \( k_s = \text{semantic\_top\_k} \) (default: `6`).

### Phase 2a: Multi-Scale Prototype Seeds (Stage 9)

When `use_multi_scale = True`, a second coarse-scale (CA1-like) search runs in parallel on prototypes assigned with a lower similarity threshold. Think of this as two hippocampal pathways firing at different granularities: fine (CA3) for pattern completion — narrow, precise matches — and coarse (CA1) for pattern generalization — broad topical overlap. A fact that surfaces at both scales is confirmed by two independent retrieval pathways. An episode that only matches at one scale might be a lucky embedding alignment; dual-scale evidence raises confidence.

\[
\mathcal{P}_{\text{coarse}} = \{ (j, s_j) \mid j \in \text{SemanticStore.search\_by\_scale}(\mathbf{q}, \text{coarse}, k_c) \}
\]

Coarse seeds are max-merged into the seed activation set, and their member episodes are later checked for dual-scale co-occurrence (see Phase 6).

### Phase 2b: Predictive Completion (Stage 3)

The transition model learns to predict \\( \\mathbf{e}_{t+1} \\) from \\( \\mathbf{e}_t \\) using prototype-level transition counts accumulated during consolidation. This is the mechanism that answers "what comes after X?" — a query whose answer lives *downstream* in a learned sequence, not in the query's own embedding neighborhood. Cosine-direct alone cannot solve this: the answer embedding may have near-zero dot product with the query embedding, but the transition model has seen the A→B sequence before and can steer retrieval toward B.

When `use_transition = True` and the transition model has completed at least one training step (`trained_steps > 0`), a forward prediction \( \hat{\mathbf{q}} = \text{TransitionModel.predict}(\mathbf{q}) \) is computed. If \( \|\hat{\mathbf{q}}\|_2 \geq \text{transition\_min\_norm} \) (default `10^{-2}`), it acts as a second cosine seed:

\[
s_i^{\text{pred}} = w_{\text{trans}} \cdot \langle \hat{\mathbf{q}}, \mathbf{e}_i \rangle, \quad w_{\text{trans}} = \text{transition\_score\_weight} \;(0.7)
\]

Predicted scores are max-merged with cosine-direct scores so a strong literal match is never demoted by a weaker prediction. The predicted embedding also seeds prototype activation (same discount factor \\( w_{\\text{trans}} \\)), so the graph spreading front is informed by both the query and its predicted continuation.

A **reserved-slot mechanism** reserves up to `transition_reserved_slots` (default `1`) head positions for predictive-seed candidates that would otherwise be displaced by cosine-direct episodes — but only when the prediction direction is *meaningfully different* from the query: \( \langle \mathbf{q}, \hat{\mathbf{q}} \rangle \leq \text{transition\_reserve\_max\_qsim} \) (default `0.85`).

### Phase 3: Spreading Activation (Stage 1)

When `use_spreading = True`, activation propagates from seed prototypes over the graph.

**Initialization**: seed prototypes receive activation proportional to their cosine match:

\[
a_0(p) = \frac{\max(0, \langle \mathbf{q}, \mathbf{c}_p \rangle)}{\max_j \langle \mathbf{q}, \mathbf{c}_j \rangle}
\]

**Propagation** (for `spread_steps` iterations):

\[
a_{t+1}(p) = \alpha \cdot a_t(p) + (1 - \alpha) \sum_{q \in \mathcal{N}_{\text{in}}(p)} \frac{w_{qp}}{\sum_{r} w_{qr}} \cdot a_t(q)
\]

Where:
- \( \alpha = \text{spread\_decay} \) (default: `0.6`) — retention factor (60% self-retention, 40% from neighbors)
- \( \mathcal{N}_{\text{in}}(p) \) = prototypes with outgoing edges to \( p \)
- \( w_{qp} \) = stored edge weight (fused similarity + transition + coactivation)

This update rule is structurally identical to **personalized PageRank** (random walk with restart). α controls the trade-off: α near 0 means activation spreads far but fast (everything gets weakly activated — noise), α near 1 means activation barely moves (effectively cosine-only).

**Pruning**: below \( \text{spread\_activation\_floor} \) (default: `10^{-3}`), activation is zeroed each step. This enforces **sparse coding** — without it, every prototype reachable in n+1 hops would acquire activation, growing the front unboundedly. Normalization per source (L1 over outgoing weights) prevents super-hub domination.

**Salience gate** (optional, `salience_gate=True`): final activation modulated by prototype support:

\[
a_{\text{final}}(p) = a(p) \cdot (1 + 0.1 \cdot \sqrt{1 + \text{support\_count}(p)})
\]

This is a **Hebbian prior**: prototypes with more evidence (higher support count from replay/consolidation) are modestly easier to activate. The √ dampens returns — a prototype with 10,000 episodes (~11.0× multiplier) is about 9.6× more activatable than one with 1 episode (~1.14×), not 10,000×. The constant 0.1 keeps this a soft prior: even massive evidence produces only an order-of-magnitude boost, never a hard filter.

### Phase 4: Spread-Projection FAISS

After spreading activation, the activated prototype centroids are reduced to a single weighted centroid in embedding space and used as a second FAISS query:

\[
\mathbf{q}_{\text{spread}} = \frac{\displaystyle\sum_{p \in \mathcal{A}} a_{\text{final}}(p) \cdot \mathbf{c}_p}{\displaystyle\left\|\sum_{p \in \mathcal{A}} a_{\text{final}}(p) \cdot \mathbf{c}_p\right\|_2}
\]

where \( \mathcal{A} \) is the set of activated prototypes after salience-gate modulation. A second FAISS search retrieves spread-projected episode candidates:

\[
\mathcal{S} = \{ (i, s_i) \mid i \in \text{FAISS.search}(\mathbf{q}_{\text{spread}}, k_{\text{sp}}),\; s_i = w_{\text{sp}} \cdot \langle \mathbf{q}_{\text{spread}}, \mathbf{e}_i \rangle,\; s_i > 0 \}
\]

Where \( k_{\text{sp}} = \text{spread\_episodic\_top\_k} \) (default: `10`) and \( w_{\text{sp}} = \text{spread\_score\_weight} \) (default: `0.85`). Episodes with discounted score \( \leq 0 \) are excluded — a zero inner product with `q_spread` carries no positive associative evidence.

Scores from \( \mathcal{S} \) are **max-merged** with cosine-direct scores: an episode already in \( \mathcal{C} \) retains its higher cosine-direct score if it exceeds the spread score.

**Why this resolves the score-scale problem**: the old approach scored graph-harvested episodes at `spread_episode_weight=0.15`, placing them on an incommensurable scale relative to cosine-direct scores of `0.56+`. By projecting spread activation back into embedding space, both retrieval channels produce cosine scores in `[−1, 1]`. The `0.85` discount is principled — direct recall fires stronger than associative spreading — rather than arbitrary.

**Brain analog**: CA3 recurrent pattern completion projects through Schaffer collaterals into the CA1 representation space, where it competes with direct EC input on equal footing. `q_spread` is that projection.

**Diversity cap**: at most `diversity_per_prototype` (default: `2`) spread-projection episodes per prototype. Cosine-direct episodes are exempt. This prevents a single high-connectivity prototype from saturating all head slots with near-duplicate spread-projection results.

**Predictive-seed promotion**: after diversity cap, the pipeline checks whether predictive-seed candidates were displaced. Candidates already in the head (by id or by prototype) are skipped. Surviving candidates are inserted just after the top cosine match, up to `transition_reserved_slots` positions. This ensures the head carries both literal cue matches and learned sequential continuations.

### Phase 5: Temporal Boost (Stage 7)

For each candidate episode \( e \) with timestamp \( t_e \):

\[
s_{\text{temporal}}(e) = \alpha_t \cdot \cos(\mathbf{t}_q, \mathbf{t}_e)
\]

Where:
- \( \mathbf{t}_q \) = temporal embedding of the query anchor timestamp
- \( \mathbf{t}_e \) = temporal embedding of the episode timestamp (multi-scale sinusoidal, see §07)
- \( \alpha_t = \text{temporal\_weight} \) (default: `0.25`)

Temporal boost is **additive, not multiplicative** — it nudges ranking by at most 25% of a perfect cosine match, never dominating semantic relevance.

### Phase 6: Salience Re-Ranking

Final score for each episode combines three independent signals additively:

\[
s_{\text{final}}(e) = \underbrace{\cos(\mathbf{q}, \mathbf{e})}_{\text{semantic}} + \underbrace{\alpha_t \cdot \cos(\mathbf{t}_q, \mathbf{t}_e)}_{\text{temporal}} + \underbrace{\alpha_s \cdot s_{\text{salience}}(e)}_{\text{salience}}
\]

Where \( \alpha_s = \text{salience\_weight} \) (default: `0.3`). For spread-projection episodes, the semantic component is the discounted `q_spread` cosine score \( w_{\text{sp}} \cdot \langle \mathbf{q}_{\text{spread}}, \mathbf{e} \rangle \). All scores are in the same `[−1, 1]` range.

**Multi-scale co-occurrence bonus**: when an episode appears in both fine-scale and coarse-scale results, its final score is multiplied by \( 1 + \omega \) where \( \omega = \text{multi\_scale\_co\_occurrence\_bonus} \) (default: `0.25`). Dual-scale evidence is stronger: the episode is confirmed by two independent retrieval pathways.

**Temporal anchor override**: the query temporal anchor defaults to "now" (recency bias), but can be explicitly set via `temporal_anchor_ts` for past-anchored queries (e.g., "what did we know last month").

### Phase 7: Reinforcement

Only cosine-direct episodes in the top slice receive recall reinforcement (+`salience_weight` to salience, +1 to `recalled_count`). Spread-projection and predictive-seed episodes do **not** receive reinforcement — this prevents self-rewarding loops where graph-activated or predicted prototypes accumulate salience independently of direct relevance.

---

## Configuration

### `RetrievalConfig`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `episodic_top_k` | `int` | `10` | Cosine-direct episodes to fetch |
| `semantic_top_k` | `int` | `6` | Cosine-direct prototypes to fetch |
| `neighbor_top_k` | `int` | `6` | Neighbors per prototype in propagation |
| `salience_weight` \( \alpha_s \) | `float` | `0.3` | Salience contribution to final score |
| `use_spreading` | `bool` | `True` | Enable spreading activation |
| `spread_steps` | `int` | `2` | Propagation iterations |
| `spread_decay` \( \alpha \) | `float` | `0.6` | Activation retention per step |
| `spread_activation_floor` | `float` | `10^{-3}` | Pruning threshold |
| `episodes_per_prototype` | `int` | `6` | Coarse-scale episode lookup for multi-scale co-occurrence tracking |
| `spread_episodic_top_k` | `int` | `10` | Episodes retrieved via `q_spread` FAISS search |
| `spread_score_weight` \( w_{\text{sp}} \) | `float` | `0.85` | Discount for spread-projection scores (direct > associative) |
| `salience_gate` | `bool` | `True` | Enable support-count modulation of spread activation |
| `diversity_per_prototype` | `int` | `2` | Max spread-projection episodes per prototype |
| ~~`spread_episode_weight`~~ | `float` | `0.15` | **Superseded** — arbitrary cross-scale weight, no longer used |
| ~~`spread_score_ceiling`~~ | `float` | `0.9` | **Superseded** — score ceiling, no longer needed (same scale) |
| `use_temporal` | `bool` | `True` | Enable temporal proximity bonus |
| `temporal_weight` \( \alpha_t \) | `float` | `0.25` | Temporal contribution to final score |
| `temporal_anchor_ts` | `int` \| `None` | `None` | Explicit query anchor (Unix ts); `None` = "now" |
| `use_multi_scale` | `bool` | `True` | Enable dual-scale (fine + coarse) search |
| `coarse_semantic_top_k` | `int` | `6` | Coarse-scale (CA1) prototype seeds |
| `multi_scale_co_occurrence_bonus` \( \omega \) | `float` | `0.25` | Multiplicative bonus for dual-scale episodes |
| `use_transition` | `bool` | `True` | Enable transition model predictive completion |
| `transition_top_k` | `int` | `6` | Predicted-seed episodes to fetch |
| `transition_score_weight` \( w_{\text{trans}} \) | `float` | `0.7` | Discount for predicted-seed scores |
| `transition_min_norm` | `float` | `10^{-2}` | Min predicted-embedding norm to activate |
| `transition_reserved_slots` | `int` | `1` | Head slots reserved for predictive candidates |
| `transition_reserve_max_qsim` | `float` | `0.85` | Max q-pred similarity to trigger reserved slot |

---

## Key Invariants

1. All episode scores are in the same `[−1, 1]` cosine space — cosine-direct, spread-projection, and predictive-completion scores are directly comparable. Spread-projection applies a `0.85` discount (direct recall fires stronger than associative spreading).
2. Spreading + projection solves pattern completion: the activation-weighted centroid `q_spread` pulls the FAISS query toward associated prototype neighborhoods, surfacing episodes that direct cosine misses. Confirmed by `test_spreading_path_completion`: 2-hop path A→B→C retrieves eps_c via spread, 1-hop does not.
3. Only cosine-direct episodes receive reinforcement — prevents spread-projection from accumulating salience independently of direct relevance.
4. Temporal boost is additive, not multiplicative — it nudges ranking rather than dominating.
5. Salience gate modestly boosts well-consolidated prototypes during spreading (Hebbian: "fire together, wire together"), shaping `q_spread` toward high-evidence neighborhoods.
6. Multi-scale co-occurrence bonus (×1.25) rewards episodes confirmed by both CA3 (fine) and CA1 (coarse) prototype pathways.
7. Predictive completion respects a hard similarity gate: predictions too similar to the query (cos > 0.85) don't trigger reserved slots — it's not sequential reasoning if the prediction barely moved.
8. Spread-projection episodes with zero or negative inner product with `q_spread` are excluded — no positive associative evidence means no inclusion.
9. Diversity cap exempts cosine-direct episodes; spread-projection episodes are capped at `diversity_per_prototype` per prototype to prevent single-prototype saturation.
---

## Implementation Files

| File | What It Implements |
|------|-------------------|
| `slowave/latent/retrieval.py` | `RetrievalPipeline` — cosine-direct FAISS, spreading activation, `_spread_projection()` (q_spread computation + second FAISS), diversity cap, predictive-seed promotion, temporal boost, salience re-rank, multi-scale co-occurrence bonus, recall reinforcement |
| `slowave/latent/retrieval.py` | `RetrievalConfig` — all config parameters; `spread_episode_weight` / `spread_score_ceiling` retained for compatibility but superseded by `spread_episodic_top_k` / `spread_score_weight` |
| `slowave/core/services/retrieval.py` | `RetrievalService` — wraps `RetrievalPipeline` with schema mapping (episodes → schemas), working-memory gating, MMR dedup, budget trimming, cue-based blending |
| `slowave/core/services/retrieval.py` | `RecallResult` — structured result: schemas + episode texts + raw events + schema activations |
| `slowave/latent/temporal.py` | `TemporalContext` — multi-scale sinusoidal temporal embeddings used in Phase 5 temporal boost |
| `slowave/latent/transition_model.py` | `TransitionModel` — prototype-level transition counts, `predict()` for Phase 2b predictive completion |
| `slowave/latent/graph_manager.py` | `GraphManager` — prototype edge storage with fused weights (similarity + transition + coactivation), `neighbors()` for spreading |
| `slowave/latent/episodic_store.py` | `EpisodicStore` — FAISS-backed episodic embedding storage, `search()` for cosine-direct, `get_many()` for materialization |
| `slowave/latent/semantic_store.py` | `SemanticStore` — prototype centroid storage, `search()` / `search_by_scale()` for fine/coarse seeds, `get_many()` for centroid retrieval in `_spread_projection()`, `episodes_for_prototypes()` for multi-scale coarse-episode tracking |
| `slowave/latent/types.py` | `RetrievedMemorySet` — retrieval result: episodic memories + prototypes + expanded neighbors + optional `EpisodeDiagnostic` / `QueryDiagnostics` (populated when `diagnose=True`) |
