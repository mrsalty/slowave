# 09 — Working Memory Gating (Context)

## Overview

The working memory gate (`WorkingMemoryGate`) is the bottleneck between long-term memory retrieval and prompt context insertion. It scores candidate schemas against the current cognitive cue (`MemoryCue`) through three additive components — geometric similarity (cosine), lexical overlap (keyword), and a capped identity prior (what the memory IS) — then applies eligibility filters, cross-scope noise-floor gates, MMR deduplication, and a token budget. Exploration slots inject a bounded serendipity channel: low-salience unrelated memories keep circulating without displacing relevant ones. The rendered output is a compact text brief, with suppressed counts and activation traces available for diagnostics.

## Data Flow

```
eng.context_brief(query, scope, ...)                    eng.activate(query, scope, ...)
        │                                                        │
        ▼                                                        ▼
RetrievalService.context_brief()                        SlowaveEngine.activate()
  ┌─ Normalize scope                                        ┌─ RetrievalPipeline
  ├─ Fetch candidates:                                        │  (FAISS + graph + temporal)
  │   · scope-matched (active ± needs_review ± superseded)     │
  │   · promoted (generalization_stage ≥ 2)                   ▼
  │   · global pool (all active)                      candidate schemas
  └─ Encode cue → embedding (if encoder available)              │
        │                                                       │
        ▼                                                       ▼
WorkingMemoryGate.select(candidates, cue, policy, cue_embedding)
  │
  ├─ Per-schema loop:
  │   1. _eligible(schema, cue, policy)   ── mode-gated status, class/layer/source
  │   2. _activation(schema, cue, ...)    ── cosine + lexical + identity + scope ± penalties
  │   3. cross-scope noise floor          ── stage 1/2: activation≥0.30 AND cosine≥0.25
  │   4. min_activation check             ── admission threshold
  │
  ├─ Sort by (activation, salience, last_updated_ts) DESC
  ├─ MMR deduplicate (cos_threshold=0.92)
  ├─ Budget trim (max_items, max_chars) + exploration slots
  └─ Render compact text brief
        │
        ▼
WorkingMemoryState
  ├─ .items          — admitted WorkingMemoryItems
  ├─ .rendered       — "- [sch_N] (peripheral) text…"  brief
  ├─ .schemas        — underlying Schema objects
  ├─ .suppressed     — {"class_excluded:latent": 3, "inactive": 1, …}
  └─ .activation_trace — per-schema ActivationTrace records
```

## Mathematical Formulation

### Phase 1: Eligibility Gating

Before scoring, a schema must pass a series of hard filters:

1. **Mode-gated status**: `default` — only `active`; `broad` — `active` + `needs_review`; `debug` — all statuses including `superseded`. (Debug mode short-circuits all further eligibility checks.)

2. **Strict scope with generalization override** (cue.mode ≠ `broad`):
   - Stage 0 (scoped): schema.scope_id must match cue.scope exactly
   - Stage 1 (portable): same `scope_kind` as origin allowed
   - Stage 2 (contextual) / Stage 3 (global): bypass the scope wall
   - In `broad` mode, no scope wall at all — any scope passes

3. **Class exclusion**: If `allowed_classes` is non-empty, `schema_class` must be in it.

4. **Layer exclusion**: Memory layers in `excluded_layers` (`raw_event`, `episodic_summary`, `assistant_summary`) are suppressed unless `source_kind == "explicit_remember"`.

5. **Source kind exclusion**: `source_kind` in `excluded_source_kinds` (`assistant_summary`, `tool_result_summary`) suppressed unless in broad/debug mode.

6. **Transcript summary detection**: Schemas matching `"User:" AND "Assistant:"` in content text are suppressed (unless broad/debug or `injectable=True`).

7. **Multi-sentence summary gate**: Schemas with ≥3 sentences or >300 chars that are NOT `episodic_summary` class and NOT `explicit_remember` source are suppressed in default mode (belt-and-suspenders for untagged legacy consolidated schemas).

### Phase 2: Activation Scoring

For each eligible schema \\( s \\) with cue \\( c \\), embedding \\( \\mathbf{e}_s \\), and cue embedding \\( \\mathbf{e}_q \\):

\\[
\\text{activation} = \\underbrace{0.40 \\cdot \\max(0, \\cos(\\mathbf{e}_q, \\mathbf{e}_s))}_{\\text{geometric}} + \\underbrace{w_{\\text{lex}} \\cdot \\text{overlap}(c, s)}_{\\text{lexical}} + \\underbrace{\\min(0.15, B_{\\text{identity}}(s))}_{\\text{capped identity prior}} + \\underbrace{B_{\\text{scope}}(s, c)}_{\\text{scope (uncapped)}} - \\underbrace{P(s)}_{\\text{penalties}}
\\]

Where:
- \\( w_{\\text{lex}} = 0.15 \\) when both embeddings present, \\( 0.40 \\) as fallback when embeddings absent
- \\( \\text{overlap}(c, s) = \\frac{|\\text{terms}(c) \\cap \\text{terms}(s)|}{\\max(|\\text{terms}(c)|, 1)} \\)

**Logical concept**: Cosine is the primary signal (40% weight). Lexical overlap is a complement at reduced weight (15%) when embeddings are available, or the full 40% fallback when they aren't — the system degrades gracefully without an encoder.

#### Identity Prior \\( B_{\\text{identity}} \\)

The identity prior is query-independent: it encodes what a memory IS, not how well it matches this query. It is capped at 0.15 so identity only tie-breaks, never outranks relevance.

| Component | Value | Condition |
|-----------|-------|-----------|
| Salience | \\( 0.15 \\cdot \\min(1.0, \\text{salience} / 20.0) \\) | Always |
| Schema class (tier 1) | \\( +0.12 \\) | `preference`, `interaction_preference`, `constraint` |
| Schema class (tier 2) | \\( +0.07 \\) | `decision`, `lesson`, `habit`, `fact`, `procedure`, `warning` |
| Stability | \\( +0.08 \\) | `stability` ∈ {`current`, `recurring`} |
| Utility | \\( \\min(0.12, \\text{schema\\_utility} \\cdot 0.15) \\) | `schema_utility > 0` |
| Memory layer (tier 1) | \\( +0.12 \\) | `profile` |
| Memory layer (tier 2) | \\( +0.06 \\) | `domain`, `workspace` |
| Source kind | \\( +0.12 \\) | `explicit_remember` |

**Logical concept**: The cap ensures a same-scope explicit-remember preference with max salience and profile layer can contribute at most 0.15 from identity — less than a moderate cosine match (0.40 × 0.5 = 0.20). Relevance always dominates.

#### Scope Bonus \\( B_{\\text{scope}} \\)

Applied AFTER the identity cap so scope-matched and global schemas are never starved below `min_activation`:

| Condition | Bonus |
|-----------|-------|
| `cue.scope` matches `schema.scope_id` exactly | \\( +0.20 \\) |
| Schema has no `scope_id` (global) | \\( +0.15 \\) |

#### Scope Mismatch Penalty (Generalization-Stage Graded)

When `cue.scope` and `schema.scope_id` are both present but differ:

| Generalization Stage | Penalty |
|---------------------|---------|
| Stage 3 (global) | 0 (no penalty — earned unrestricted access) |
| Stage 2 (contextual) | \\( -0.12 \\) (reduced penalty) |
| Stage 0/1 (scoped/portable) | \\( -0.35 \\) (full penalty) |

#### Additional Penalties \\( P(s) \\)

\\[
P(s) = \\begin{cases}
0.30 & \\text{if } \\text{source\\_kind} \\in \\{\\text{assistant\\_summary}, \\text{tool\\_result\\_summary}\\} \\\\
0.12 & \\text{if } |\\text{content\\_text}| > 500 \\text{ (verbose inhibition)} \\\\
0.15 & \\text{if } \\text{content\\_text contains } \\text{\"Assistant:\"} \\\\
0.30 \\cdot \\text{context\\_noise\\_score} & \\text{if } \\text{context\\_noise\\_score} > 0 \\\\
0 & \\text{otherwise}
\\end{cases}
\\]

Where `context_noise_score` is maintained at consolidation time from `shown_count`, `used_count`, `irrelevant_count` feedback history (see `08-feedback.md`). All four penalties are additive.

### Phase 3: Cross-Scope Noise Floor

For schemas whose `scope_id` differs from `cue.scope` and whose `generalization_stage` is 1 or 2:

\\[
\\text{admit if } \\begin{cases}
\\text{activation} \\geq 0.30 & \\text{(Gate A: activation floor)} \\\\
\\cos(\\mathbf{e}_q, \\mathbf{e}_s) \\geq 0.25 & \\text{(Gate B: cosine floor, when embeddings available)}
\\end{cases}
\\]

Stage 3 (global) schemas are exempt from both gates. The cosine gate (B) ensures surface-word overlap alone cannot admit an unrelated promoted memory.

**Logical concept**: Two independent gates prevent cross-scope noise — a promoted schema must be both relevant enough overall AND geometrically related to the query. The activation floor was raised from 0.20 to 0.30 to exclude generic memories scoring on salience/utility boosts alone with no real semantic match.

### Phase 4: Sorting & MMR Deduplication

Items are sorted by \\( (\\text{activation}, \\text{salience}, \\text{last\\_updated\\_ts}) \\) descending.

MMR deduplication removes near-duplicates in activation order:

\\[
\\text{keep } s_i \\text{ iff } \\forall j < i: \\cos(\\mathbf{e}_{s_i}, \\mathbf{e}_{s_j}) < \\theta_{\\text{mmr}}
\\]

Where \\( \\theta_{\\text{mmr}} = 0.92 \\). Schemas without embeddings are always kept.

### Phase 5: Budget Trimming & Exploration Slots

When admitted items ≤ `max_items`, all are selected (up to `max_chars`). When admitted items > `max_items`:

1. The top `min(max_items * 3, max_items)` by activation are passed to `_apply_budget()`, which fills up to `max_items` slots (subject to `max_chars`)
2. The remaining `exploration_slots` positions are filled from the leftover pool, ranked by salience (not activation), and labeled `(peripheral)` in the rendered brief

This is a bounded serendipity channel: low-salience memories keep circulating without ever displacing a relevant one from the top.

### Phase 6: Rendering

Each selected item is rendered as:

```
- [sch_{id}] (peripheral) {compact_text}
```

`compact_text` is the schema's `content_text` whitespace-collapsed to a single line, truncated to `max_item_chars`, with `…` appended if cut.

The `(peripheral)` marker indicates items admitted via exploration slots rather than relevance ranking.

## Configuration

### `GatePolicy`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_items` \\( M \\) | `int` | `8` | Maximum schemas in context brief (relevance-ranked) |
| `max_chars` \\( C \\) | `int` | `4000` | Maximum total rendered characters |
| `max_item_chars` \\( L \\) | `int` | `500` | Maximum rendered characters per schema (content is compacted) |
| `min_activation` \\( \\alpha_{\\min} \\) | `float` | `0.20` | Activation floor — schemas below this are suppressed |
| `exploration_slots` \\( E \\) | `int` | `2` | Trailing salience-ranked slots when admitted > max_items |
| `allowed_classes` | `tuple[str, ...]` | `_DEFAULT_ALLOWED_CLASSES` | Schema types eligible; non-empty = exclusive filter |
| `excluded_layers` | `tuple[str, ...]` | `_DEFAULT_EXCLUDED_LAYERS` | Memory layers never admitted (unless `explicit_remember`) |
| `excluded_source_kinds` | `tuple[str, ...]` | `_DEFAULT_EXCLUDED_SOURCES` | Source kinds never admitted (unless broad/debug) |

### `MemoryCue`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str \| None` | `None` | Natural-language query text |
| `scope` | `str \| None` | `None` | Scope identifier (e.g. `"project:slowave"`) |
| `goal` | `str \| None` | `None` | Short goal phrase |
| `task_type` | `str \| None` | `None` | Task category |
| `situation` | `dict[str, Any]` | `{}` | Arbitrary situational key-value pairs |
| `requirements` | `tuple[str, ...]` | `()` | Requirement strings |
| `application` | `str \| None` | `None` | Application name |
| `topics` | `tuple[str, ...]` | `()` | Topic tags |
| `entities` | `tuple[str, ...]` | `()` | Entity references |
| `mode` | `str` | `"default"` | Retrieval mode: `default`, `broad`, or `debug` |

### `WorkingMemoryState`

| Field | Type | Description |
|-------|------|-------------|
| `items` | `list[WorkingMemoryItem]` | Admitted items (including peripheral) |
| `rendered` | `str` | Compact text brief for prompt injection |
| `cue_terms` | `list[str]` | Extracted cue terms (for diagnostics) |
| `suppressed` | `dict[str, int]` | Counts per suppression reason (e.g. `"inactive"`, `"class_excluded:latent"`) |
| `activation_trace` | `list[ActivationTrace]` | Per-candidate trace: `(schema_id, activation, reason, admitted)` |

### Internal Constants

| Constant | Symbol | Value | Description |
|----------|--------|-------|-------------|
| Identity bonus cap | — | `0.15` | Max query-independent score boost |
| Noise penalty weight | \\( w_n \\) | `0.30` | Multiplier for `context_noise_score` |
| MMR cosine threshold | \\( \\theta_{\\text{mmr}} \\) | `0.92` | Near-duplicate detection threshold |
| Cosine weight | — | `0.40` | Geometric similarity contribution |
| Lexical weight (embeddings present) | \\( w_{\\text{lex}} \\) | `0.15` | Lexical overlap when embeddings active |
| Lexical weight (fallback) | \\( w_{\\text{lex}} \\) | `0.40` | Lexical overlap when embeddings absent |
| Cross-scope activation floor | — | `0.30` | Min activation for stage 1/2 cross-scope schemas |
| Cross-scope cosine floor | — | `0.25` | Min cosine for stage 1/2 cross-scope schemas |

### Default Sets

**`_DEFAULT_ALLOWED_CLASSES`**: `("fact", "preference", "interaction_preference", "constraint", "habit", "decision", "lesson", "relationship", "artifact", "task", "open_question", "warning", "procedure")`

**`_DEFAULT_EXCLUDED_LAYERS`**: `("raw_event", "episodic_summary", "assistant_summary")` — these never pass eligibility unless `source_kind == "explicit_remember"`.

**`_DEFAULT_EXCLUDED_SOURCES`**: `("assistant_summary", "tool_result_summary")` — these never pass eligibility unless mode is `broad` or `debug`.

## Key Invariants

1. **Identity prior is capped at 0.15** — what a memory IS must only tie-break, never outrank how well it matches the current query. Uncapped, same-scope explicit schemas sum to ~0.58 vs a 0.40 max cosine contribution.
2. **Scope bonus is applied AFTER the identity cap** — scope-matched and global schemas are never starved below `min_activation` by the identity ceiling.
3. **Scope mismatch penalty is generalization-stage graded** — Stage 3 (global) pays 0, Stage 2 (contextual) pays -0.12, Stage 0/1 pay -0.35. The penalty is not one-size-fits-all.
4. **Cross-scope Stage 1/2 schemas must pass two independent gates** — activation ≥ 0.30 AND cosine ≥ 0.25. Surface-word overlap alone cannot admit an unrelated promoted memory.
5. **MMR deduplication prevents two near-identical schemas** (cosine ≥ 0.92) from both occupying token budget. Always preserves the higher-activation one.
6. **Exploration slots do not displace relevance-ranked items** — they fill only when admitted > max_items, and are ranked by salience, not activation.
7. **`assistant_summary` and `tool_result_summary` source kinds incur a -0.30 penalty** in activation scoring in addition to being excluded at eligibility (belt-and-suspenders).
8. **Mode controls both eligibility AND candidate fetching** — `default` fetches only `active`; `broad` adds `needs_review`; `debug` adds `superseded`. The `_eligible()` gate mirrors these rules.
9. **Multi-sentence summaries (≥3 sentences or >300 chars) are suppressed** in default mode unless tagged `episodic_summary` class or `explicit_remember` source — a belt-and-suspenders for untagged legacy schemas.
10. **Noise penalty (`_NOISE_PENALTY_WEIGHT = 0.30`)** is the primary cleanliness mechanism — it can reduce activation by up to 0.30, while salience deltas alone move activation by ~0.0004.
11. **`source_kind == "explicit_remember"` overrides the multi-sentence summary gate** — explicitly remembered schemas bypass the ≥3-sentence/>300-char filter. It also adds a +0.12 identity bonus in activation scoring, but does NOT override layer exclusion at eligibility level.
12. **Debug mode (`mode == "debug"`) bypasses ALL eligibility filters** — every schema is eligible.
13. **The `suppressed` dict and `activation_trace` list are always populated** — even when no items are suppressed, for diagnostic transparency.

## Implementation Files

| File | What It Implements |
|------|-------------------|
| `slowave/core/context.py` | `WorkingMemoryGate`, `MemoryCue`, `GatePolicy`, `WorkingMemoryState`, `WorkingMemoryItem`, `ActivationTrace`, all scoring/eligibility/dedup/budget helpers |
| `slowave/core/services/retrieval.py` | `RetrievalService.context_brief()` — candidate fetching, scope normalization, cue embedding encoding, delegation to `WorkingMemoryGate` |
| `slowave/core/engine.py` | `SlowaveEngine.context_brief()` — public API delegation |
| `slowave/ops.py` | `context_brief()` — MCP-friendly wrapper |
| `slowave/symbolic/schema_store.py` | `Schema` — the candidate object; `generalization_stage`, `scope_id`, `facets` fields read by the gate |
| `slowave/core/feedback.py` | `FeedbackService` — maintains `context_noise_score` consumed by the noise penalty |

## Diagnostic Hooks

| Metric | What It Measures | How to Instrument |
|--------|-----------------|-------------------|
| `suppressed` dict | Per-reason suppression counts — reveals which eligibility filter is most aggressive | Already in `WorkingMemoryState.suppressed`; log it after each `context_brief()` call |
| `activation_trace` | Per-schema activation breakdown (admitted + rejected) — reveals whether cosine, lexical, or identity dominates | Already in `WorkingMemoryState.activation_trace`; requires `mode="debug"` for full candidate set |
| `cross_scope_below_floor` count | How many promoted (stage 1/2) schemas fail the noise-floor gates | Key in `suppressed["cross_scope_below_floor"]` |
| `cross_scope_low_cosine` count | How many promoted schemas pass the activation floor but fail the cosine gate | Key in `suppressed["cross_scope_low_cosine"]` |
| Exploration slot utilization | Are peripheral items actually appearing, or is `exploration_slots` dead weight? | Count `(peripheral)` items in `rendered` or `item.peripheral` in `items` |
| `below_activation` count | How many eligible schemas fall below `min_activation` | Key in `suppressed["below_activation"]` |
| Per-item activation reasons | What components contributed to each item's score | `WorkingMemoryItem.reason` (e.g. `"cosine=0.73,cue_overlap=0.25,salience=0.25,preference,stability=current,profile,scope_match=project:slowave"`) |
| `noise` in reasons | How often the noise penalty is actively reducing activation | Grep `reason` for `noise=` substring |
| MMR suppressed count | How many near-duplicates are removed | Compute `len(items_before_mmr) - len(items_after_mmr)` |

## Parameter Sensitivity

| Parameter | Direction | Effect | Sweep Range |
|-----------|-----------|--------|-------------|
| `min_activation` | ↑ | Fewer schemas admitted; tighter relevance requirement | 0.10–0.40 |
| `exploration_slots` | ↑ | More serendipity, more token budget consumed by unrelated items | 0–4 |
| `max_items` | ↑ | More context, higher token cost, risk of dilution | 4–16 |
| `max_chars` | ↑ | Longer briefs, potential for prompt overflow | 1000–8000 |
| `max_item_chars` | ↑ | More detail per schema, less compact briefs | 200–1000 |
| `_IDENTITY_BONUS_CAP` | ↑ | Identity (what a memory IS) gains weight vs relevance — risk of query-invariant ranking | 0.05–0.30 |
| `_NOISE_PENALTY_WEIGHT` | ↑ | Noisy schemas pushed further down; stronger feedback-loop cleaning | 0.10–0.50 |
| Cross-scope activation floor (0.30) | ↑ | Fewer promoted cross-scope schemas admitted | 0.20–0.50 |
| Cross-scope cosine floor (0.25) | ↑ | Stricter geometric requirement for promoted schemas | 0.10–0.40 |

## Known Failure Modes

| Symptom | Likely Cause | Diagnostic Signal |
|---------|-------------|-------------------|
| Context brief is nearly query-invariant (same items every query) | Identity prior dominating — class/layer/salience bonuses summing near cap | `activation_trace` reasons show mostly class/layer/scope, little cosine contribution |
| Good promoted (Stage 2/3) schemas never appear in cross-scope queries | Cross-scope noise floor too aggressive — activation floor (0.30) or cosine floor (0.25) blocking legitimate matches | `cross_scope_below_floor` or `cross_scope_low_cosine` counts are high for schemas you expect to see |
| Irrelevant promoted schemas leak into cross-scope context | Cosine floor (0.25) too low — surface-word overlap sneaking through | `cross_scope_low_cosine` count is zero but irrelevant promoted schemas appear in brief |
| Exploration slots always empty | `exploration_slots` set but admitted ≤ max_items, so no leftover pool | Check `len(items)` vs `max_items` before exploration slot allocation |
| `excluded_layers` not suppressing as expected | Schema has `source_kind == "explicit_remember"` — that overrides layer exclusion (Invariant 11) | Check schema's `facets["source_kind"]` |
| Multi-sentence consolidated schemas leaking into default context | Schema tagged `episodic_summary` class or `explicit_remember` source — those bypass the multi-sentence gate | Check schema's `facets["schema_class"]` and `facets["source_kind"]` |
| Noise penalty has no effect | `context_noise_score` is 0 or near-zero — feedback loop hasn't accumulated enough negative signal | Check schema's `facets["context_noise_score"]` |

## Relationship to Other Modules

| Module | Relationship |
|--------|-------------|
| `08-feedback.md` | Upstream producer of `context_noise_score` (computed there from shown/used/irrelevant counts, consumed here via `_NOISE_PENALTY_WEIGHT`). Also produces `status`/`needs_review` for mode-gated eligibility. |
| `06-retrieval.md` | Upstream producer of candidate schemas via FAISS + graph + temporal retrieval. The gate scores and filters what retrieval activates. |
| `05-consolidation.md` | Upstream producer of schemas; `generalization_stage` (computed at consolidation time) drives cross-scope penalty grading and noise-floor gating. |
| `02-salience.md` | Salience (decayed/reinforced there) feeds the identity prior through `0.15 * min(1.0, salience/20.0)` — a distinct write path from feedback-driven salience changes. |
| `04-graph.md` | Graph edges can promote schemas to higher generalization stages, which changes their cross-scope treatment in the gate. |
| MCP surface (`slowave/mcp/tools.py`) | `slowave_activate` → `context_brief()` is called to build the rendered context brief for prompt injection. The gate is exercised on every activation. |
| `slowave/ops.py` | `context_brief()` wrapper used by `slowave_activate`/`slowave_recall` — the gate is the final step before returning context to the agent. |
