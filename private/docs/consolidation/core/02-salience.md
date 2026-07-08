# 02 — Salience Dynamics

## Overview

Salience is a per-memory scalar that controls three downstream behaviours: how likely an episode is to be sampled during replay, how much weight it contributes to retrieval ranking, and when it yields to a consolidated schema. There are **two parallel tracks** — episodic salience (managed by `SalienceEngine`, lives on `episodic_memories`) and schema salience (managed by `SchemaStore` + `FeedbackService`, lives on `schemas`). They are initialised differently, decay/reinforce through different mechanisms, and enter retrieval scoring through different normalisation paths.

## Data Flow

```
                         ┌─────────────────────────────────────────────────────┐
                         │               EPISODIC TRACK                        │
                         │                                                      │
  new episode ──────────►│ _episode_salience(emb)                               │
  (ingest)               │   novelty = (1 − nn_sim) / 2 · novelty_weight       │
                         │   surprise = 1 − pred·emb  (TransitionModel)        │
                         │   s₀ = max(0.01, novelty + 0.3·surprise)            │──► s₀ stored in DB
                         │   [remember: boost → min(1.5, s₀ + 0.6)]           │
                         │   [macro haircut → max(s₀·0.8, 0.05)]               │
                         └─────────────────────────────────────────────────────┘
                                         │
                         ┌──────────────────────────────┐
  replay runs ──────────►│ decay pass                   │  s ← max(min_s, s·exp(−Δt/τ))
                         └──────────────────────────────┘
                                         │
                         ┌──────────────────────────────┐
  replay samples ────────►│ proportional sampling        │  P(i) ∝ sᵢ
                         └──────────────────────────────┘
                                         │
                         ┌──────────────────────────────┐
  retrieval returns ────►│ recall reinforcement          │  s ← s + salience_weight
  (cosine-direct only)   └──────────────────────────────┘
                                         │
                         ┌──────────────────────────────┐
  consolidation ─────────►│ consolidation penalty        │  s ← max(min_s, s·γc)
                         └──────────────────────────────┘
                                         │
                                   retrieval score
                                   += salience_weight · s   (raw, no normalisation)

                         ┌─────────────────────────────────────────────────────┐
                         │               SCHEMA TRACK                          │
                         │                                                      │
  schema created ────────►│ s_schema = 0.5 + confidence                        │──► stored in DB
                         │                                                      │
  feedback signal ───────►│ s ← clamp(s + δ_feedback, 0.01, 20.0)             │
                         │                                                      │
                         │ retrieval score += salience_weight · norm(s_schema) │
                         │   norm(s) = 2/(1 + exp(−s/2)) − 1    [sigmoid]      │
                         └─────────────────────────────────────────────────────┘
```

## Mathematical Formulation

### Phase 1: Initial Salience at Encoding

**Novelty** (distance from nearest episodic neighbour):

\[
\text{novelty} = \max(s_{\min},\; w_n \cdot \tfrac{1 - \text{nn\_sim}}{2})
\]

Where:
- \( \text{nn\_sim} \in [-1, 1] \) = cosine similarity to the nearest episode in FAISS
- \( w_n \) = `novelty_weight` (default: `1.0`)
- \( s_{\min} \) = `min_salience` (default: `0.01`)

**Predictive surprise** (how much the transition model was wrong):

\[
\text{surprise} = \max(0,\;\min(1,\; 1 - \hat{e} \cdot e_{\text{new}}))
\]

Where \( \hat{e} \) is the `TransitionModel`'s predicted next embedding from the nearest episode. Returns `0.0` when the store is empty or the model is untrained (cold start).

**Initial salience** (combines both signals):

\[
s_0 = \max(0.01,\; \text{novelty} + 0.3 \cdot \text{surprise})
\]

**Logical concept**: Novelty gates salience by distance from known content; surprise gates by prediction error. Together they favour content that is both semantically new AND structurally unexpected, which captures consolidation-worthy events more reliably than novelty alone.

### Phase 2: Encoding Modifiers

Applied immediately after \( s_0 \), before storing:

**Macro-episode haircut** (applied first, macro episodes only):

\[
s_0 \leftarrow \max(s_0 \cdot 0.8,\; 0.05)
\]

**Logical concept**: Macro-episodes span entire sessions — they contain broad context but lack the atomic precision of single-event micro-episodes. The 20% haircut reduces their pull on replay sampling so that replay slots go preferentially to fine-grained events, while the floor of 0.05 ensures they are never fully excluded. This creates a deliberate granularity bias: micro-events are more likely to be replayed and consolidated.

**Remember-event boost** (applied if any event in the chunk has type `remember:*`):

\[
s_0 \leftarrow \min(1.5,\; s_0 + 0.6)
\]

**Logical concept**: The remember-boost (+0.6, capped at 1.5) ensures explicitly encoded memories compete well from the start. A user's deliberate `remember` act signals high encoding strength — the system should respect that signal by giving the memory immediate retrieval and replay priority, equivalent to a memory that has been repeatedly reinforced.

### Phase 3: Exponential Decay (Lazy)

Decay is **not continuous** — it runs during the replay engine's salience-decay pass. The reference timestamp `last_salience_ts` is updated whenever salience changes.

\[
s(t) = \max(s_{\min},\; s(t_0) \cdot e^{-(t - t_0)/\tau})
\]

Where:
- \( \tau \) = `tau_seconds` (default: `604800.0` s = 7 days)
- Half-life: \( t_{1/2} = \tau \ln 2 \approx 418,944\,\text{s} \approx 4.8\,\text{days} \)

**Logical concept**: Recency bias without explicit timestamps in retrieval. A memory that hasn't been recalled since yesterday has already decayed close to floor. If replay never runs, decay never runs — this is a known limitation.

### Phase 4: Proportional Sampling for Replay

\[
P(i) = \frac{\max(s_{\min}, s_i)}{\sum_j \max(s_{\min}, s_j)}
\]

**Logical concept**: higher-salience episodes are more likely to be selected for replay — this is the primary mechanism by which salience controls consolidation throughput. Using `max(s_min, s_i)` in both numerator and denominator guarantees that even floor-salience episodes retain non-zero probability (no episode is permanently invisible). Sampling without replacement prevents a single high-salience episode from consuming the entire replay batch. Ties are broken by the random draw.

### Phase 5: Recall Reinforcement

Applied only to **cosine-direct** episodes in the top-\(k\) result slice. Graph-harvested episodes are excluded.

\[
s \leftarrow s + \alpha_s
\]

Where \( \alpha_s \) = `RetrievalConfig.salience_weight` (default: `0.3`).

> **Note**: The reinforcement amount is `RetrievalConfig.salience_weight` (default `0.3`), not a field on `SalienceConfig`.

**Logical concept**: Memories used by the retriever get stronger — use-dependent potentiation. Restricting this to cosine-direct episodes prevents graph-harvested episodes from accumulating salience regardless of whether their content was relevant.

### Phase 6: Consolidation Penalty

Applied once per episode per consolidation event:

\[
s \leftarrow \max(s_{\min},\; s \cdot \gamma_c)
\]

Where \( \gamma_c \) = `consolidation_penalty` (default: `0.5`).

**Logical concept**: Once an episode's content is summarised into a schema, the hippocampal trace (episode) should cede to the cortical representation (schema). The penalty halves episodic salience, biasing future replay toward episodes not yet consolidated.

### Phase 7: Schema Salience at Creation

\[
s_{\text{schema}} = 0.5 + \text{confidence}
\]

Where `confidence` is the cosine similarity between the episode cluster centroid and the schema text embedding (range ≈ 0–1). Schema salience starts in `[0.5, 1.5]`.

**Logical concept**: The offset `0.5` gives new schemas an initial advantage over raw episodes (which start near `0.01`–`0.1`), reflecting the principle that consolidated knowledge should be more retrievable than unprocessed experience. The `confidence` term ties schema strength to the geometric quality of the cluster: tight, well-separated clusters (high centroid-text similarity) produce higher-confidence schemas that enter retrieval with stronger initial pull. Weak or noisy clusters start closer to the floor and must earn salience through positive feedback signals.

### Phase 8: Schema Salience via Feedback

\[
s \leftarrow \text{clamp}(s + \delta_f,\; 0.01,\; 20.0)
\]

Where \( \delta_f \) is the feedback signal label's delta (see Configuration). The ceiling `20.0` is enforced at the SQL level.

**Logical concept**: Schema salience is use-driven — positive feedback (`useful`, `partially_useful`) increases salience, negative signals (`irrelevant`, `stale`, `wrong`) decrease it. The asymmetric magnitudes (e.g., `+0.10` for useful vs `-0.30` for wrong) make correction faster than reward, so a schema that is confidently wrong is suppressed quickly. The floor (`0.01`) ensures even heavily penalized schemas are never fully erased — future evidence could rehabilitate them. The ceiling (`20.0`) prevents unbounded growth that would drown out cosine similarity in retrieval ranking.

### Phase 9: Schema Salience Normalization for Retrieval

Schema salience is **sigmoid-normalized** before entering the ranking score:

\[
s_{\text{norm}} = \frac{2}{1 + e^{-s/2}} - 1 \;\in [0, 1)
\]

\[
\text{score} \mathrel{+}= \alpha_s \cdot s_{\text{norm}}
\]

**Logical concept**: Raw schema salience can reach `20.0` after repeated reinforcement. Without normalization, `salience_weight * 20.0` would dominate the cosine term. The sigmoid compresses the range to `[0, 1)` while preserving monotonicity. Episodic salience (bounded approximately by the remember-boost cap of `1.5` in practice) enters raw without normalization.

## Configuration

### `SalienceConfig`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tau_seconds` \( \tau \) | `float` | `604800.0` | Exponential decay time constant (seconds); 7-day default → half-life ≈ 4.8 days |
| `min_salience` \( s_{\min} \) | `float` | `0.01` | Absolute floor — no episode fully erases |
| `novelty_weight` \( w_n \) | `float` | `1.0` | Scales the novelty term in \( s_0 \) |
| `surprise_weight` | `float` | `0.3` | Weight for the predictive-surprise term in \( s_0 \) |
| `consolidation_penalty` \( \gamma_c \) | `float` | `0.5` | Multiplicative penalty after consolidation |

### `RetrievalConfig` (salience-relevant fields)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `salience_weight` \( \alpha_s \) | `float` | `0.5` | Episodic recall reinforcement amount AND schema ranking weight |

### `FeedbackConfig` (schema salience deltas)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `useful_salience_delta` | `float` | `0.10` | \( \delta_f \) for `useful` feedback |
| `partially_useful_salience_delta` | `float` | `0.04` | \( \delta_f \) for `partially_useful` |
| `irrelevant_salience_delta` | `float` | `-0.05` | \( \delta_f \) for `irrelevant` |
| `stale_salience_delta` | `float` | `-0.20` | \( \delta_f \) for `stale` |
| `wrong_salience_delta` | `float` | `-0.30` | \( \delta_f \) for `wrong` |
| `min_salience` | `float` | `0.01` | Floor for schema salience after delta |

## Key Invariants

1. Episodic salience never drops below `min_salience` — floor enforced at decay, penalisation, and proportional sampling.
2. Decay is lazy: it only runs during the replay engine's salience-decay pass. An episode whose replay is never triggered retains its last-stored salience indefinitely.
3. Only cosine-direct episodes in the top-k receive recall reinforcement. Graph-harvested episodes are explicitly excluded (`retrieval.py:444–453`).
4. Episodic salience enters retrieval scoring raw; schema salience is sigmoid-normalized. Both are then multiplied by the same `salience_weight`.
5. Schema salience is bounded `[0.01, 20.0]` by SQL-level clamping; episodic salience has no upper ceiling in the schema but is practically bounded by the encoding cap of `1.5`.
6. The surprise contribution is `surprise_weight * surprise`; both the coefficient and the term are configurable via `SalienceConfig.surprise_weight`.

## Implementation Files

| File | What It Implements |
|------|-------------------|
| `slowave/latent/salience.py` | `SalienceConfig` dataclass; `SalienceEngine` (decay, novelty, penalize, sample_proportional) |
| `slowave/core/services/ingest.py` | `_episode_salience()` — initial s₀ with novelty+surprise; remember-boost; macro-haircut |
| `slowave/latent/replay_engine.py` | Lazy decay pass (`lines 300–308`); proportional sampling (`line 311`); consolidation penalty (`lines 390–394`) |
| `slowave/latent/retrieval.py` | Recall reinforcement via `increment_recall` (`lines 449–453`); episodic salience scoring term (`line 345`) |
| `slowave/core/services/retrieval.py` | `_norm_salience()` sigmoid; schema salience in ranking score (`line 316`) |
| `slowave/core/consolidation.py` | Schema salience initialisation `0.5 + confidence` (`line 277`) |
| `slowave/core/feedback.py` | `FeedbackConfig` with all delta fields; feedback routing to `update_salience` |
| `slowave/symbolic/schema_store.py` | Schema salience persistence; SQL cap at `20.0`; `update_salience()` with floor |
| `slowave/latent/episodic_store.py` | `increment_recall()` — raw SQL salience update; `update_salience()`; `list_saliences()` |

## Diagnostic Hooks

| Metric | What It Measures | How to Instrument |
|--------|-----------------|-------------------|
| Spearman ρ(episodic `salience`, `recalled_count`) | Whether salience predicts recall frequency — should be > 0.5 | `SELECT salience, recalled_count FROM episodic_memories` |
| Episodic salience distribution at t=0 / t=1d / t=7d / t=30d | Whether τ=604800s (7d) is calibrated to actual session cadence | Histogram of `salience` binned by age `(now − last_salience_ts)` |
| Fraction of episodes at floor (`salience ≤ min_salience + ε`) | Floor saturation — how many memories are effectively dead | `SELECT COUNT(*) WHERE salience <= 0.015` |
| `surprise > 0` fraction during ingest | Whether `TransitionModel` is trained and contributing | Log `surprise` field in episode metadata; compute non-zero fraction |
| Schema salience histogram | Whether feedback is differentiating schemas — bimodal expected | `SELECT salience FROM schemas ORDER BY salience` |
| Cosine-direct reinforce rate | Fraction of retrieved episodes that receive the recall boost | Count `increment_recall` calls vs total retrieval calls |

## Parameter Sensitivity

| Parameter | Direction | Effect | Sweep Range |
|-----------|-----------|--------|-------------|
| `tau_seconds` | ↑ | Memories stay warm longer; cross-session recall improves; stale content competes in replay longer | `[1800, 3600, 7200, 86400]` |
| `tau_seconds` | ↓ | Aggressive forgetting; cold-start after short breaks | — |
| `min_salience` | ↑ | More floor saturation; decayed memories retain replay probability | `[0.001, 0.01, 0.05]` |
| `novelty_weight` | ↑ | High-novelty content dominates early salience; familiar content deprioritised | `[0.5, 1.0, 2.0]` |
| `consolidation_penalty` | → 1.0 | Consolidated episodes retain most salience; compete with fresh content | `[0.3, 0.5, 0.7, 0.9]` |
| `consolidation_penalty` | → 0.0 | Consolidated episodes floor almost immediately | — |
| `RetrievalConfig.salience_weight` | ↑ | Recall reinforcement grows; heavy-use episodes could dominate sampling | `[0.1, 0.2, 0.3, 0.5]` |
| `FeedbackConfig.wrong_salience_delta` | more negative | Wrong memories suppressed faster; requires accurate user signals | `[-0.20, -0.30, -0.50]` |

## Known Failure Modes

| Symptom | Likely Cause | Diagnostic Signal |
|---------|-------------|-------------------|
| A small set of episodes dominate every replay batch | Salience runaway: frequently recalled episodes accumulate reinforcement faster than they decay | Gini coefficient of salience distribution; episodes with `recalled_count > 20` |
| Memories from a month ago unavailable | `tau_seconds` too short for use case — default 604800 (7d) means memories older than ~month are at floor | Salience histogram binned by age; check `now − last_salience_ts > 2592000` fraction |
| `surprise` always 0 | `TransitionModel` cold-start — no predictions until the model has been trained on at least one batch | `surprise` fraction in ingest metadata |
| `tau_seconds` too short for use case | Default 7d covers typical daily use; if sessions span months, consider increasing | Salience histogram binned by age — all memories near floor = tau too short |
| Schema salience not differentiating retrieval | Feedback signals are sparse or all `partially_useful` — deltas too small to create meaningful spread | Schema salience histogram; compare salience of `useful` vs `stale` labelled schemas |
| Decay never runs | Replay is disabled or not triggered; `last_salience_ts` never updates | Check `replay_engine.run()` call frequency; `last_salience_ts` age distribution |

## Relationship to Other Modules

| Module | Relationship |
|--------|-------------|
| `01-ingestion.md` | Ingest calls `_episode_salience()` to compute \( s_0 \); applies remember-boost and macro-haircut before storing |
| `03-replay.md` | Replay triggers the lazy decay pass; uses `sample_proportional` for episode selection; applies consolidation penalty after a consolidation event |
| `05-consolidation.md` | Consolidation sets initial schema salience (`0.5 + confidence`); consolidation event triggers episodic consolidation penalty |
| `06-retrieval.md` | Retrieval applies recall reinforcement to cosine-direct top-k; uses episodic salience (raw) and schema salience (sigmoid-normalized) as additive ranking terms |
| `08-feedback.md` | Feedback applies `salience_delta` to schemas; owns `FeedbackConfig` with all delta values |
| `07-temporal.md` | No direct coupling; temporal scores are independent ranking terms combined additively with salience |
