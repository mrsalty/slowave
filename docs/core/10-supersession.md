# 10 — Supersession Manifold

## Overview

The supersession manifold detects when a new memory **replaces** (supersedes) an old one, rather than being an unrelated addition. It uses the first right singular vector (SVD1) of a multi-domain seed set of (old, new) fact pairs. The resulting direction axis is a single vector in embedding space that best explains value-substitution across domains.

## Mathematical Formulation

### Seed Set

A fixed set of \( m \) (old_fact, new_fact) pairs spanning 7 domains and 5 languages:

\[
\mathcal{S} = \{(\text{old}_i, \text{new}_i)\}_{i=1}^m, \quad m = 20
\]

Domains: tech, medical, business, financial, HR, legal, science, + multilingual (IT/FR/DE).

Personal preference domain is excluded — geometrically anti-aligned with SVD1.

### Difference Matrix

Encode all texts, compute normalized difference vectors:

\[
\mathbf{d}_i = \frac{\text{encode}(\text{new}_i) - \text{encode}(\text{old}_i)}{\|\text{encode}(\text{new}_i) - \text{encode}(\text{old}_i)\|_2}
\]

Stack into matrix \( \mathbf{D} \in \mathbb{R}^{m \times d} \).

### SVD1 Direction

\[
\mathbf{D} = \mathbf{U} \mathbf{\Sigma} \mathbf{V}^T
\]

\[
\mathbf{v}_{\text{svd1}} = \mathbf{V}_{1,:} \quad (\text{first right singular vector})
\]

**Sign convention**: orient \( \mathbf{v}_{\text{svd1}} \) so the majority of seed pairs have positive alignment:

\[
\mathbf{v}_{\text{svd1}} \leftarrow -\mathbf{v}_{\text{svd1}} \quad \text{if} \quad \frac{1}{m}\sum_i \langle \mathbf{d}_i, \mathbf{v}_{\text{svd1}} \rangle < 0
\]

### Direction Score

For a candidate (new, old) pair:

\[
\text{dir}(\mathbf{e}_{\text{new}}, \mathbf{e}_{\text{old}}) = \left\langle \frac{\mathbf{e}_{\text{new}} - \mathbf{e}_{\text{old}}}{\|\mathbf{e}_{\text{new}} - \mathbf{e}_{\text{old}}\|_2}, \mathbf{v}_{\text{svd1}} \right\rangle
\]

Returns `0.0` if `‖diff‖ < 10^{-8}` (paraphrase / near-identical).

### Supersession Decision Logic

Given cosine similarity and direction score:

| Condition | Action |
|-----------|--------|
| Same scope, \( \cos \geq 0.85 \) + \( \text{dir} \geq 0.10 \) | Supersede old schema |
| Same scope, \( \cos \geq 0.85 \) + \( \text{dir} \in (-0.05, 0.05) \) | Flag `needs_review` |
| Same scope, \( \cos \geq 0.85 \) + \( \text{dir} < 0 \) | Reinforce old (contradiction) |
| Same scope, \( \cos \in [0.70, 0.85) \) + \( \text{dir} \geq 0.10 \) | Supersede (extended gate) |
| Cross-scope, \( \cos \geq 0.78 \) | Reinforce + cross-scope evidence |
| \( \cos \geq 0.35 \) | Mark topically related |

### Empirical Performance

- SVD1 axis separation (supersession vs. addition): **+0.35**
- Mean centroid separation: +0.09
- Cosine separation: +0.32
- SVD1 covers: tech, medical, business, financial, HR, legal, science, multilingual
- Personal preference: anti-aligned (−0.17) — excluded from seed set

## Configuration (Global Constants)

| Constant | Value | Description |
|----------|-------|-------------|
| `SAME_SCOPE_COS_THRESHOLD` | `0.85` | Cosine floor for same-scope action |
| `EXTENDED_SAME_SCOPE_COS_THRESHOLD` | `0.70` | Lower bound for extended same-scope gate |
| `CROSS_SCOPE_COS_THRESHOLD` | `0.78` | Cosine floor for cross-scope linking |
| `DIRECTION_THRESHOLD` | `0.10` | Minimum direction score for supersession |
| `DIR_REVIEW_BAND` | `(−0.05, 0.05)` | Direction range triggering needs_review |
| `TOPICAL_THRESHOLD` | `0.35` | Minimum similarity for topical relationship |

## Key Invariants

1. The SVD1 axis is computed once lazily and cached — `invalidate()` re-triggers computation (e.g., after encoder change).
2. Cross-scope schemas are **never** superseded — only reinforced with cross-scope evidence.
3. Direction score alone is never sufficient — must be combined with cosine ≥ threshold.
4. The extended gate (0.70–0.85) only triggers supersession when direction score is strongly positive — no reinforce or needs_review in this band.
5. SVD1 dimension normalization ensures all seed pairs contribute equally regardless of raw diff magnitude.