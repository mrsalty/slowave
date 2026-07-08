# 09 — Working Memory Gating (Context)

## Overview

The working memory gate is the bottleneck between long-term memory retrieval and prompt context insertion. It scores activated schemas on query relevance, scope match, class/layer bonuses, and noise penalties, then applies MMR deduplication and a token budget.

## Mathematical Formulation

### Step 1: Schema Scoring

For each schema \( s \) with embedding \( \mathbf{e}_s \) and cue \( c \):

\[
\text{score}(s, c) = \underbrace{\cos(\mathbf{e}_q, \mathbf{e}_s)}_{\text{cosine}} + \underbrace{B_{\text{identity}}(s, c)}_{\text{identity bonus}} - \underbrace{P_{\text{noise}}(s)}_{\text{noise penalty}}
\]

**Identity bonus** \( B_{\text{identity}} \) is the sum of:

| Bonus | Value | Condition |
|-------|-------|-----------|
| `class_bonus` | `+0.05` | Schema type is in `allowed_classes` |
| `layer_bonus` | `+0.03` | Memory layer is in `allowed_memory_layers` |
| `provenance_bonus` | `+0.05` | Source kind is `"explicit_remember"` |
| `scope_bonus` | `+0.08` | Schema scope matches cue scope exactly |
| `scope_kind_bonus` | `+0.04` | Schema scope kind matches cue scope kind |
| `salience_bonus` | `+0.02` | Schema salience ≥ median |
| `utility_bonus` | `+0.03` | Schema utility score ≥ median |

**Identity bonus cap**: \( B_{\text{identity}} \leq 0.15 \) (prevents query-invariant ranking).

**Noise penalty** \( P_{\text{noise}} \):

\[
P_{\text{noise}} = w_n \cdot \text{noise\_score}(s)
\]

Where:
- \( w_n = 0.30 \) (`_NOISE_PENALTY_WEIGHT`)
- `noise_score(s)` is derived from `shown_count`, `used_count`, `irrelevant_count` feedback history

### Step 2: Keyword Scoring (Fallback)

For schemas without embeddings, a simple keyword overlap score is used:

\[
\text{score}_{\text{kw}}(s, c) = \frac{|\text{terms}(c) \cap \text{terms}(s)|}{\max(|\text{terms}(c)|, 1)}
\]

### Step 3: Activation Ranking

Schemas are ranked by descending score. The "rendered" boolean controls whether peripheral schemas are included.

### Step 4: MMR Deduplication

Near-duplicates are removed from the ranked list:

\[
\text{keep } s_i \text{ iff } \forall j < i: \cos(\mathbf{e}_{s_i}, \mathbf{e}_{s_j}) < \theta_{\text{mmr}}
\]

Where \( \theta_{\text{mmr}} = 0.92 \) — schemas with cosine ≥ 0.92 are considered duplicates. Schemas without embeddings are always kept.

### Step 5: Budget Trimming

Two constraints are applied:

1. **Item limit**: at most `max_items` schemas
2. **Character limit**: total rendered text length ≤ `max_chars`

Items are included in rank order until either limit is exceeded.

### Step 6: Rendering

Each selected schema is rendered as:

```
- [sch_{id}] (peripheral) {content_text}
```

The `(peripheral)` marker indicates schemas with class/layer outside the explicit `allowed` sets.

## Configuration

### `GatePolicy`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_items` | `int` | `10` | Maximum number of schemas in context |
| `max_chars` | `int` | `4000` | Maximum total rendered characters |
| `allowed_classes` | `tuple[str]` | `_DEFAULT_ALLOWED_CLASSES` | Schema types eligible for identity bonus |

### `_DEFAULT_ALLOWED_CLASSES`

`("fact", "preference", "interaction_preference", "constraint", "habit", "decision", "lesson", "relationship", "artifact", "task", "open_question", "warning", "procedure")`

### Excluded Layers

`("raw_event", "episodic_summary", "assistant_summary")` — these never receive the layer identity bonus.

### Excluded Sources

`("assistant_summary", "tool_result_summary")` — these never receive the provenance identity bonus.

### Internal Constants

| Constant | Symbol | Value | Description |
|----------|--------|-------|-------------|
| Identity bonus cap | — | `0.15` | Max query-independent score boost |
| Noise penalty weight | \( w_n \) | `0.30` | Multiplier for context noise score |
| MMR cosine threshold | \( \theta_{\text{mmr}} \) | `0.92` | Near-duplicate detection threshold |

## Key Invariants

1. Identity bonuses are capped at 0.15 — what a memory IS must only tie-break, never outrank how well it matches the query.
2. Schemas without embeddings fall back to keyword scoring — the system degrades gracefully when the encoder is unavailable.
3. MMR deduplication prevents two near-identical schemas from both occupying token budget.
4. Noise penalty (`_NOISE_PENALTY_WEIGHT = 0.30`) is the primary mechanism for cleaning ranking — it can reduce activation by up to 0.30 compared to salience deltas of ~0.0004.