# 06 — Retrieval Pipeline

## Overview

The retrieval pipeline combines two complementary mechanisms: **direct cosine similarity** (exact FAISS search) and **spreading activation** over the prototype graph (pattern completion). Results are scored, merged, temporally boosted, and salience-re-ranked.

## Mathematical Formulation

### Phase 1: Query Encoding

\[
\mathbf{q} = \text{encode}(query) \in \mathbb{R}^d, \quad \|\mathbf{q}\|_2 = 1
\]

### Phase 2: Cosine-Direct Retrieval

FAISS search over episodic embeddings:

\[
\mathcal{C} = \{ (i, s_i) \mid i \in \text{FAISS.search}(\mathbf{q}, k_e), \; s_i = \langle \mathbf{q}, \mathbf{e}_i \rangle \}
\]

Where \( k_e = \text{episodic\_top\_k} \) (default: `10`).

Prototype search:

\[
\mathcal{P}_{\text{seed}} = \{ (j, s_j) \mid j \in \text{SemanticStore.search}(\mathbf{q}, k_s), \; s_j = \langle \mathbf{q}, \mathbf{c}_j \rangle \}
\]

Where \( k_s = \text{semantic\_top\_k} \) (default: `6`).

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
- \( \alpha = \text{spread\_decay} \) (default: `0.6`) — retention factor
- \( \mathcal{N}_{\text{in}}(p) \) = prototypes with outgoing edges to \( p \)
- \( w_{qp} \) = stored edge weight (fused similarity + transition + coactivation)

**Pruning**: below \( \text{spread\_activation\_floor} \) (default: `10^{-3}`), activation is zeroed each step.

**Salience gate** (optional): final activation modulated by prototype support:

\[
a_{\text{final}}(p) = a(p) \cdot (1 + 0.1 \cdot \sqrt{1 + \text{support\_count}(p)})
\]

### Phase 4: Episode Harvesting

From each activated prototype, harvest member episodes:

\[
\mathcal{H} = \bigcup_{p \;:\; a(p) > 0} \{ (e, a(p) \cdot w_{\text{spread}}) \}
\]

Where \( w_{\text{spread}} = \text{spread\_episode\_weight} \) (default: `0.15`).

**Score ceiling**: graph-harvested scores are capped at:

\[
s_{\text{harvest}} \leq \gamma_{\text{ceiling}} \cdot \min_{e \in \mathcal{C}} s_e
\]

Where \( \gamma_{\text{ceiling}} = \text{spread\_score\_ceiling} \) (default: `0.9`).

**Diversity cap**: at most `diversity_per_prototype` (default: `2`) episodes per prototype from graph harvest.

### Phase 5: Temporal Boost (Stage 7)

For each candidate episode \( e \) with timestamp \( t_e \):

\[
s_{\text{temporal}}(e) = \alpha_t \cdot \cos(\mathbf{t}_q, \mathbf{t}_e)
\]

Where:
- \( \mathbf{t}_q \) = temporal embedding of the query anchor timestamp
- \( \mathbf{t}_e \) = temporal embedding of the episode timestamp
- \( \alpha_t = \text{temporal\_weight} \) (default: `0.25`)

Temporal embeddings are multi-scale sinusoidal (see §07 — Temporal Context).

### Phase 6: Salience Re-Ranking

Final score for each episode:

\[
s_{\text{final}}(e) = \underbrace{\cos(\mathbf{q}, \mathbf{e})}_{\text{semantic}} + \underbrace{\alpha_t \cdot \cos(\mathbf{t}_q, \mathbf{t}_e)}_{\text{temporal}} + \underbrace{\alpha_s \cdot s_{\text{salience}}(e)}_{\text{salience}}
\]

Where \( \alpha_s = \text{salience\_weight} \) (default: `0.3`).

For graph-harvested episodes, the semantic component is replaced by the harvest score (capped).

### Phase 7: Reinforcement

Only cosine-direct episodes in the top slice receive recall reinforcement (+`salience_weight` to salience, +1 to `recalled_count`). Graph-harvested episodes do not receive reinforcement to prevent self-rewarding feedback loops.

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
| `episodes_per_prototype` | `int` | `6` | Episodes harvested per prototype |
| `spread_episode_weight` | `float` | `0.15` | Base score for graph-harvested episodes |
| `spread_score_ceiling` | `float` | `0.9` | Max harvest score relative to cosine |
| `salience_gate` | `bool` | `True` | Enable support-count modulation |
| `diversity_per_prototype` | `int` | `2` | Max graph episodes per prototype |
| `use_temporal` | `bool` | `True` | Enable temporal proximity bonus |
| `temporal_weight` \( \alpha_t \) | `float` | `0.25` | Temporal contribution to final score |

## Key Invariants

1. Cosine-direct episodes always outrank graph-harvested ones (score ceiling + low base weight).
2. Spreading activation solves pattern completion: episodes with weak cosine matches can still be retrieved if reachable through high-weight edges.
3. Only cosine-direct episodes receive reinforcement — prevents graph self-reinforcement.
4. Temporal boost is additive, not multiplicative — it nudges ranking rather than dominating.
5. Salience gate modestly boosts well-consolidated prototypes (Hebbian: "fire together, wire together").