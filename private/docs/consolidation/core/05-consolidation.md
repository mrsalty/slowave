# 05 — Consolidation (Prototypes → Schemas)

## Overview

Consolidation lifts replayed latent prototypes into first-class symbolic schemas — durable typed claims with embeddings, salience, and relational edges — stored in SQLite with FTS indexing. The pipeline is orchestrated by `ConsolidationService`, which runs one replay pass (ReplayEngine), one latent consolidation pass (Consolidator), and one decay pass (SchemaStore) per invocation. The entire path is brain-only: zero LLM calls. Schemas are built from prototype geometry (centroids, PCA facet axes) and contrastive lexical signatures against the global schema corpus.

The pipeline is triggered by the background worker at regular intervals, or manually via `slowave consolidate` (CLI) / `engine.consolidate_once()` (Python API).

## Data Flow

```
                                            ConsolidationService
                    ┌────────────────────────────┼───────────────────────────────┐
                    ▼                            ▼                               ▼
          ReplayEngine.replay_once()   Consolidator.consolidate()       SchemaStore.decay_unused()
          ┌─ replay sampled episodes   ┌─ for each prototype:          ┌─ active schemas
          │  └→ update centroids       │   ┌─ gate explicit-remembers  │   └→ recurrence_count == 0
          │  └→ build graph edges      │   ├─ LatentSchemaBuilder     │     └→ first_formed_ts > idle
          │  └→ train transition       │   │  .build()                 │       └→ salience -= 0.15
          └──────────┬─────────────────┤   ├─ _write_latent_schema()   │         └→ flag needs_review
                     │                 │   │  ├─ near-dup guard        │           if salience < 0.30
                     │                 │   │  ├─ classification        │
                     │                 │   │  ├─ schema creation        │
                     │                 │   │  └─ geometric judge       │
                     │                 │   └─ _record_debug()          │
                     └─────────────────┴───────────────────────────────┘
```

## Mathematical Formulation

### Phase 1: Prototype Selection & Gating

Consolidation receives a list of prototype IDs from the ingest service. For each prototype \( p \) with centroid \( \mathbf{c}_p \in \mathbb{R}^d \) and member episode IDs \( \{e_1, \ldots, e_m\} \):

\[
\text{members}(p) = \{\, e_i \mid (p, e_i) \in \text{episode\_prototype\_map} \,\}
\]

**Explicit-remember gate:** If every raw event behind the sampled episodes is a `remember:*` event, the prototype is skipped — `remember()` already created first-class schemas synchronously, and re-consolidation would produce composite near-duplicates from adjacent remembers merged into one macro-episode. Instead, the consolidator links related schemas via the prototype centroid:

\[
\text{link\_schemas}(\mathbf{c}_p) = \text{add\_relation}(\text{top}_1, \text{top}_2, \text{"reinforces"})
\]

Where \( \text{top}_1, \text{top}_2 \) are the two closest active schemas by cosine similarity to \( \mathbf{c}_p \), requiring \( \cos(\mathbf{c}_p, \text{top}_1) \geq 0.65 \) and \( \cos(\mathbf{c}_p, \text{top}_2) \geq 0.60 \).

### Phase 2: Latent Schema Building (`LatentSchemaBuilder.build`)

For a prototype with centroid \( \mathbf{c} \) and member embedding matrix \( \mathbf{E} \in \mathbb{R}^{m \times d} \), the builder computes:

**Temporal anchor:**

\[
\bar{t} = \frac{1}{m}\sum_{i=1}^{m} t_i, \qquad \Delta t = \max(t_i) - \min(t_i)
\]

Where \( t_i \) are Unix timestamps of member episodes.

**Central member** (episode closest to centroid):

\[
i^* = \arg\max_i \; \frac{\mathbf{e}_i \cdot \mathbf{c}}{\|\mathbf{e}_i\| \cdot \|\mathbf{c}\| + \epsilon}
\]

The central member's `source_content` (or `content_text` fallback) becomes the schema's human-readable claim text — derived from latent state, not the substrate.

**Facet axes** (within-cluster principal directions, requires \( m \geq 3 \)):

\[
\mathbf{E}_{\text{centered}} = \mathbf{E} - \mathbf{1} \mathbf{c}^\top, \qquad \mathbf{U} \boldsymbol{\Sigma} \mathbf{V}^\top = \text{SVD}(\mathbf{E}_{\text{centered}})
\]

\[
\mathbf{F} = \mathbf{V}_{1:k}^\top \in \mathbb{R}^{k \times d}, \quad k = \min(\text{n\_facet\_axes}=4, \; m)
\]

The facet axes encode *what dimensions the cluster's members differ on* — the geometric fingerprint of within-concept variance.

**Confidence** (cluster tightness):

\[
\sigma^2_{\text{within}} = \frac{1}{m}\sum_{i=1}^{m} \|\mathbf{e}_i - \mathbf{c}\|^2, \qquad \text{conf} = 1 - \min\!\left(1,\; \frac{\sigma^2_{\text{within}}}{\max(v_{\text{floor}}, 10^{-6})}\right)
\]

\[
0 \leq \text{conf} \leq 1, \qquad v_{\text{floor}} = 10^{-2}
\]

Where \( v_{\text{floor}} \) is the variance floor (`variance_floor`). For unit-norm embeddings in 384-d space, a tight cluster has \( \sigma^2_{\text{within}} \approx 3 \times 10^{-4} \), yielding \( \text{conf} \approx 0.97 \). A loose cluster with \( \sigma^2_{\text{within}} \geq 10^{-2} \) yields \( \text{conf} = 0 \). With fewer than 2 members, \( \text{conf} = 1.0 \) by default.

**Logical concept**: Confidence is the cluster's cohesion score — tight clusters represent precise, well-evidenced concepts; loose clusters represent noisy or heterogeneous groupings. This value feeds into the geometric judge (Phase 4) and the schema's initial salience (\( 0.5 + \text{conf} \)).

**Lexical signature** (contrastive TF-IDF, Stage 7a):

\[
\text{score}(\tau) = \text{tf}_{\text{cluster}}(\tau) \cdot \log\!\left(1 + \frac{N_{\text{corpus}}}{1 + \text{df}_{\text{corpus}}(\tau)}\right)
\]

\[
\text{tf}_{\text{cluster}}(\tau) = \frac{\text{count of } \tau \text{ in cluster texts}}{\text{total tokens in cluster}}
\]

Where \( \text{df}_{\text{corpus}}(\tau) \) is the document frequency of term \( \tau \) across the global background corpus (up to 500 existing schema content texts). The contrastive IDF suppresses generic terms that appear everywhere; it boosts terms rare in the corpus but common within this cluster. The top 8 scored terms form the `lexical_signature` dict, and the top 3 form the `display_label` (e.g. `"faiss / sqlite / local"`).

**Logical concept**: The lexical signature is deterministic and fully geometry-grounded — no LLM. It serves as a human-readable label for the cluster and as a lightweight retrieval cue. When no background corpus is available, the cluster's own texts serve as the corpus (intra-cluster distinctiveness only).

**VSA encoding** (default: geometric mode):

The full centroid \( \mathbf{c} \) and the facet axes \( \mathbf{F} \) are bound into a VSA hypervector via `build_schema_vsa()`. This vector is stored in the schema's facets as a base64-encoded blob for future VSA-based retrieval experiments; it does not affect current retrieval.

**Support count:** \( s = m \) — how many member episodes back this schema.

### Phase 3: Schema Persistence & Deduplication (`_write_latent_schema`)

#### 3a. Near-duplicate guard

Before creating a new schema, the consolidator searches for the closest existing active schema by cosine similarity:

\[
\text{near\_dup}(\mathbf{c}) = \text{search\_embedding}(\mathbf{c}, \; \text{limit}=1)
\]

If \( \cos(\mathbf{c}, \text{near\_dup}) \geq 0.92 \) and the existing schema is `active`, the new schema is **not** created. Instead, the existing schema is reinforced:

\[
\text{reinforce\_schema}(\text{near\_dup.id}, \; \text{evidence, confidence})
\]

This prevents every consolidation pass from re-encoding the same concept into a duplicate. If the new schema's scope differs from the existing one, `cross_scope_reinforcement_count` is incremented.

#### 3b. Best related schema

If no near-duplicate is found, the consolidator finds the single most-related existing schema:

1. **Embedding search**: `search_embedding(centroid, limit=5, include_inactive=False)` — returns the top result with \( \cos \geq 0.72 \)
2. **FTS fallback**: `search_fts(claim, limit=3)` — text-search fallback if embedding search returns nothing

If no related schema is found, the new schema is created with outcome `"created"`.

#### 3c. Schema classification

Consolidated schemas are classified by provenance and structure:

\[
\text{schema\_class} = \begin{cases}
\text{None} & \text{if } \text{source\_kind} = \text{"explicit\_remember"} \\
\text{"episodic\_summary"} & \text{if } |\text{sentences}| \geq 3 \;\lor\; \text{len}(\text{text}) > 300 \\
\text{"fact"} & \text{otherwise}
\end{cases}
\]

#### 3d. Schema creation

New schemas are inserted into `schemas` with:
- Content text = canonicalized claim
- Initial salience = \( 0.5 + \text{conf} \)
- Embedding = float32 centroid (L2-normalized)
- `schema_prototype_map` linking to source prototype
- `schema_evidence` rows for each member episode (weight=1.0)
- FTS5 index updated
- `dedupe=True` — text-normalized duplicate check within same scope merges instead of inserting

### Phase 4: Geometric Contradiction Detection (`GeometricContradictionJudge.judge`)

When a related existing schema is found (Phase 3b) and its embedding is retrievable, the geometric judge compares the old and new `LatentSchema`:

#### Step 1: Centroid similarity

\[
\cos_{ab} = \frac{\mathbf{a} \cdot \mathbf{b}}{\|\mathbf{a}\| \cdot \|\mathbf{b}\| + \epsilon}, \quad \mathbf{a} = \text{centroid}_{\text{old}}, \; \mathbf{b} = \text{centroid}_{\text{new}}
\]

\[
\Delta t = t_{\text{new}} - t_{\text{old}}
\]

#### Step 2: Verdict routing

\[
\text{verdict} = \begin{cases}
\text{"unrelated"} & \text{if } \cos_{ab} < 0.75 \\
\text{"reinforces"} & \text{if } \cos_{ab} \geq 0.95 \\
\text{contradiction\_test} & \text{if } 0.75 \leq \cos_{ab} < 0.95
\end{cases}
\]

#### Step 3: Facet-axis distance (contradiction test)

When centroids are close but not maximally similar, the judge compares facet axes:

\[
\phi_i = \frac{|\mathbf{f}_{\text{old},i} \cdot \mathbf{f}_{\text{new},i}|}{\|\mathbf{f}_{\text{old},i}\| \cdot \|\mathbf{f}_{\text{new},i}\| + \epsilon}, \qquad d_{\text{facet}} = 1 - \frac{1}{k} \sum_{i=1}^{k} \phi_i, \quad k = \min(k_{\text{old}}, k_{\text{new}})
\]

\[
\text{verdict} = \begin{cases}
\text{"contradicts"} & \text{if } d_{\text{facet}} \geq 0.35 \\
\text{"refines"} & \text{if } d_{\text{facet}} < 0.35
\end{cases}
\]

If either schema has zero facet axes (fewer than 3 member episodes), \( d_{\text{facet}} = 0.0 \).

**⚠ In practice, via `Consolidator._write_latent_schema`, this is not a rare edge case — it is the ALWAYS case for the *old* schema.** `_write_latent_schema` reconstructs the old (existing) schema's `LatentSchema` view with `facet_axes=np.zeros((0, dim))` unconditionally, because raw facet axes are never persisted anywhere retrievable — they are only bound lossily into the VSA hypervector blob described below, which cannot be inverted back into the original axis matrix. This means \( k_{\text{old}} = 0 \) on every real invocation of this path, so \( d_{\text{facet}} = 0.0 \) always, regardless of the *new* schema's actual member count or facet-axis divergence. **The `"contradicts"` verdict is therefore provably unreachable via `Consolidator._write_latent_schema`, not merely rare** — confirmed by `tests/unit/test_contradicts_verdict_unreachable.py` (2026-07-09), which shows the real (unmocked) judge always returns `"refines"` here even when the new schema's facet axes are maximally divergent (orthonormal, sign-flipped, or random) from any hypothetical old structure. The B1/B2 StaleMemory ablation runs confirm this empirically: 0 `contradicts` verdicts across 26,250 real prototypes. Existing tests in `test_contradiction_support_gate.py` did not catch this because they all mock `judge.judge()` directly to inject a `"contradicts"` verdict, testing only the downstream support/recency gates.

**Logical concept**: Two schemas conflict when their centroids are close (same topic) but their facet axes disagree (different *aspect* of that topic). The brain analogue is predictive coding — a mismatch on facet axes is a prediction error that triggers reconsolidation. `"refines"` means the axes agree but not perfectly: the newer schema is a tighter, more precise formulation of the same concept. **This mechanism is currently non-functional for the `_write_latent_schema` path** — fixing it would require persisting the old schema's facet axes/strengths in a retrievable form (e.g. a new BLOB column, mirroring how the centroid embedding is stored) rather than only the current VSA-encoded blob.

#### Step 4: Supersession gates

When the verdict is `"contradicts"`, two hard gates prevent premature supersession:

**Support gate:**

\[
\text{supersede\_eligible} = (s_{\text{new}} \geq \text{min\_support\_to\_supersede} = 2)
\]

A schema backed by only 1 episode should not bury a well-established one.

**Recency gate:**

\[
\text{supersede\_eligible} \;\land\; (|\Delta t| > \text{min\_time\_delta\_to\_supersede\_s} = 3600)
\]

Near-simultaneous contradictions (within 1 hour) are treated as reinforcement rather than supersession — they reflect rapid toggling, not genuine belief revision.

If both gates pass and \( \Delta t > 0 \):

\[
\text{relation} = \text{"supersedes"}, \qquad \text{old\_status} = \text{"superseded"}
\]

If both gates pass and \( \Delta t \leq 0 \):

\[
\text{relation} = \text{"contradicts"}, \qquad \text{old\_status} = \text{"contradicted"}
\]

The old schema's status is transitioned and its salience is set to 0.05 to suppress it in retrieval. A `schema_relations` edge is created with the appropriate relation type.

If either gate fails, the verdict is downgraded to `"reinforced"` — the new schema is created but the old one is not touched.

### Phase 5: Schema Relations & Cross-Scope Links

When the verdict is `"reinforces"` or `"refines"`, a relation edge is created without touching the old schema's status:

\[
\text{add\_relation}(\text{new\_id, old\_id, relation, confidence})
\]

Cross-scope reinforcement: when the new schema's scope differs from the related schema's scope, `cross_scope_reinforcement_count` is incremented on the old schema. This breaks the bootstrap deadlock where stage-0 schemas can never accumulate cross-scope evidence without already being promoted.

### Phase 6: Schema Decay (`decay_unused`)

Active schemas that have never been recalled and are older than `idle_days` suffer a salience penalty:

\[
s_i \leftarrow \max(0.01,\; s_i - 0.15)
\]

\[
\text{flag\_review} = (s_i < 0.30)
\]

Explicit-remember schemas (`source_kind == "explicit_remember"`) and schemas with `recurrence_count > 0` are exempt — the user asked to keep those, and recalled schemas have proven utility.

Brain analogue: memories never activated during waking or sleep weaken over time (synaptic downscaling). This is a lazy background pass, not a per-consolidation operation — it runs at the end of `consolidate_once()`.

---

## Configuration

### `Consolidator` Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_episodes_per_prototype` | `int` | `8` | Max member episodes sampled per prototype for schema building |

### `LatentSchemaConfig` (`slowave/latent/schema.py`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n_facet_axes` \( k \) | `int` | `4` | Number of principal PCA directions retained as facet axes |
| `variance_floor` \( v_{\text{floor}} \) | `float` | `10^{-2}` | Floor for within-cluster variance when computing confidence; calibrated to 384-d unit-norm space |
| `min_members_for_facets` | `int` | `3` | Minimum member count to compute facet axes via SVD |

### `GeometricJudgeConfig` (`slowave/latent/schema.py`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `same_topic_cosine` \( \tau_{\text{same}} \) | `float` | `0.75` | Minimum centroid cosine for two schemas to be "about the same thing" |
| `reinforce_cosine` \( \tau_{\text{reinforce}} \) | `float` | `0.95` | Cosine above which schemas are judged as reinforcing |
| `contradicts_facet_dist` \( \tau_{\text{contra}} \) | `float` | `0.35` | Facet-axis distance above which schemas contradict rather than refine |
| `min_support_to_supersede` | `int` | `2` | Minimum support count (member episodes) for new schema to supersede |
| `min_time_delta_to_supersede_s` | `float` | `3600` | Minimum time delta (seconds) for new schema to supersede an older one |
| `near_dup_guard_cosine` | `float` | `0.92` | Cos ≥ this in `Consolidator._write_latent_schema`'s near-dup guard → reinforce existing active schema instead of creating new/reaching the judge. Exposed via `SlowaveConfig.judge` (plans/05-consolidation.md B2 ablation); was hardcoded until 2026-07-09 |
| `related_schema_cosine` | `float` | `0.72` | Cos ≥ this in `Consolidator._best_related_schema` → treat as semantically related and pass to the geometric judge. Also exposed via `SlowaveConfig.judge`; was hardcoded until 2026-07-09 |

### Explicit-remember Link Cosine (hardcoded in Consolidator)

| Constant | Value | Description |
|----------|-------|-------------|
| Explicit-remember link cosine | `0.65` / `0.60` | Min cosine for top-1 / top-2 schemas when linking via centroid (`_link_schemas_via_prototype_centroid`) |

### Decay Parameters (hardcoded in `decay_unused`)

| Parameter | Value | Description |
|-----------|-------|-------------|
| `decay_amount` | `0.15` | Salience subtracted per decay pass |
| `review_threshold` | `0.30` | Salience below this → flagged `needs_review` |
| Salience floor | `0.01` | Minimum salience after decay (never goes to zero) |

---

## Key Invariants

1. **Zero LLM calls** — every consolidation path (building, judging, classifying) is pure geometry and contrastive TF-IDF. No model inference.
2. **Explicit remembers are never re-consolidated** — `_episodes_all_explicit_remember()` gates out prototypes whose episodes are purely from `remember()` calls, preventing composite near-duplicates. They still populate schema relations via `_link_schemas_via_prototype_centroid()`.
3. **Near-duplicate guard prevents duplicate schemas** — cosine ≥ 0.92 against any active schema reinforces the existing one instead of creating a new one.
4. **Missing embeddings cannot trigger supersession** — `_fetch_schema_embedding()` returning `None` short-circuits the geometric judge; the new schema is created without a verdict. Confirmed by `test_missing_embedding_supersession.py`.
5. **Contradiction requires both support AND recency gates** — a single-episode or near-simultaneous contradiction is downgraded to reinforcement. Confirmed by `test_contradiction_support_gate.py`.
6. **Cross-scope schemas are never superseded** — the geometric judge makes no scope-based decisions. Cross-scope evidence is recorded as `cross_scope_reinforcement_count`, feeding into generalization stage promotion (see 09-context).
7. **Explicit-remember schemas are exempt from decay** — `decay_unused()` skips schemas with `source_kind == "explicit_remember"` or `recurrence_count > 0`.
8. **Schema confidence = 1.0 for singleton prototypes, 0.0 for loose clusters** — bounded in [0, 1], driven by within-cluster variance relative to `variance_floor`.
9. **Facet axes require ≥ 3 members** — below this threshold, `facet_axes` is a zero matrix and `facet_strengths` is empty. The geometric judge treats facet distance as 0.0 in this case.
10. **Superseded/contradicted schemas get salience 0.05** — they remain in the DB (for provenance and relation edges) but are suppressed from retrieval.

---

## Implementation Files

| File | What It Implements |
|------|-------------------|
| `slowave/core/consolidation.py` | `Consolidator` — prototype iteration, schema building delegation, `_write_latent_schema()`, explicit-remember gate, near-duplicate guard, geometric verdict routing, schema classification, related-schema linking, debug recording |
| `slowave/core/consolidation.py` | `ConsolidationStats` — frozen dataclass with outcome counters |
| `slowave/core/consolidation.py` | `_classify_consolidated_schema()` — structure-based classification (fact vs episodic_summary) |
| `slowave/core/services/consolidation.py` | `ConsolidationService` — orchestrates replay + consolidation + decay in one pass, writes `worker_runs` rows |
| `slowave/latent/schema.py` | `LatentSchema` — frozen dataclass: centroid, facet axes/strengths, temporal anchor, confidence, lexical signature, VSA vector |
| `slowave/latent/schema.py` | `LatentSchemaConfig` — builder configuration dataclass |
| `slowave/latent/schema.py` | `LatentSchemaBuilder` — `.build()` method: SVD facet axes, confidence, contrastive TF-IDF, VSA encoding |
| `slowave/latent/schema.py` | `GeometricContradictionJudge` — `.judge()` method: centroid similarity → facet-axis distance → verdict (reinforces/refines/contradicts/unrelated) |
| `slowave/latent/schema.py` | `GeometricJudgeConfig` — judge configuration dataclass |
| `slowave/latent/schema.py` | `_build_lexical_signature()` — contrastive TF-IDF: term scoring, corpus vs cluster document frequencies |
| `slowave/symbolic/schema_store.py` | `SchemaStore.create()` — schema insertion with deduplication, FTS indexing, evidence rows |
| `slowave/symbolic/schema_store.py` | `SchemaStore.reinforce_schema()` — merge provenance, salience boost, confidence max-merge, facet/tag stability |
| `slowave/symbolic/schema_store.py` | `SchemaStore.decay_unused()` — lazy salience decay for idle unreinforced schemas |
| `slowave/symbolic/schema_store.py` | `SchemaStore.add_relation()` — upsert relation edges (reinforces/refines/contradicts/supersedes) |
| `slowave/symbolic/schema_store.py` | `SchemaStore.update_status()` — transition schema status + salience |
| `slowave/symbolic/schema_store.py` | `SchemaStore.increment_cross_scope_reinforcement()` — cross-scope evidence counter |
| `slowave/symbolic/schema_store.py` | `SchemaStore.search_embedding()` — Python-side cosine search over BLOB embeddings (used by near-dup guard and related-schema lookup) |
| `slowave/symbolic/schema_store.py` | `SchemaStore.search_fts()` — FTS5 fallback for text-based related-schema lookup |
| `slowave/core/engine.py` | `SlowaveEngine` — constructs `Consolidator` (lines 215-225), wires `_episodic_store_ref`, delegates `consolidate_once()` / `decay_schemas()` |
| `tests/unit/test_contradiction_support_gate.py` | 4 tests: support gate, recency gate, full contradiction path, default config values |
| `tests/unit/test_missing_embedding_supersession.py` | 3 tests: consolidation path with None embedding, judge-called-with-valid-embedding regression, engine remember() path |
| `tests/unit/test_latent_schema.py` | LatentSchemaBuilder unit tests |
| `tests/unit/test_contrastive_tfidf.py` | Contrastive TF-IDF lexical signature tests |
| `tests/unit/test_schema_utility.py` | Schema utility score and decay tests |
| `tests/unit/test_engine_consolidate.py` | End-to-end consolidate_once with created schemas |

---

## Diagnostic Hooks

| Metric | What It Measures | How to Instrument |
|--------|-----------------|-------------------|
| `near_dup_reinforced` | Fraction of schemas blocked by the 0.92 near-duplicate guard | Log when `_write_latent_schema` returns `"reinforced"` from the near-dup path vs the geometric-judge path |
| `explicit_gate_skipped` | Fraction of prototypes skipped because all episodes are explicit remembers | Counter in `_consolidate_latent` — already available via `ConsolidationStats.schemas_skipped` but conflated with other skip reasons; separate it |
| `missing_embedding_fallback` | How often `_fetch_schema_embedding` returns None → created without verdict | Log warning in `_write_latent_schema` already exists; add a counter |
| `contradiction_rate` | Fraction of geometric verdicts returning "contradicts" | Already available via `ConsolidationStats.schemas_contradicted` |
| `verdict_distribution` | Distribution of geometric verdicts (unrelated / reinforces / refines / contradicts) | Add per-verdict counters to `ConsolidationStats` or a debug JSON field |
| `decay_impact` | Mean salience drop and fraction flagged `needs_review` | Returned by `decay_unused` stats dict (`decayed`, `flagged_review`) |
| `schema_confidence_distribution` | Histogram of LatentSchema confidence values | Add a list to consolidation debug output or `ConsolidationStats` |
| `corpus_size_for_tfidf` | Number of schemas in the background corpus for contrastive TF-IDF | Log at start of `_consolidate_latent` — already tracked as `_global_corpus` length |

## Parameter Sensitivity

| Parameter | Direction | Effect | Sweep Range |
|-----------|-----------|--------|-------------|
| `same_topic_cosine` | ↑ | Fewer schemas reach the geometric judge → more "unrelated" verdicts, fewer contradictions detected | 0.60, 0.70, 0.75, 0.80, 0.85 |
| `reinforce_cosine` | ↑ | Wider "reinforces" band → fewer schemas proceed to facet-axis comparison | 0.90, 0.92, 0.95, 0.97 |
| `contradicts_facet_dist` | ↑ | Fewer contradictions, more "refines" verdicts | 0.20, 0.30, 0.35, 0.40, 0.50 |
| `min_support_to_supersede` | ↑ | More conservative — only well-backed schemas can supersede | 1, 2, 3, 5 |
| `min_time_delta_to_supersede_s` | ↑ | More conservative recency gate → toggling contradictions become reinforcement | 300, 1800, 3600, 7200, 86400 |
| `variance_floor` | ↑ | Higher confidence for loose clusters → more schemas appear "confident" when they shouldn't | 10⁻³, 5×10⁻³, 10⁻², 5×10⁻², 10⁻¹ |
| `n_facet_axes` | ↑ | More detail in geometric judge comparison, but noise in higher SVD components | 2, 4, 6, 8 |
| Near-duplicate guard (0.92) | ↑ | Fewer duplicates bypassed → more schemas created for concepts that are semantically close but not identical | 0.88, 0.90, 0.92, 0.94, 0.96 |
| Related-schema threshold (0.72) | ↑ | Fewer schemas reach geometric judge → more "created" without relation edges | 0.65, 0.70, 0.72, 0.75, 0.80 |

## Known Failure Modes

| Symptom | Likely Cause | Diagnostic Signal |
|---------|-------------|-------------------|
| Every consolidation pass creates schemas, never reinforces | Near-duplicate guard too low OR `variance_floor` too high (all schemas have high confidence → centroids diverge) | `near_dup_reinforced` ≈ 0, `schemas_reinforced` ≈ 0 |
| No contradictions ever detected (**confirmed root cause, not hypothetical**: 0/26,250 in 2026-07-09 B1+B2 runs) | `_write_latent_schema` reconstructs the old schema's facet axes as always-empty (`np.zeros((0, dim))`) since they are never persisted retrievably — `contradicts_facet_dist` is structurally unreachable regardless of threshold value. NOT a `same_topic_cosine`/`contradicts_facet_dist` calibration issue — sweeping either will not fix this. | `verdict_counts["contradicts"]` == 0 while `verdict_counts["refines"]` is nonzero; `test_contradicts_verdict_unreachable.py` proves it directly |
| Too many false contradictions | `same_topic_cosine` too high AND `contradicts_facet_dist` too low → noise in facet axes triggers spurious contradictions | `contradiction_rate` > 20%, schemas toggling between active/superseded |
| Explicit-remember schemas duplicated by consolidation | `_episodes_all_explicit_remember` gate broken → episodes from remember-only sessions are re-consolidated into near-duplicate schemas | Same content text appears across multiple schema IDs from consolidation |
| Loose clusters get confidence = 0.0 → no schema created | `variance_floor` too low → tight calibration breaks for real noisy clusters | `schemas_skipped` high despite non-empty prototypes |
| Decay deletes everything | `idle_days` too short OR `decay_amount` too large → all unreinforced schemas decay below review threshold in one pass | All active schemas flagged `needs_review` after one consolidate_once |
| Cross-scope relations never form | `scope_id` is NULL for all episodes → `scope_for_episodes` returns None, no cross-scope reinforcement | `cross_scope_reinforcement_count` always 0 |

## Relationship to Other Modules

| Module | Relationship |
|--------|-------------|
| `03-replay.md` | Upstream producer — `ReplayEngine.replay_once()` runs before consolidation, providing updated centroids and graph edges |
| `04-graph.md` | Indirect — prototype creation (which determines what gets consolidated) is driven by replay; `_link_schemas_via_prototype_centroid()` reads `semantic.get(pid)` to find existing schemas |
| `06-retrieval.md` | Downstream consumer — consolidated schemas are the primary recall candidates; schema status (active/superseded/contradicted) gates retrieval eligibility |
| `08-feedback.md` | Feedback reinforces schemas via `reinforce_schema()` and `increment_cross_scope_reinforcement()` — increases salience and recurrence_count, which protects against decay |
| `09-context.md` | Decay feeds into WorkingMemoryGate — schemas flagged `needs_review` are excluded from default context; generalization stage promotion uses `cross_scope_reinforcement_count` |
| `10-supersession.md` | The geometric judge replaces the old SVD1-direction-based supersession manifold for the consolidation path (the manifold still applies at `remember()` time) |
| `11-vsa.md` | VSA vectors are built and stored during consolidation (`build_schema_vsa`) but not currently used in retrieval — deferred |
