# 05 — Consolidation (Prototypes → Schemas)

## Overview

Consolidation lifts replayed latent prototypes into first-class symbolic schemas stored in SQLite with FTS indexing. Two paths exist: the **brain-only latent path** (zero LLM calls) and a legacy text path. The latent path is the production default.

## Latent Consolidation Pipeline

### Step 1: Prototype Selection

Prototypes are selected if they have accumulated enough support (member episodes) and haven't been consolidated recently.

### Step 2: Latent Schema Building

For each selected prototype \( p \) with centroid \( \mathbf{c} \) and member episodes \( \{e_1, \ldots, e_m\} \):

**Content text** is derived from the prototype's lexical signature and member episode texts — no LLM involved.

**Embedding**: the prototype centroid \( \mathbf{c} \) becomes the schema's embedding.

**Facets** extracted from episode metadata:
- `memory_layer`: inferred from schema type (profile / domain / workspace)
- `source_kind`: `"consolidation"` or `"explicit_remember"`
- `entity_count`, `episode_count`: from prototype support

### Step 3: Schema Classification

Consolidated schemas are classified by structure:

```
if source_kind == "explicit_remember" → no reclassification
elif sentence_count >= 3 or len(text) > 300 → "episodic_summary"
else → "fact"
```

### Step 4: Supersession & Contradiction Check

For each new schema claim, check against existing active schemas:

**Cosine similarity check:**

\[
\cos_{\text{new,old}} = \langle \mathbf{e}_{\text{new}}, \mathbf{e}_{\text{old}} \rangle
\]

Thresholds from `supersession_manifold.py`:

| Condition | Action |
|-----------|--------|
| Same scope, \( \cos \geq 0.85 \) | Flag for review (potential supersession) |
| Same scope, \( \cos \in [0.70, 0.85) \) | Check direction score |
| Same scope, direction ≥ `DIRECTION_THRESHOLD` | Supersede old schema |
| Cross-scope, \( \cos \geq 0.78 \) | Reinforce + record cross-scope evidence |
| \( \cos \geq 0.35 \) | Mark as topically related |

**Direction score** (see §10 — Supersession Manifold):

\[
\text{dir} = \langle \hat{\mathbf{d}}, \mathbf{v}_{\text{SVD1}} \rangle, \quad \mathbf{d} = \mathbf{e}_{\text{new}} - \mathbf{e}_{\text{old}}
\]

### Step 5: Schema Storage

New schemas are inserted into the `schemas` table with:
- `content_text`: canonicalized text
- `embedding`: float32 L2-normalized vector
- `facets_json`: JSON metadata dictionary
- `status`: `"active"`, `"needs_review"`, or `"superseded"`
- `created_at`, `last_updated_at`: timestamps
- FTS5 index updated automatically via triggers

### Step 6: Schema-Protype Mapping

A row is inserted into `schema_prototype_map` linking the new schema to its source prototype, enabling bidirectional navigation between latent and symbolic layers.

## Schema Decay

Active schemas that have never been recalled can be decayed:

\[
s_{\text{schema}} \leftarrow s_{\text{schema}} \cdot \gamma_{\text{decay}}, \quad \gamma_{\text{decay}} \in (0, 1]
\]

Triggered by `decay_schemas(idle_days=30.0)` — the schema store's `decay_unused` method applies a salience penalty to schemas with zero recall count and `last_recalled_at` older than `idle_days`.

## Configuration

### Consolidator Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_episodes_per_prototype` | `int` | `8` | Max member episodes used for text extraction |

### Supersession Thresholds (Global Constants)

| Constant | Value | Description |
|----------|-------|-------------|
| `SAME_SCOPE_COS_THRESHOLD` | `0.85` | Cosine threshold for same-scope action |
| `EXTENDED_SAME_SCOPE_COS_THRESHOLD` | `0.70` | Lower bound for same-scope direction check |
| `CROSS_SCOPE_COS_THRESHOLD` | `0.78` | Cosine threshold for cross-scope linking |
| `DIRECTION_THRESHOLD` | `0.10` | Minimum direction score for supersession |
| `DIR_REVIEW_BAND` | `(-0.05, 0.05)` | Direction range triggering needs_review |
| `TOPICAL_THRESHOLD` | `0.35` | Minimum similarity for topical relationship |

## Key Invariants

1. Zero LLM calls in the consolidation path — schemas are built from prototype geometry and lexical signatures.
2. Explicit memories (`source_kind = "explicit_remember"`) are never reclassified.
3. Cross-scope schemas are never superseded — only reinforced with cross-scope evidence.
4. Schemas with `status = "superseded"` are excluded from context/recall by default.