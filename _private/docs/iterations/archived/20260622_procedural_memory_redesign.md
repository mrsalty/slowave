# Procedural Memory Redesign

**Date:** 2026-06-22  
**Status:** Discussion — not yet implemented  
**Topic:** Auto-detecting procedural memories; procedure supersession; removing `slowave_remember_procedure` from the MCP surface

---

## Problem statement

There are two MCP tools for storing memories:

- `slowave_remember(content, type)` → stores a **Schema** (embedding-backed, `schemas` table). When called with `type="procedure"`, it silently stores a flat schema with a `procedure` tag — it does NOT route to the procedural store.
- `slowave_remember_procedure(procedure_steps, goal, ...)` → stores a **ProceduralMemory** (`procedural_memories` table, no embeddings, trigger-matched retrieval).

The routing decision is forced onto the client. The client has no automatic signal to distinguish "remember to always run unit tests before committing" (procedure) from "the API key is stored in ~/.config" (fact). Any keyword-based heuristic would be English-only and fragile.

---

## What is procedural memory?

Procedural memory in the brain:
1. **Implicit** — fires automatically in context, not retrieved by conscious query
2. **Action-oriented** — encodes *how to act*, not *what is true*
3. **Sequence-ordered** — step A → step B → step C; order is part of the memory
4. **Context-triggered** — activates when situational cues match a stored policy
5. **Feedback-strengthened** — success/failure reinforces or weakens it (basal ganglia dopamine)

Declarative/semantic memory (schemas) encodes facts: *X is Y*, *prefer Z*, *the value is W*.  
Procedural memory encodes action policies: *when doing X, always first do A then B*.

These are genuinely different storage architectures — two stores are neuroscientifically correct. The problem is the routing, not the separation.

---

## Proposed design

### 1. Remove `slowave_remember_procedure` from the MCP surface

Keep `engine.remember_procedure()` as an internal method (useful for seeding and tests). Remove it as a public MCP tool. No client should ever need to call it explicitly.

### 2. Auto-detect procedural content via latent space prototype classification

#### Why not keyword heuristics

A keyword/regex approach (matching `always`, `before`, `whenever`, etc.) is English-only and would fail for any other language. Slowave is a universal system — it must work for Italian, Japanese, French, Arabic, or any language a client might use.

#### The latent space approach

Procedural content and declarative content form **distinct regions in embedding space**, independent of language. "Always run tests before committing" (EN), "Toujours lancer les tests avant de committer" (FR), and "先にテストを実行してからコミットする" (JA) all embed near each other in a multilingual encoder — and all far from declarative facts in any language.

This is the Slowave thesis applied to routing: **classification is geometry, not language**.

**Binary prototype classifier:**

Two prototype vectors stored in the DB:
- `procedure_centroid` — mean embedding of K canonical procedure examples across multiple languages
- `fact_centroid` — mean embedding of K canonical fact examples across multiple languages

At `remember` time:
```
emb = encode(content)
score = cosine(emb, procedure_centroid) - cosine(emb, fact_centroid)
if score > threshold → route to procedural store
```

**Self-improving through existing feedback loop:**
- `slowave_reinforce(feedback="wrong")` on a misclassified memory → pull centroid away from that embedding
- Explicit `type="procedure"` from the caller → reinforce procedure centroid toward this embedding
- Over time the classifier adapts to the user's domain and language without any rule changes

**Seed set:**
- ~20 canonical examples per class, spanning 5–8 languages and multiple domains (coding, cooking, healthcare, business, personal habits)
- Embedded at init and stored in DB as the initial centroids
- Prototypes recomputed during consolidation replay as new confirmed examples accumulate

**Structural pre-filter (English and structured formats only, kept as fast path):**

For content that is already explicitly structured (numbered lists, bulleted checklists), a structural pre-filter can bypass the embedding classification entirely — it's unambiguous regardless of language:
- `^\d+[.)]\s+` with ≥2 items → procedure (numbered steps)
- `^[-*]\s+` with ≥2 items → procedure (bulleted checklist)
- `type="procedure"` explicitly passed → procedure

The latent classifier handles everything else, including all natural-language single-sentence policies in any language.

#### Encoder upgrade: multilingual model required

`all-MiniLM-L6-v2` is English-optimized. True multilingual classification requires switching to `paraphrase-multilingual-MiniLM-L12-v2` — same 384 dimensions, same sentence-transformers interface, 50+ languages. This is a **separate but necessary change** for the latent classifier to work correctly across languages. The prototype approach works with either encoder; only accuracy changes.

### 3. Step and trigger extraction

Once content is classified as a procedure:

- **Multi-step (numbered/bulleted):** parse each item as a separate step
- **Single-sentence policy:** `[content]` as a single step; extract trigger from temporal clause if present
- **Trigger extraction:** match `before (\w+)`, `after (\w+)`, `when(ever)?\s+(\w+)`, `upon (\w+ing)` — the existing `_terms()` function in `procedural.py` handles tokenisation, and this works cross-linguistically for common prepositions

### 4. Procedure supersession on write

The existing `procedural.py` has `_jaccard()`, `_list_similarity()`, `status: candidate|active|deprecated`, and confidence-based demotion in `apply_feedback()`. What's missing is a conflict check at write time.

**Algorithm (in `ProceduralMemoryStore.create()`):**

```
store new procedure P_new
→ retrieve active procedures with trigger overlap (jaccard on trigger_pattern)
→ for each P_old where:
      trigger_overlap(P_old, P_new) > 0.6
      AND step_action_overlap(P_old, P_new) > 0.3
  → mark P_old.status = "deprecated"
  → record P_old.superseded_by = P_new.id  (new DB column)
→ include supersession info in store response
```

Brain model: **retroactive interference** — a new policy in the same contextual slot inhibits the old one. The old procedure is demoted (not deleted) and can surface as a fallback if the new one fails repeatedly.

**New DB column needed:** `superseded_by_id INTEGER REFERENCES procedural_memories(id)` on the `procedural_memories` table.

---

## Files to change

| File | Change |
|---|---|
| `slowave/mcp/tools.py` | Route in `slowave_remember` using classifier; structural pre-filter for explicit formats; remove `slowave_remember_procedure` tool registration |
| `slowave/latent/classifier.py` *(new)* | `MemoryTypeClassifier`: holds procedure/fact centroids, `classify(emb) -> str`, `reinforce(emb, label)` |
| `slowave/core/engine.py` | Init classifier; call `classify()` in `remember()`; call `reinforce()` from feedback path |
| `slowave/core/procedural.py` | Add supersession check in `create()`; add `superseded_by_id` field to `ProceduralMemory` dataclass |
| `slowave/storage/schema.sql` | Add `superseded_by_id` column and `memory_type_prototypes` table (stores procedure/fact centroids) |
| `slowave/symbolic/encoder.py` | Upgrade default model to `paraphrase-multilingual-MiniLM-L12-v2` (separate PR) |
| `tests/unit/test_procedural_memory.py` | Tests for latent classification, structural pre-filter, step extraction, supersession |

---

## Verification

1. `slowave_remember(content="always run unit tests and linting before committing or pushing", scope="project:slowave")` → response has `procedure_id`, not `event_id`
2. `slowave_remember(content="ricordati sempre di lavarsi le mani prima di cucinare", scope="project:slowave")` (Italian) → same result
3. `slowave_activate(...)` → new procedure appears in `procedures` array
4. Store a superseding procedure → old one appears as `deprecated` in DB with `superseded_by_id` set
5. Run unit tests: `.venv/bin/python -m pytest tests/unit/test_procedural_memory.py -v`
6. Run smoke tests: `.venv/bin/python -m pytest tests/unit/test_smoke.py -v`

---

## Open questions

- Supersession threshold tuning: 0.6 trigger overlap + 0.3 step overlap — needs eval against real examples.
- Should a superseded procedure be retrievable at all, or fully suppressed? (Brain: inhibited not deleted — lean toward surfacing with a `deprecated` flag and low score as fallback.)
- Prototype threshold: what cosine margin is reliable enough to avoid false positives? Needs a small labelled eval set.
- Encoder upgrade timing: should the multilingual encoder switch happen in the same PR as the classifier, or separately to isolate risk?
---
## Review feedback (2026-06-22)

### Strengths

1. **Aligned with core thesis.** The argument that procedural and declarative content occupy distinct regions in embedding space, independent of language, is the exact reasoning that justifies slowave's architecture. This isn't bolted-on ML — it's the system applying its own principles to itself.

2. **Binary prototype classifier is simple and testable.** Two centroids, one cosine comparison, one threshold. No neural net, no training loop, no external dependency. It's inline with the "brain only, no LLM" constraint.

3. **Self-improving through existing feedback loop.** Using `slowave_reinforce` to nudge centroids is elegant — the classifier gets better the more it's used, with zero new infrastructure.

4. **Structural pre-filter as a fast path.** Catching numbered lists and explicit `type="procedure"` before the embedding step is pragmatic — saves compute and catches unambiguous cases.

5. **Supersession with retroactive interference.** Demoting (not deleting) old procedures and surfacing them as fallbacks mirrors basal ganglia function correctly. The `superseded_by_id` foreign key is the right schema choice.

### Critical gaps (resolve before implementation)

#### 1. Cold start for the classifier — no plan for initial centroids

The classifier needs `procedure_centroid` and `fact_centroid` to exist before it can classify anything. On a fresh install, these don't exist. The document mentions "K canonical examples across multiple languages" but never specifies what K is, what the canonical examples are, or what happens when centroids are absent (fallback to structural pre-filter only? always route to schemas?).

**Recommendation:** Add a `seed_classifier()` that runs at engine init if centroids are null, using ~10 hardcoded multilingual example pairs. Document the fallback behavior (route to schemas when classifier is cold).

#### 2. Trigger extraction is language-dependent, contradicting the multilingual thesis

The trigger extraction regex patterns (`before (\w+)`, `after (\w+)`, `when(ever)?\s+(\w+)`, `upon (\w+ing)`) only match English. Italian "prima di", French "avant de", Japanese "前に" — none will match. The claim that `_terms()` tokenization handles this doesn't hold. Since supersession depends on accurate trigger extraction via Jaccard overlap, non-English procedures will silently fail to supersede.

**Recommendation:** Either (a) accept that trigger extraction is English-only for now and document it as a known limitation with a plan to use LLM-based extraction later, or (b) replace regex extraction with embedding-based trigger similarity (cosine on the trigger clause), making trigger matching fully language-agnostic too.

#### 3. No client override mechanism

`slowave_remember_procedure` is removed from the MCP surface, but the latent classifier can misclassify. The document says explicit `type="procedure"` should reinforce the centroid, but doesn't say whether it also *overrides* routing at storage time. Without an override, the classifier becomes a single point of failure.

**Recommendation:** Keep `type` as an optional override. If `type="procedure"` or `type="fact"` is passed explicitly, bypass the classifier entirely and route directly. This also solves the cold-start chicken-and-egg problem: the first few procedures can be explicitly typed until centroids are well-formed.
### Important gaps (resolve during implementation)

#### 4. Structural/latent classifier disagreement resolution

Two paths can fire (structural pre-filter and latent classifier). When they disagree — e.g., a numbered list of facts — which wins? No resolution strategy is defined.

**Recommendation:** Structural pre-filter is a *strong hint* but the latent classifier is the *final arbiter*. If structural says "procedure" but latent says "fact" with high confidence, route to schemas and log a warning. Conversely, latent "procedure" with high confidence should override a negative structural result.

#### 5. `slowave_remember` API migration path is undefined

What happens to the `type` parameter on `slowave_remember`? Does it become optional? Deprecated? What about existing code that calls `slowave_remember(type="procedure")`?

**Recommendation:** `type` becomes optional (defaults to auto-detect). If passed explicitly, it overrides the classifier (see gap #3). Existing callers with `type="procedure"` continue to work unchanged. `slowave_remember_procedure` is soft-deprecated for one release (emits a log warning) then removed.

#### 6. Supersession silently fails when trigger extraction is weak

If trigger extraction returns empty or produces weak tokens, supersession silently never fires — you get duplicate/conflicting procedures without warning.

**Recommendation:** Fall back to full-text step overlap if trigger extraction returns empty. Emit a warning in the store response when a new procedure has high step-action overlap with an existing active one but trigger overlap is below threshold.

#### 7. Imperative mood can confuse the classifier

"Use SQLite for this project" is an imperative sentence but it's a preference/decision, not a procedure. The binary centroid model may struggle with imperative mood in declarative statements.

**Recommendation:** Document as a known limitation. The structural pre-filter will catch some cases, and the reinforcement loop will nudge centroids over time. Track false-positive rate.

#### 8. Encoder upgrade dependency is underspecified

The multilingual classifier requires a multilingual encoder. If the current model is English-optimized, the classifier can't work correctly for non-English content. The document says the encoder upgrade is a "separate PR" but the PR ordering must be: encoder upgrade first, then classifier.

**Recommendation:** Make the dependency explicit. Either bundle the encoder upgrade in this PR, or have the classifier gate on the encoder version at init (`if model is not multilingual: raise ConfigurationError`).

#### 9. Step extraction lacks specificity

The document describes step extraction from numbered lists but doesn't specify what delimiters count, whether bullets are included, how nested lists are handled, or what "newline-separated" means for single-sentence policies.

**Recommendation:** Specify a concrete grammar: numbered = lines matching `^\s*(?:\d+[.)]\s+|[-*+]\s+)`. Bullet points count. Nested items are flattened. Single-sentence content becomes a single step with the whole content as the step text.

#### 10. Seeding workflow after removing `slowave_remember_procedure`

If `slowave_remember_procedure` is removed, the only way to get a procedure into the system is through the auto-classifier — which has a cold-start problem (gap #1). There's a chicken-and-egg loop.

**Recommendation:** Add a seeding workflow: run seeding scripts to populate initial procedures and centroids, then the auto-classifier takes over. Alternatively, the explicit `type` override (gap #3) serves this purpose.

### Additional verification tests

Add to the verification plan (lines 136–142):

7. **Cold-start test:** Fresh DB, no centroids → `slowave_remember(content="always do X before Y")` → should route to schemas (fallback) until centroids are seeded.
8. **Misclassification correction:** Store a misclassified item → call `slowave_reinforce(feedback="wrong")` → store the same item again → verify it routes correctly the second time.
9. **Supersession chain:** Store P1 → store P2 (supersedes P1) → store P3 (supersedes P2) → verify P1 and P2 are deprecated, P3 is active, and the chain is traceable via `superseded_by_id`.
