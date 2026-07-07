# Slowave DB Analysis and Findings — 2026-06-26

## Scope

Direct SQLite analysis of `~/.slowave/slowave.db` (2.9 MB + 4.0 MB WAL) plus codebase tracing
to explain each anomaly found. No code changes made; this document records findings and fix
directions only.

## Database snapshot (2026-06-26)

| Table | Rows |
|---|---|
| sessions | 73 |
| raw_events | 185 |
| episodic_memories | 121 |
| semantic_prototypes | 42 (21 fine + 21 coarse) |
| prototype_edges | 612 |
| schemas | 110 |
| schema_relations | 19 |
| schema_evidence | 232 |
| worker_runs | 184 |
| context_recall_events | 62 |
| context_feedback_events | 44 |
| consolidation_debug | 5,307 |

### Sessions

73 total across 4 scopes. Session state breakdown:

| State | Count |
|---|---|
| Truly open (`ended_ts IS NULL`) | 6 |
| Reaped without outcome (`ended_ts NOT NULL`, `outcome NULL`) | 20 |
| Committed with outcome | 48 |

Scope distribution (committed + open):

| Scope | Total | Success | Open |
|---|---|---|---|
| project:slowave | 61 | 37 | 24 |
| project:delfica | 9 | 7 | 2 |
| project:cimmeria | 2 | 2 | 0 |
| project:smoke | 2 | 1 | 1 |

### Schemas

110 total — 109 active, 1 superseded. All created via explicit `remember()` calls; the background
worker created only 2 via consolidation. Confidence is uniformly high (~0.987). Salience is heavily
skewed (max 137, median near 0.01).

Schema relations: 19 edges for 110 nodes (17% connected). Breakdown: 9 `reinforces`, 9 `refines`,
1 `supersedes`. Zero `contradicted` schemas ever produced.

### Episodic memories

121 episodes. **All have `salience = 0.01`** — the configured floor. 51 of 121 (42%) have been
recalled at least once; max `recalled_count = 9`.

### Semantic prototypes and edges

42 prototypes (21 fine, 21 coarse). Fine and coarse `support_count` are identical (avg 795,
max 3894). 612 edges across 42 nodes (~14.6 per node). Edge weight components:
- `w_similarity` avg 0.417
- `w_coactivation` avg 0.412
- `w_transition` avg **0.036** — near zero

### Worker runs

184 runs, all successful. Totals: schemas_created=2, schemas_reinforced=5298. Average duration
962 ms, but most runs show 0 ms (`ended_ts - started_ts` resolution is 1 s).

### Feedback

44 feedback events: 40 useful (91%), 2 partially_useful, 1 irrelevant, 1 missing. Positive signal
quality throughout.

---

## Findings

### Finding 1 — Scope double-prefix was a SQL display artifact (no bug)

**Initial observation:** session rows appeared as `project:project:slowave` when scope columns were
concatenated.

**Cause:** The `sessions` table stores `scope_kind="project"` and `scope_id="project:slowave"` (the
full canonical string). The display query `scope_kind || ':' || scope_id` doubled the prefix
artificially. `normalize_scope()` in `core/scope.py` correctly passes the full `kind:value` string
through unchanged.

**Status:** Not a bug.

---

### Finding 2 — "26 open sessions" was a wrong predicate (no bug)

**Initial observation:** 26 sessions had `outcome IS NULL`, suggesting the idle reaper was not
closing them.

**Cause:** `session_reaper.py` closes sessions by calling `eng.session_end(sid, consolidate=False)`
without an `outcome` argument. `raw_log.end_session` writes `ended_ts=now, outcome=NULL`. These
reaped sessions have `ended_ts NOT NULL` but `outcome NULL`, so they appeared "open" under the
`outcome IS NULL` predicate — but are in fact closed.

Correct breakdown: only **6 truly open sessions** (`ended_ts IS NULL`), 20 reaped without outcome,
48 committed.

**Status:** Not a bug. The idle reaper works correctly.

---

### Finding 3 — Flat episodic salience: real issue

**Observation:** All 121 episodic memories have `salience = 0.01` (the `min_salience` floor).

**Root cause (traced to code):**

`ReplayConfig.sample_size = 256` (`latent/replay_engine.py:19`) exceeds the total episode count of
121. `SalienceEngine.sample_proportional` (`latent/salience.py:53`) therefore always returns all
121 episodes on every replay pass. `replay_once()` then calls `penalize_after_consolidation` on
every sampled episode:

```python
# replay_engine.py:368-370
for eid, _pid in pairs:
    mem = self.episodic.get(eid)
    self.episodic.update_salience(eid, self.salience.penalize_after_consolidation(mem.salience))
```

`penalize_after_consolidation` is `salience * consolidation_penalty` (default 0.5), floored at
`min_salience=0.01`. Starting from 1.0, 7 replay passes halve the salience to ~0.0078, which is
clamped to 0.01. With 184 worker runs (≈ every 5 minutes), every episode has been at the 0.01
floor for most of the system's lifetime.

**Effect:** `sample_proportional` receives uniform weights, so replay samples at random regardless
of episode novelty or importance. The entire salience-based prioritisation mechanism is a no-op.

**Fix directions:**
- Cap `sample_size` to a fraction of the total episode count (e.g. `min(sample_size, count // 2)`).
- Make the consolidation penalty conditional: skip the penalty when `salience <= min_salience * k`
  (e.g. `k=2`) to avoid penalising episodes already at the floor.
- Increase `tau_seconds` so natural exponential decay is slower relative to the consolidation
  penalty cycle.

---

### Finding 4 — Worker not creating new schemas: expected behaviour (no bug)

**Observation:** `worker_runs.schemas_created` total = 2 across 184 runs. `consolidation_debug`
entries show `prompt_text=""` and zero `extracted_claims_json`.

**Root cause:** The empty `prompt_text` and zero `extracted_claims_json` are legacy LLM-path fields.
The current latent (no-LLM) consolidation path always writes them as empty stubs in `_record_debug`
(`core/consolidation.py:287-303`). They are not evidence of failure.

The worker IS consolidating: 5,298 reinforcements across 184 runs (~29 per run). The `Consolidator`
builds a `LatentSchema` per prototype, then searches for an existing schema with cosine ≥ 0.72
(`_best_related_schema`, `consolidation.py:329`). With 110 explicit schemas covering the embedding
space, nearly every prototype finds a match and is reinforced rather than creating a new schema.

The `_episodic_store_ref` attribute (set via `engine.py:225` after construction) is correctly
wired — the consolidation path reaches `latent_builder.build()` successfully.

**Status:** Expected behaviour for a stable, mature schema set. Consolidation is working correctly.

---

### Finding 5 — Low transition weight: real architectural tension

**Observation:** `prototype_edges.w_transition` avg = 0.036 (vs coactivation avg 0.412, similarity
avg 0.417). `TransitionModel` predictive seed is essentially inactive.

**Root cause (traced to code):**

In `replay_once()` (`replay_engine.py:340-347`), transition counts are only accumulated between
**different** prototypes:

```python
for a, b in zip(mems_sorted[:-1], mems_sorted[1:]):
    pa = self.semantic.prototype_for_episode(a.id)
    pb = self.semantic.prototype_for_episode(b.id)
    if pa is None or pb is None or pa == pb:
        continue        # ← most consecutive pairs land here
    transition_counts[(pa, pb)] += 1.0
```

With a focused single-domain corpus (all sessions in `project:slowave`), consecutive episodes
cluster into the same prototypes most of the time. A 50-episode sample shows ~74% same-prototype
pairs (`pa == pb`), which all get discarded. The few cross-prototype transitions that survive
produce very small conditional probabilities after normalisation, stored as near-zero `w_transition`
values.

`TransitionModel._get_successor_prototypes()` (`latent/transition_model.py:132`) queries
`WHERE w_transition > 0`. Most edges pass this filter (avg 0.036 > 0), but the resulting
weighted-average predictions are too diffuse to produce a useful predictive embedding, so the
retrieval pipeline's predictive seed never adds meaningful signal.

**Fix directions:**
- Lower the fine-scale `assignment_threshold` (currently 0.60) to create more distinct fine
  prototypes, reducing same-prototype pair rate.
- Record intra-prototype temporal sequences separately (e.g. track recency within a prototype
  without requiring cross-prototype jumps).
- Apply a minimum `w_transition` threshold in `_get_successor_prototypes` higher than zero to
  avoid noisy low-weight edges polluting predictions.

---

## Summary

| # | Finding | Real issue? |
|---|---|---|
| 1 | Scope double-prefix in display | No — SQL display artifact |
| 2 | 26 open sessions | No — wrong predicate; reaper works |
| 3 | Flat episodic salience (all 0.01) | **Yes** — `sample_size > episode_count` penalises all episodes every run |
| 4 | Worker not creating schemas | No — expected behaviour; consolidation reinforces stable schema set |
| 5 | Low transition weight (avg 0.036) | **Yes** — 74% of episode pairs share a prototype, starving transition signal |

Two actionable issues: **salience floor saturation** (Finding 3) and **transition signal
starvation** (Finding 5). Both are in the latent replay/consolidation loop and can be addressed
independently without touching the symbolic layer.
