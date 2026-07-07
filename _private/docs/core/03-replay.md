# 03 — Replay Engine & Prototype Formation

## Overview

The replay engine is the **hippocampal replay** analogue: periodically, it samples a batch of episodic memories, assigns each to the nearest semantic prototype (or creates new ones), and updates the prototype graph edges. This is the bridge from raw episodic traces to stable semantic prototypes.

## Mathematical Formulation

### Step 1: Salience-Proportional Sampling

Sample \( N \) episodes without replacement:

\[
\mathcal{B} = \{e_i \sim P(i) \mid i = 1 \ldots N\}, \quad P(i) = \frac{s_i}{\sum_j s_j}
\]

Where \( N = \text{sample\_size} \) (default: `256`).

### Step 2: Prototype Assignment (Dual-Scale)

For each sampled episode \( e \) with embedding \( \mathbf{e} \):

For scale ∈ {fine, coarse}:

\[
\mathcal{P}_{\text{scale}} = \text{FAISS.search}(\mathbf{e}, \text{top\_k} = 1, \text{scale})
\]

Let \( p^* \) be the nearest prototype with centroid \( \mathbf{c}^* \), and let \( \cos^* = \langle \mathbf{e}, \mathbf{c}^* \rangle \).

**Dentate Gyrus gate (Stage 8, optional):**

When `use_pattern_separation = True`, find the runner-up prototype \( p' \) with similarity \( \cos' \):

\[
\text{distinctive\_sim} = \cos^* - \lambda_{\text{sep}} \cdot \cos'
\]

Where \( \lambda_{\text{sep}} = \text{dg\_separation\_lambda} \) (default: `0.3`).

If `distinctive_sim < assignment_threshold(scale)`, the episode creates a **new** prototype.

**Assignment threshold per scale:**

| Scale | Default Threshold | Brain Analogue |
|-------|------------------|----------------|
| `fine` | `assignment_threshold` (0.85) | CA3: high specificity |
| `coarse` | `coarse_assignment_threshold` (0.60) | CA1: broad clusters |

### Step 3: Prototype Update (Online Mean)

When episode \( e \) is assigned to prototype \( p \):

\[
\mathbf{c}_{\text{new}} = \frac{n \cdot \mathbf{c}_{\text{old}} + \mathbf{e}}{n + 1}
\]

\[
n_{\text{new}} = n_{\text{old}} + 1
\]

\[
\sigma^2_{\text{new}} = \frac{n-1}{n} \cdot \sigma^2_{\text{old}} + \frac{\|\mathbf{e} - \mathbf{c}_{\text{new}}\|^2}{n}
\]

For all prototypes \( p, q \) co-occurring in the replay batch:

**Similarity weight:**

\[
w_{\text{sim}}(p, q) = \cos(\mathbf{c}_p, \mathbf{c}_q)
\]

**Transition weight (EMA):**

\[
w_{\text{trans}}(p, q) \leftarrow w_{\text{trans}}(p, q) \cdot \alpha_d + \text{count}(p \rightarrow q) \cdot (1 - \alpha_d)
\]

**Coactivation weight (EMA):**

\[
w_{\text{coact}}(p, q) \leftarrow w_{\text{coact}}(p, q) \cdot \alpha_d + \text{count}(p, q) \cdot (1 - \alpha_d)
\]

Where \( \alpha_d = \text{accumulate\_decay} \) (default: `0.3`).

**Fused edge weight:**

\[
w(p, q) = \lambda_1 \cdot w_{\text{sim}}(p, q) + \lambda_2 \cdot w_{\text{trans}}(p, q) + \lambda_3 \cdot w_{\text{coact}}(p, q)
\]

| Parameter | Default | Weight |
|-----------|---------|--------|
| `lambda_similarity` \( \lambda_1 \) | `1.0` | Cosine similarity between centroids |
| `lambda_transition` \( \lambda_2 \) | `0.5` | Temporal succession probability |
| `lambda_coactivation` \( \lambda_3 \) | `0.3` | Co-occurrence in same batch |

### Step 5: Homeostatic Normalization

Per-source L1 normalization:

\[
w(p, q) \leftarrow w(p, q) \cdot \frac{T}{\sum_{q'} w(p, q')}, \quad T = \text{homeostatic\_target}
\]

Relative pruning:

\[
\text{prune } w(p, q) \text{ if } w(p, q) < \max(\tau_{\text{ratio}} \cdot \max_{q'} w(p, q'), \; \tau_{\text{abs}})
\]

Where:
- \( T = \text{homeostatic\_target} \) (default: `0.5`)
- \( \tau_{\text{ratio}} = \text{prune\_ratio} \) (default: `0.2`)
- \( \tau_{\text{abs}} = \text{prune\_below} \) (default: `0.05`)

### Step 6: Self-Supervised Rehearsal (Stage 5)

For selected prototypes (most recent member as probe):

1. Retrieve top-k episodes for probe embedding
2. **Misses**: siblings from other prototypes not retrieved → reinforce coactivation bridge (+`self_supervise_miss_reward`)
3. **Confusers**: foreign prototype episodes in results → penalize coactivation bridge (−`self_supervise_confuser_penalty`)
4. Skip prototypes with `needs_review` or `contradicting_episode_ids` schemas (dentate gyrus gate)

## Configuration

### `ReplayConfig`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sample_size` | `int` | `256` | Episodes sampled per replay pass |
| `max_prototypes_per_replay` | `int` | `32` | Max new prototypes per pass |
| `assignment_threshold` | `float` | `0.85` | Cosine threshold for CA3 (fine) |
| `coarse_assignment_threshold` | `float` | `0.60` | Cosine threshold for CA1 (coarse) |
| `transition_batch_size` | `int` | `64` | Batch for transition counting |
| `transition_steps` | `int` | `50` | Max temporal steps for transitions |
| `use_pattern_separation` | `bool` | `False` | Dentate gyrus pattern separation |
| `dg_separation_lambda` | `float` | `0.3` | Runner-up penalty strength |
| `self_supervise` | `bool` | `True` | Self-supervised rehearsal |
| `self_supervise_max_prototypes` | `int` | `32` | Max prototypes probed |
| `self_supervise_min_members` | `int` | `3` | Min members to probe |
| `self_supervise_top_k` | `int` | `8` | Top-k retrieval for probe |
| `self_supervise_miss_reward` | `float` | `0.5` | Coactivation boost for misses |
| `self_supervise_confuser_penalty` | `float` | `0.25` | Coactivation penalty for confusers |

## Key Invariants

1. Prototype centroids are online means — converge over multiple passes.
2. Edge weights EMA with `accumulate_decay = 0.3` — 70% current pass, 30% history.
3. Homeostatic normalization prevents super-hub dominance.
4. Self-supervised rehearsal is failure-driven: only misses/confusers produce signals.
5. Contradicted/review schemas are excluded from rehearsal probes (dentate gyrus gate).