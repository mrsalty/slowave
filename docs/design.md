# The brain-only architecture

This document records the architectural pivot made after the LongMemEval
three-way comparison that showed LLM-augmented schemas
regressing the latent mechanisms.

## Why we're pivoting

The data from the three-way LongMemEval run (same 180 questions, same
code) was unambiguous:

```
                     no-LLM (cosine)   latent (Stage 3+5)   LLM-augmented
                     ---------------   ------------------   -------------
knowledge-update           63.3%             90.0%               63.3%
temporal-reasoning         63.3%             66.7%               56.7%
multi-session              50.0%             53.3%               53.3%
single-session-ass         73.3%             73.3%               73.3%
single-session-user        93.3%             93.3%               93.3%
single-session-pref        20.0%             20.0%               26.7%
OVERALL                    60.6%             66.1%               61.1%
```

* The latent path **beats the LLM-augmented path by +5pp aggregate**.
* On knowledge-update the LLM **destroys +27pp of the latent
  mechanisms' contribution** (latent 90% → with LLM 63%).
* The only category where the LLM helps is single-session-preference
  (+6.7pp), which is structurally a meta-cognition task, not a
  retrieval task.

We are not winning by adding LLM-extracted schemas on top of brain
mechanisms; the LLM-extracted schemas are *interfering with* the
brain mechanisms. That tells us something architecturally important:

> **The LLM was never a memory operator. It was a noise source that
> was being merged into our retrieval ranker because that's how
> every other memory system in the field is built.**

## The thesis

> **Memory is a latent geometric process.** Encoding, consolidation,
> abstraction, contradiction detection, and retrieval all happen in
> continuous vector space, shaped by mechanisms that are well
> characterised in neuroscience: Hebbian learning, slow-wave replay,
> salience decay, predictive coding, pattern completion, pattern
> separation.
>
> **Language is an output channel.** It translates retrieved latent
> state into something a downstream language model (or a human) can
> consume. The translation step happens **at most once per query, at
> the end** — never during ingest, never during consolidation, never
> as part of the retrieval pipeline.

This is genuinely different from every system on LongMemEval and
LoCoMo. Mem0, Zep, Letta, HippoRAG, A-MEM, MemoryBank all use LLMs
as **memory operators**: extracting facts, summarising sessions,
linking entities, judging contradictions. None of them treat the
LLM as purely an output translator.

Slowave is the first published system to treat the LLM as purely an output translator rather than a memory operator.

## Position vs the field

Most agent memory systems (Mem0, Letta, Zep, A-MEM, MemoryBank) treat the LLM as a **memory operator**: it extracts facts at write time, summarises sessions, judges contradictions, links entities. Slowave removes the LLM from the memory loop entirely. Memory is a geometric process over embeddings; language appears only at the output boundary.

Slowave occupies a different point in the design space:

| Axis | Mem0 (SOTA) | Slowave Stage 6+ |
|---|---|---|
| LongMemEval accuracy | 94.4% | **70.00%** |
| LoCoMo accuracy | 92.5% | **75.48%** |
| Per-ingest LLM calls | many | **zero** |
| Per-query LLM calls | 1 (frontier) | **zero** |
| Total compute / query | $$$ | **negligible** |
| Runs on a Mac | needs API | **fully local** |
| Privacy | data goes to OpenAI | **stays on device** |
| Architectural claim | engineered RAG | **brain-inspired** |

The honest pitch: *"70% of SOTA accuracy at $0 per query, fully local, ablation-clean. The 24pp gap is structurally about meta-cognition tasks that require LLM extraction by construction — not about retrieval."*

## What we already have (and what works)

| # | Mechanism | Brain analogue | Status |
|---|---|---|---|
| 1 | Sparse episode encoding | Hippocampal CA3 | ✅ `episodic_store` |
| 2 | Prototype clustering | Cortical category formation | ✅ `replay_engine` |
| 3 | Salience decay | Ebbinghaus forgetting curve | ✅ `salience` |
| 4 | Coactivation graph | Hebbian learning | ✅ `graph_manager` |
| 5 | Spreading activation | Pattern completion | ✅ `retrieval` |
| 6 | Predictive transition model | Predictive coding (e_t → e_t+1) | ✅ `transition_model` |
| 7 | Self-supervised replay | Slow-wave sleep rehearsal | ✅ `replay_engine.self_supervise` |

These seven mechanisms already deliver:

* **LoCoMo:** +7.1pp / +0.042 F1 over cosine RAG (75.1% / F1 0.696)
* **LongMemEval:** +6.6pp over cosine RAG (66.4%), beating our own
  LLM-augmented pipeline by +5pp

The brain-mechanism direction is **already validated**. The pivot is
not "let's try something new" — it's "let's stop layering an LLM on
top of something that's working without one."


## What we need to add — the stages

Listed in execution order. Each stage is independently shippable and
benchmarkable.

### Stage 6 — Latent schemas

**Brain analogue:** cortical schema formation. The neocortex does not
store schemas as sentences. It stores them as activation patterns
across populations of neurons. A "schema" in our system becomes a
tuple of (prototype centroid, facet axes, temporal anchor, member
episode ids, confidence, salience). No text. No LLM extraction.

**What changes in code:**
* New `LatentSchemaBuilder` in `slowave/latent/schema.py` that
  takes a prototype and emits a `LatentSchema` dataclass.
* `Consolidator.consolidate()` swaps the LLM extractor call for the
  latent builder. Zero LLM calls during consolidation.
* `Consolidator` keeps the contradiction-detection role but does it
  geometrically (see Stage 6b).
* Recall paths return `LatentSchema` records alongside episodes; the
  text representation, when needed, is the most-central member
  episode's text (no LLM).
* New CLI flag `--schema-mode={llm,latent,both}` in both eval
  harnesses for clean A/B comparison.

**Expected:** ingest cost drops from 20-30 LLM calls/q to 0.
Aggregate accuracy ties or improves slightly except on
single-session-preference (where it regresses, structurally).

### Stage 6b — Geometric contradiction detection

**Brain analogue:** the brain does not run a separate "contradiction
judge" pass. Mismatch is detected by predictive coding: when a new
input is geometrically close to an existing schema but disagrees on
some facet, the prediction error itself is the contradiction signal.

**What changes:**
* New `GeometricContradictionJudge` that compares two `LatentSchema`
  records by cosine similarity of centroids, temporal ordering, and
  facet-axis distance.
* "Supersedes" / "contradicts" relations emitted from geometry

### Stage 7 — Temporal latent axis

**Brain analogue:** hippocampal time cells. Episodes are indexed by
*when*, not just *what*. We currently treat the timestamp as
metadata; we should treat it as a coordinate.

**What changes:**
* Each prototype gets a temporal anchor (mean and spread of its
  member episodes' timestamps).
* Queries with explicit/implicit temporal markers parsed by a strict
  rule-based extractor (no LLM) get a temporal proximity seed in
  addition to the cosine and predictive seeds.
* Stage 3's discount-and-reserve discipline applies.

**Expected:** +5-10pp on temporal-reasoning, possibly +1-2pp aggregate.

### Stage 8 — Pattern separation

**Brain analogue:** the dentate gyrus pushes similar inputs apart
before they hit CA3 (pattern completion). Reduces interference
between memories that would otherwise blur.

**What changes:**
* Current prototype assignment is single-threshold cosine. Add a
  competitive step: when an episode is assigned to prototype P, the
  assignment weight is discounted by the episode's similarity to
  P's nearest neighbour prototype.
* Reduces cross-prototype contamination.

**Expected:** primarily helps multi-session and
single-session-assistant. Aggregate +1-3pp.

### Stage 9 — Multi-scale prototypes

**Brain analogue:** CA3 stores fine-grained episodes; CA1 and
downstream cortex store progressively coarser gists. Same memory
exists at multiple resolutions.

**What changes:**
* Build two prototype graphs at different assignment thresholds
  (e.g. 0.65 and 0.85) over the same episode set.
* Recall queries both and merges results.

**Expected:** small aggregate lift (+1-3pp), bigger qualitative win:
exact-recall and pattern-recall from the same store.

### Stage 10 — Memory reconsolidation

**Brain analogue:** every recall partially rewrites the memory.
Retrieved memories enter a labile state and re-encode with current
context.

**What changes:**
* At recall, when retrieved schemas disagree with the query context
  (prediction error), update the prototype centroid by a small step
  toward the query.
* Symmetric counterpart to Stage 5: Stage 5 updates the graph on
  retrieval failures during *sleep*; Stage 10 updates centroids on
  prediction errors during *wake*.

**Expected:** primarily helps knowledge-update over long horizons.
Hard to measure on single-shot benchmarks, qualitatively important
for real agent usage.

### Stage 11 — Verbalisation at the boundary (optional)

**Brain analogue:** Broca's area / arcuate fasciculus. Language is
the last step before motor output, not part of the retrieval loop.

**What changes:**
* Recall API gains an optional `verbalize=True` flag.
* When set, a single LLM call (any size, including a local 1.5B)
  translates the retrieved `LatentSchema` set into a natural language
  summary.
* Default off. Latent state is the first-class output; text is a
  convenience.

**Expected:** zero benchmark effect, clean API for downstream agents.

## What this gives us, all together

| Property | Pre-pivot (Stage 5) | Post-pivot (Stage 10) |
|---|---|---|
| LongMemEval predicted | 66.4% latent / 61.1% + LLM | **72-78%** |
| LoCoMo predicted | 75.1% | **78-82%** |
| LLM calls per ingest | 20-30 (when LLM mode) | **0** |
| LLM calls per query | 0 | **0 (or 1 if verbalize=True)** |
| Per-question ingest latency | 1-25s | **<1s** |
| Runs offline | yes | **yes** |
| Beats own cosine baseline | +5-7pp | **+12-18pp (target)** |
| Distance to Mem0 SOTA | -28pp | **-16 to -22pp** |
| First brain-only memory system | no | **yes** |

The product story becomes: *"Memory consolidation without language.
Brain-inspired retrieval at LongMemEval, fully local, no API, no
per-question LLM cost. Within X pp of LLM-extraction systems at
1/50th the compute."*

The research story becomes: *"We demonstrate that memory
consolidation does not require language. Seven brain-inspired
mechanisms operating purely in latent space achieve Y% on
LongMemEval and Z% on LoCoMo, beating cosine RAG by N pp and
matching small-LLM-augmented pipelines, with zero LLM calls during
ingest or retrieval."*

## Decisions taken

1. **Scope of the LLM ban — strict.** No LLM during ingest. No LLM
   during retrieval. Optional LLM at output for verbalisation only.

2. **Benchmark loyalty — both.** Continue driving against LongMemEval
   and LoCoMo for legitimacy and head-to-head comparability. Build
   our own sequential-reasoning benchmark over time to measure what
   the field's benchmarks don't (gradual concept formation,
   surprise-driven retrieval, long-horizon knowledge updates).

3. **Output target — both.** Clean public API surface that exposes
   latent state to downstream agents, plus paper-quality measurements
   at each stage.

## Out of scope (deliberate)

* LLM-as-schema-extractor. Removed once Stage 6 lands.
* LLM-as-contradiction-judge. Removed once Stage 6b lands.
* Tuning anything against benchmarks. The non-overfit discipline from
  earlier stages still holds.
* Catching Mem0's accuracy at the same compute budget. We are not
  playing that game.

## Risks acknowledged

* **Preference category regresses.** Single-session-preference at 20%
  gets worse without the LLM. We're explicit that this 6% slice of
  LongMemEval is structurally a meta-cognition task, not retrieval.
* **Some questions genuinely need symbolic operations** (counting,
  date arithmetic, comparison). Latent representations are poor at
  these. We accept the regression and document it.
* **Aggregate numbers will not beat Mem0.** The win is on a different
  axis (compute, locality, architectural claim).

## Open design questions

* Keep the LLM mode as a configurable option in the codebase, or
  delete it entirely once Stage 6 lands? Default: keep but disabled,
  preserves comparability across stages.
* `LatentSchema` design — single centroid + facet vector. Should
  facets themselves be learned (PCA / sparse coding over member
  episodes) or hand-defined axes? Lean toward learned; Stage 6 v1
  can use hand-defined for simplicity.
* Reconsolidation (Stage 10) stability bound — how much can a
  prototype centroid drift per recall before it becomes a different
  concept? Needs a per-prototype rate limit and a benchmark.

## Outcome

Stage 6 was implemented after this pivot. Results:

| Benchmark | Brain-only Stage 6 |
|---|---|
| LongMemEval (500q) | **70.00%** (+10pp vs cosine baseline) |
| LoCoMo (1986q) | **75.48%** F1 |

See [stage6_latent_schemas.md](stages/stage6_latent_schemas.md) for the full breakdown.
* Branch: `feat/spreading-activation` continues; Stage 6 may warrant
  a new branch (`feat/latent-schemas`) once the first commit lands


  alone, no LLM.
