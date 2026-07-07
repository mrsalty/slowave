# Brain-Inspired Gaps: Analysis, Resolution Plan & Measurement

**Date:** 2026-06-24  
**Status:** Refined after external review (GPT-5.5, 2026-06-24) — proposals updated, new gap added  
**Context:** Emerged from end-to-end audit of the generalization/promotion pipeline after implementing the geometry-only supersession refactor (see `20260624_geometry_only_supersession.md`) and the cross-scope generalization fixes.

---

## External review summary (GPT-5.5)

> "Slowave has largely moved beyond 'vector memory' design questions and is now dealing with second-order learning dynamics. Most of the remaining issues are no longer retrieval problems; they're questions about how schemas form, consolidate, generalize, and update over time. That is a good sign architecturally."

**Tier 1 — genuine architectural flaws (fix):** Gap 4 (pollution), Gap 3 (judge bypass)  
**Tier 2 — good ideas, need empirical validation:** Gap 1 (semantic diversity), Gap 2 (bootstrap deadlock)  
**Tier 3 — optimization:** Gap 5 (inhibition)  
**New gap identified:** Schema abstraction quality — Slowave promotes but does not abstract

---

## What works well (do not break)

Before the gaps: three mechanisms are genuinely brain-faithful and should be preserved as-is.

- **Replay + offline consolidation** — decouples ingest from schema formation, mirrors hippocampal replay during sleep. `ReplayEngine` → `Consolidator` pipeline is architecturally correct.
- **Prototype clustering** — `SemanticStore` centroid + facet-axes representation mirrors neocortical schema formation from episodic statistics. Zero LLM. Correct.
- **Temporal spread gate** — `stage1_min_distinct_sessions >= 2` (and higher for later stages) mirrors the neuroscience finding that hippocampus→neocortex transfer requires reactivation across separate sleep/waking cycles, not just within-session repetition. This constraint is one of the most faithful details in the system.

---

## Gap 1 — Scope-based ≠ context-based generalization

### Problem
Stage promotion is driven by `distinct_scope_count` (how many named scopes recalled a schema). This is a **structural proxy** for contextual diversity, not actual semantic diversity. A schema recalled from 8 coding-project scopes (all semantically similar) reaches Global. A schema recalled from 3 radically different domains (coding, medical, legal) reaches only stage 1 — even though the latter is genuinely more generalised.

The brain promotes a memory to semantic/neocortical storage based on **contextual semantic breadth**, not on how many labelled containers it appeared in.

### Root cause
`scope_kind` (e.g. "project") adds a rough category signal but it's still structural. The `scope_kind_breadth_pct` metric partially mitigates this, but most real deployments use only `project:*` scopes, making `distinct_scope_kind_count` always 1.

### Proposed resolution

**Add semantic diversity as a promotion bonus, not a gate.**

> **Review note (GPT-5.5):** Query embedding dispersion ≠ schema abstraction. A schema about "always run tests before push" recalled in Python, Go, and Rust projects may produce very similar query embeddings (all about testing workflows). Meanwhile "docker" may appear in legal, medical, and software contexts with high query dispersion while remaining a narrow fact. The metric risks measuring query dispersion rather than schema generality.

Revised approach: treat `semantic_diversity` as a **bonus multiplier** on scope breadth, not a gate. A schema with high query dispersion can reach a given stage with fewer distinct scopes; a schema with low query dispersion requires more scopes to compensate.

```
semantic_diversity = 1 - mean_pairwise_cosine(recall_query_embeddings)
effective_scope_breadth = scope_breadth_pct * (1 + 0.3 * semantic_diversity)
```

The multiplier (0.3) is a tunable parameter — calibrate empirically against the WikiScenarios generalization family. This changes promotion speed, not promotion ceiling, so it's safe to roll out incrementally.

**Files:** `schema_store.py:_update_utility_scores()`, `GeneralizationConfig` (new bonus_weight parameter).

### Measurement
- **New micro-benchmark**: store the same schema, recall it from N scopes — vary whether those scopes are semantically similar (all coding) vs diverse (coding, legal, medical). Assert that diverse-context recalls promote faster/further than homogeneous ones.
- **LoCoMo adversarial category** (currently 80.9%) should improve: genuinely generalised schemas would surface across topically different question types.

---

## Gap 2 — Bootstrap deadlock in stage promotion

### Problem
Stage-0 schemas are scope-locked at retrieval time — they don't surface in `activate` calls from other scopes. But stage promotion requires cross-scope recall events, which only accumulate if the schema surfaces. The schema can't exit stage 0 without cross-scope recall events, but it can't get cross-scope recall events without exiting stage 0.

### Current workaround
P4 in `engine.py` records cross-scope `remember()` events as `schema_evidence`, and `_update_utility_scores()` now counts those via a UNION query. This breaks the deadlock for the `remember()` path.

But: the bootstrap deadlock still exists for schemas that are never explicitly re-remembered cross-scope (the majority). A schema remembered in project:A that is relevant in project:B but never explicitly re-remembered there will stay at stage 0 forever.

### Proposed resolution

**Record offline reinforcement as a distinct signal — not as fabricated recall.**

> **Review note (GPT-5.5):** The original proposal (write synthetic `context_recall_items` entries) conflates observed recall with offline reinforcement. These are different kinds of evidence. Synthetic recalls can create positive-feedback loops: consolidation creates synthetic evidence → utility increases → promotion → more future recalls → more synthetic evidence. The brain does offline replay, but replay is not equivalent to fabricating retrieval events.

Revised approach: when the `Consolidator` detects a "reinforces" verdict between two schemas from different scopes, increment a dedicated counter `cross_scope_reinforcement_count` (stored in `facets_json`). `_update_utility_scores()` reads this counter separately from `context_recall_items` — it contributes to stage promotion but with lower weight than genuine observed recall.

```
observed_recall (context_recall_items) → full weight
offline_reinforcement (cross_scope_reinforcement_count) → partial weight (e.g. 0.5×)
```

This preserves the distinction between what was actually retrieved and what was inferred during consolidation.

**Files:** `core/consolidation.py:_write_latent_schema()`, `schema_store.py:_update_utility_scores()`, `GeneralizationConfig` (new weight parameter).

### Measurement
- **Cross-scope generalization bench**: Feed identical content from N scopes via `remember()` only (no cross-scope activate sessions). Run `consolidate_once()`. Assert schema reaches stage 1 faster than without the fix.
- Existing WikiScenarios `G-*` family (generalization) should improve — schemas from separate Wikipedia page sessions should reinforce each other during consolidation.

---

## Gap 3 — GeometricContradictionJudge bypassed for explicit memories

### Problem
The most brain-faithful component — `GeometricContradictionJudge`, which uses centroid cosine + facet-axis distance to detect when two schemas describe the same topic differently — only runs on **latent prototype schemas** created by consolidation. It never runs on **explicit `remember()` calls**.

When a user explicitly states "the project now uses DuckDB," the old SQLite fact can only be superseded if:
1. The cosine between old and new is ≥ 0.85 (true for short seed-pair-style sentences), AND
2. The direction_score ≥ 0.10 (true for tech tool substitution)

The wiki scenarios S-1/S-2 demonstrate the failure: cos(v1, v2) = 0.82/0.79, which falls below the same-scope gate. These facts are never superseded at `remember()` time, and consolidation doesn't run on them either.

In the brain, explicit salient experiences are **exactly** what triggers reconsolidation. The contradiction judge should be more available, not less.

### Proposed resolution

**Run a lightweight version of GeometricContradictionJudge in `remember()` at lower cosine threshold.**

After schema creation, search for topically-related schemas (cosine ≥ 0.70 — the judge's own `same_topic_cosine` threshold) and pass them through the judge. If the verdict is "contradicts" AND the new schema has higher salience (it was just explicitly stated), supersede the old one.

This lowers the cosine requirement from 0.85 (current P3 gate) to 0.70, compensated by requiring the judge's facet-axis divergence signal (`facet_dist >= 0.35`) — which is less likely to false-positive for paraphrases (which would have low facet distance since they represent the same facets).

**Note:** For single-sentence explicit memories, `facet_axes` will be empty → `facet_dist = 0.0` → the judge says "refines" not "contradicts." A fallback: when facet_axes are empty, use direction_score from the SupersessionManifold as the contradiction signal (already implemented for the 0.85+ range).

**Files:** `engine.py:remember()`, after the geometry pass. Reuse `GeometricContradictionJudge` from `latent/schema.py`.

### Measurement

**Current state (Gap 3 not yet implemented):**
- WikiScenarios S-1/S-2: v1_status stays "active" — nothing catches the cos 0.79–0.82 update pairs. The geometry pass requires 0.85; P1 regex is gone; the judge only runs on latent schemas, never on explicit `remember()` calls.
- StaleMemory concrete prefs: 86–99%. The ~1–14% gap at the bottom of each concrete category is the slice that falls in cos 0.70–0.85 and is currently unhandled.
- LME knowledge-update: 94.9%. Updates that happened to be short and same-structure are already caught at cos ≥ 0.85; the gap is paraphrase-style updates.

**Projected improvement after Gap 3 is implemented:**
- WikiScenarios S-1, S-2: v1_status flips to "superseded". Benchmark score unchanged (still hit=True — retrieval works either way) but data hygiene correct.
- StaleMemory concrete prefs: +2–5pp by recovering the cos 0.70–0.85 update band.
- LME knowledge-update: +1–2pp for paraphrase-style fact updates.

**Caveat:** for single-sentence explicit memories, `facet_axes` will be empty → `facet_dist = 0.0` → judge says "refines" not "contradicts." The fallback to `direction_score` then applies — but S-1/S-2 specifically have direction_score 0.082/−0.085, both below DIRECTION_THRESHOLD (0.10). So S-1/S-2 would still not supersede even after Gap 3, unless the fallback threshold is lowered or a different signal is used for the empty-facet case. Full S-1/S-2 resolution may require a separate approach.

---

## Gap 4 — Episodic summary pollution from context_query events

### Problem
`context_query` events (from `slowave_activate`) are logged as raw events and participate in episode formation. When consolidation clusters the session's episodes, the activate query text ("remember Karpathy Guidelines for coding") becomes the central episode of a cluster, blended with other session content (cimmeria CRITICAL INVARIANTs, delfica microservice facts). This produces episodic summaries like `"remember Karpathy Guidelines for coding CRITICAL INVARIANT: event_time must always come from record.updated_at..."` — noise that looks like a Karpathy schema but is actually a session snapshot.

In the brain, the question you pose to retrieve a memory is not itself encoded as a memory trace. Only the retrieved content and its context are consolidated.

### Proposed resolution

**Two options, independent and complementary:**

**A. Exclude `context_query` events from episode formation** (surgical).  
In `IngestService.form_episodes()`, filter out events with `type = 'context_query'` before passing to the episodic encoder. These events are queries, not facts; they should not anchor prototypes.

**B. Deprioritise `context_query` events as central episode candidates** (softer).  
In `LatentSchemaBuilder.build()`, when selecting the `central_episode_id` (the episode whose text becomes the schema's text handle), skip episodes whose source event type is `context_query`. Pick the next-most-central episode instead.

Option A is cleaner and has no risk of information loss (query text is already stored in `context_recall_events`). Option B is safer if downstream components depend on `context_query` events being in the episodic store for other reasons.

**Files (option A):** `core/services/ingest.py:form_episodes()` — add type filter.  
**Files (option B):** `latent/schema.py:LatentSchemaBuilder.build()` — skip context_query as central episode.

### Measurement
- **Direct**: after fix, query `schemas WHERE schema_class = 'episodic_summary' AND content_text LIKE '%remember%'` — count should drop to near zero.
- **WikiScenarios generalization (G-*)**: currently these scenarios benefit from consolidation of Wikipedia content; removing query noise should improve the signal-to-noise in consolidated schemas, which should improve retrieval keyword hit rate.
- **LoCoMo multi-session** (84.9%): cross-session recall accuracy should improve when episodic summaries represent actual facts rather than query-fact blends.

---

## Gap 5 — No near-duplicate suppression at recall time

### Problem
When two semantically similar schemas in the same scope both score above the activation threshold, both surface in `activate`, consuming token budget redundantly.

### Framing note (GPT-5.5)
> True lateral inhibition is dynamic competition among representations — not a simple cosine threshold. The brain analogy is weaker here than for other gaps. Frame this as **context compression** (engineering) rather than brain-faithful inhibition.

### Proposed resolution (lower priority)

Apply a **Maximal Marginal Relevance (MMR)** deduplication pass in the `WorkingMemoryGate` after scoring: schemas are admitted greedily, each new candidate penalised by its maximum cosine similarity to already-admitted schemas. This is standard information-retrieval practice, not neuroscience.

**Files:** `core/context.py:WorkingMemoryGate`.

### Measurement
- Token efficiency: working context size should shrink for scopes with many near-duplicate schemas.
- No benchmark regression expected (MMR selects the most relevant representative, not an arbitrary one).

---

## Gap 6 — Schema abstraction quality (new, identified in review)

### Problem

> "Promotion seems driven primarily by recall frequency, scope breadth, and temporal spread. None of those measure whether a schema became more abstract." — GPT-5.5

Current pipeline: `episodes → prototypes → schema promotion`. Promotion is driven by *utility* (how often recalled) and *breadth* (how many scopes). Neither measures *abstraction level*.

Example:
- Project A: "The project uses pytest for testing"
- Project B: "The project uses cargo test for testing"  
- Project C: "The project uses go test for testing"

If all three reach the same cluster and promote, the schema text will be whichever sentence was most central — a specific tool name, not the principle "run tests before committing." The neocortical abstraction is never formed.

A brain-inspired system should distinguish `fact → schema → principle` as the schema consolidates across more diverse contexts. Currently Slowave stops at globally promoted facts; it has no mechanism for principle emergence.

### Why this is the largest remaining gap

The other gaps are correctness issues (pollution, bypass, deadlock). This is a *capability* gap — Slowave cannot currently produce abstract principles from specific instances, even with perfect execution of all other gaps fixed.

### Proposed resolution (research-level)

**Phase 1 — measure abstraction level of existing schemas** (immediate, no code change).  
Compute the within-cluster embedding variance of a promoted schema's source episodes. Low variance = specific fact (all episodes say the same thing, same vocabulary). High variance = abstract principle (episodes say different things that map to the same centroid). Track `episode_embedding_variance` in facets.

**Phase 2 — bias the central episode selection toward higher abstraction**.  
`LatentSchemaBuilder` currently picks the episode closest to the centroid as the text handle. Replace with the episode *least similar to any other single episode* — the one that captures the "essence" rather than the most common example. This changes the schema's text handle from "uses pytest" to the episode that says something like "testing discipline" when one exists.

**Phase 3 — schema text re-synthesis at stage promotion** (requires LLM at boundary only).  
When a schema promotes from stage 2 → 3, run a single LLM call to synthesise a principle-level text handle from the cluster of source episodes. This is the one point where language is genuinely necessary — and it's at the boundary of the system, not inside consolidation. Consistent with the north star: LLM as output-only verbalisation channel, not memory operator.

### Measurement
- **New metric**: `episode_embedding_variance` distribution across stage 0 vs stage 3 schemas. Stage 3 schemas should have significantly higher variance than stage 0.
- **Abstraction bench** (new): feed 5 specific instances (pytest, cargo test, go test, unittest, jest) across 5 scopes. After consolidation + promotion, assert the schema's central text is the principle "run tests before committing" (or a cosine-close equivalent) rather than any specific tool name. Requires either the LLM phase or the biased central episode selection.
- **LoCoMo multi-session** (84.9%): questions that require cross-session generalisation should improve if schemas carry principle-level content.

---

## Priority order (revised after external review)

| # | Gap | Tier | Implementation cost | Priority |
|---|---|---|---|---|
| **4** — context_query pollution | Tier 1 (architectural flaw) | Low (filter one event type) | 🔴 Do first |
| **3** — judge bypassed for explicit memories | Tier 1 (architectural flaw) | Medium (wire existing judge at 0.70) | 🟠 Second |
| **2** — bootstrap deadlock | Tier 2 (validated idea) | Medium (separate counter, not synthetic recall) | 🟡 Third |
| **6** — schema abstraction quality | New (largest capability gap) | High (3-phase research track) | 🟢 Fourth — start Phase 1 (measurement) immediately |
| **1** — semantic diversity promotion bonus | Tier 2 (bonus, not gate) | Medium (tunable multiplier) | 🟢 Fifth — after calibration data exists |
| **5** — near-duplicate suppression (MMR) | Tier 3 (engineering) | Low | 🔵 Opportunistic |

---

## Benchmark expectations per gap

> ⚠️ All "projected" figures are for *after* the gap is implemented. Current state is listed separately.

| Gap | Current state on existing benchmarks | Projected after fix | New benchmark needed |
|---|---|---|---|
| **4** pollution | G-* wikiscenarios 100% (already good); LoCoMo multi-session 84.9% | G-* +1–2pp; LoCoMo multi-session +1–2pp | Pollution rate: `COUNT(episodic_summary WHERE content LIKE query verb)` |
| **3** judge bypass | S-1/S-2 v1_status="active" (not superseded); StaleMemory concrete 86–99%; nothing handles cos 0.70–0.85 | StaleMemory concrete +2–5pp; LME knowledge-update +1–2pp; S-1/S-2 data hygiene fix (score unchanged) | Extended S-* asserting `v1_status="superseded"`; note S-1/S-2 themselves may still fail (direction_score 0.082/−0.085 < 0.10) |
| **2** bootstrap | Stage-0 schemas stuck without cross-scope activate; no existing benchmark covers this | Flat on all existing benchmarks | Promotion speed bench: N-scope `remember()` only → consolidate → assert stage ≥ 1 |
| **1** diversity bonus | Promotion speed uniform regardless of recall context diversity | Flat on existing benchmarks | Promotion rate bench: homogeneous vs diverse recall contexts → different stage advancement rates |
| **5** MMR | Near-duplicate schemas both surface; no suppression | Token efficiency −10–20%; accuracy flat | Redundancy ratio per activate call (mean max-cosine between returned schemas) |
| **6** abstraction | Specific facts promoted, no principles extracted; LoCoMo commonsense 50% | Flat (Phase 1–2); LoCoMo commonsense +5–15pp (Phase 3, LLM boundary only) | PrincipleRecall bench: 5 specific instances → assert retrieved schema is principle-level |

**Macro expectation:** Gap 4 and Gap 3 are the only two that will move existing benchmarks measurably (3–8pp combined across StaleMemory and WikiScenarios). Gaps 1, 2, 5, 6 require new benchmarks to make their improvements visible — shipping them without new tests makes them invisible on paper. The benchmarks must evolve alongside the system.
