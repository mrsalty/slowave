# 04 — Graph Manager (Prototype Edges)

## Overview

The graph manager maintains a **sparse directed graph** over semantic prototypes. Each edge encodes a weighted relationship between two prototypes derived from three signals: semantic similarity, temporal transition probability, and co-occurrence frequency.

## Data Structure

A directed edge \((p \rightarrow q)\) with components:

\[
\text{edge}(p \rightarrow q) = (w_{\text{sim}}, w_{\text{trans}}, w_{\text{coact}}, w, \text{ts})
\]

Where \( w = \lambda_1 w_{\text{sim}} + \lambda_2 w_{\text{trans}} + \lambda_3 w_{\text{coact}} \) is the fused weight used for retrieval.

## Mathematical Formulation

### Edge Weight Fusion

\[
w_{pq} = \lambda_1 \cdot \cos(\mathbf{c}_p, \mathbf{c}_q) + \lambda_2 \cdot P(q \mid p) + \lambda_3 \cdot \text{coact}(p, q)
\]

Where:
- \( \cos(\mathbf{c}_p, \mathbf{c}_q) \) = cosine similarity of prototype centroids
- \( P(q \mid p) \) = empirical transition probability (EMA-accumulated)
- \( \text{coact}(p, q) \) = co-occurrence count (EMA-accumulated)

### EMA Accumulation

For transition and coactivation components, each replay pass produces a raw count; the stored value is an EMA:

\[
v_{\text{new}} = v_{\text{old}} \cdot \alpha_d + \text{count}_{\text{current}} \cdot (1 - \alpha_d)
\]

Where \( \alpha_d = \text{accumulate\_decay} \).

**Interpretation**: `accumulate_decay = 0.3` means 70% of the stored weight comes from the most recent pass, 30% from prior history. This makes the graph quickly responsive to new patterns while retaining some stability.

### Homeostatic Normalization

Per-source prototype, outgoing edges are normalized to a target L1 sum:

\[
w_{pq} \leftarrow w_{pq} \cdot \frac{T}{\sum_{q'} w_{pq'}}, \quad T = \text{homeostatic\_target}
\]

This prevents super-hubs (frequently co-occurring prototypes) from dominating all outgoing activation.

### Relative Pruning

After normalization, edges are pruned if:

\[
w_{pq} < \max(r_{\text{ratio}} \cdot \max_{q'} w_{pq'}, \; \tau_{\text{abs}})
\]

Where:
- \( r_{\text{ratio}} = \text{prune\_ratio} \) — relative to strongest outgoing edge
- \( \tau_{\text{abs}} = \text{prune\_below} \) — absolute floor

### Neighbor Retrieval

For spreading activation, the top-k outgoing edges from a prototype are fetched:

\[
\mathcal{N}(p, k) = \{(q, w_{pq}) \mid q \in \text{top-}k \text{ by } w_{pq} \text{ DESC}\}
\]

Where \( k = \text{neighbor\_top\_k} \) (used in activation propagation, default: `6`).

## Configuration

### `GraphConfig`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `top_k_similarity` | `int` | `8` | Max similarity edges per prototype |
| `top_k_coactivation` | `int` | `6` | Max coactivation edges per prototype |
| `prune_below` | `float` | `0.05` | Absolute pruning threshold |
| `lambda_similarity` \( \lambda_1 \) | `float` | `1.0` | Weight for cosine similarity component |
| `lambda_transition` \( \lambda_2 \) | `float` | `0.5` | Weight for transition probability |
| `lambda_coactivation` \( \lambda_3 \) | `float` | `0.3` | Weight for coactivation component |
| `accumulate_decay` \( \alpha_d \) | `float` | `0.3` | EMA decay (lower = faster adaptation) |
| `homeostatic_enabled` | `bool` | `True` | Enable homeostatic L1 normalization |
| `homeostatic_target` \( T \) | `float` | `0.5` | Target L1 sum per source |
| `prune_ratio` \( r_{\text{ratio}} \) | `float` | `0.2` | Relative pruning fraction of max |

## Key Invariants

1. Edges are directed — \( w_{pq} \neq w_{qp} \) in general.
2. The fused weight \( w \) is what's used in retrieval; component weights are stored for diagnostics.
3. Homeostatic normalization runs after every accumulation pass.
4. `accumulate_decay = 0.3` is aggressive — single-exposure traces fade quickly unless reinforced.
5. Similarity edges dominate the weight (λ₁ = 1.0) while transition (λ₂ = 0.5) and coactivation (λ₃ = 0.3) are secondary signals.