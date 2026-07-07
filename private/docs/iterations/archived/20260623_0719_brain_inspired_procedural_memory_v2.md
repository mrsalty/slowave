> **⚠️ REVISED VERSION AVAILABLE:** v2 has an encode() boundary violation (calls encode/cosine inside the embedding-free `procedural.py`). See [`20260623_0719_brain_inspired_procedural_memory_v3.md`](./20260623_0719_brain_inspired_procedural_memory_v3.md) for the boundary-hardened v3. Key changes: (1) all embedding work moved to `procedural_enforcement.py`/`procedural_enrichment.py`; (2) §3 example replaced with realistic Option-B content; (3) `task_complete` removed from scorer; (4) weak step ordering documented.

# Brain-Inspired Procedural Memory v2: Revised Plan

**Date:** 2026-06-23  
**Status:** Design — superseded by v3  
**Previous documents:** `20260622_procedural_memory_redesign.md` (auto-detection), `20260623_0719_brain_inspired_procedural_memory.md` (v1 of this plan)  
**Review source:** Opus LLM code-level review of v1 against the full repo

---

## 0. Review Feedback & What Changed from v1

Opus reviewed v1 against the full codebase and found three critical issues:

### 1. The event stream is too sparse for subsequence mining (v1 \u00a72-\u00a73)

v1's central premise was that `raw_events` contain a rich action trace that can be mined for subsequences. The actual per-session event stream under the cognitive-cycle API is:

```
slowave_activate    \u2192 context_query (the task text)            \u2014 tools.py:279
slowave_remember    \u2192 remember:{type} events (1\u20135 per session)  \u2014 engine.py:444
slowave_commit      \u2192 task_complete (\"outcome=X\")             \u2014 tools.py:528
slowave_recall      \u2192 no event
slowave_reinforce   \u2192 no event
```

A typical session has 3\u20137 events: `[context_query, remember:decision, remember:fact, task_complete]`. This is not the fine-grained `input1\u2192input2\u2192input3\u2192outcome` sequence that basal-ganglia subsequence mining requires. The CLAUDE.md discourages logging ephemeral state, which actively works against trace richness.

**Resolution:** Two concrete options, both should be evaluated before Tier 2 begins:
- **Option A (enrich capture):** Add a lightweight `event_append` call after significant agent actions (tool calls, file edits). The agent already calls `slowave_remember` for durable facts; extend this to log action traces as `remember:action` events. This doesn't require a new MCP tool \u2014 just guidance in the system prompt.
- **Option B (pivot the miner):** Abandon raw_events mining. Instead, evolve the existing `promote_candidates_from_feedback()` to extract richer steps from the sessions that produced those feedback events. This is simpler and reuses proven infrastructure.

**Recommendation: Option B first, Option A as enhancement.** The existing miner already works; fixing its placeholder steps gives the highest ROI.

### 2. `promote_candidates_from_feedback()` already exists and does ~70% of Tier 2

`ProceduralMemoryStore.promote_candidates_from_feedback()` (procedural.py:467, wired at engine.py:669):
- Groups `context_feedback_events` by `(goal, task_type)`
- Applies `replay_min_group_size` and `candidate_min_distinct_contexts` thresholds
- Creates candidate procedures \u2014 but with **generic placeholder steps** like `"Reuse the memory cluster that was useful before: [ids]"`

This is a simpler, working acquisition mechanism. The only thing it lacks is **meaningful step content**. v1 proposed building a parallel subsequence miner \u2014 that's unnecessary when the existing miner just needs step enrichment.

**Resolution:** Frame Tier 2 as an evolution of `promote_candidates_from_feedback()`, not a replacement. The enhancement: for each qualifying feedback group, retrieve the `remember:*` events from the associated sessions and extract their content as procedure steps using embedding-based deduplication.

### 3. Goal/outcome are partially captured already

v1 proposed new `sessions.goal` and `sessions.outcome` columns as if starting from scratch. But `goal` already flows into `context_recall_events.goal` (schema.sql:243) and `context_feedback_events.goal`. `outcome` is logged as a `task_complete` raw event (tools.py:528). The existing miner (`promote_candidates_from_feedback()`) already uses these fields.

**Resolution:** The new columns on `sessions` are still useful (single source of truth, cheaper query), but the doc must reconcile with data already in flight. The existing miner continues to use recall/feedback tables; the new enforcement tracker can use `sessions.goal` for its own correlation.

---

## 1. Core Thesis (unchanged from v1)

Procedural memory in the brain is the **crystallization of repeated, successful action sequences** \u2014 the basal ganglia records `input1 \u2192 input2 \u2192 input3 \u2192 outcome(success) \u2192 store procedure`. The feedback (dopamine reward) is the trigger for encoding.

Slowave already has the plumbing:
- Sessions have ordered event streams
- Sessions have goals (context)
- Sessions have outcomes (dopamine signal)
- Replay engine does offline consolidation
- `ProceduralMemoryStore` has `candidate \u2192 active \u2192 deprecated` lifecycle
- `apply_feedback()` reinforces/suppresses based on success/failure
- `promote_candidates_from_feedback()` already does implicit acquisition from feedback events

The missing pieces:
- **Tier 1:** Detecting when a session followed an existing procedure (enforcement tracking)
- **Tier 2:** Replacing generic placeholder steps with meaningful action descriptions (evolve existing miner)

---

## 2. Tier 1: Enforcement Tracking (revised)

### Revised: Acknowledge Event Sparsity

Under current usage, a session has 3\u20137 events. The `remember:*` events are the most semantically rich \u2014 they encode the agent's key actions and decisions. Coverage scoring should focus on matching procedure steps against `remember:*` event content, not the full event stream.

### Mechanism: Step-Coverage Scoring

```python
def compute_step_coverage(
    procedure_steps: list[str],
    session_events: list[RawEvent],
    match_threshold: float = 0.65,
) -> float:
    """
    Match procedure steps against session events using cosine similarity.
    Only scores against remember:* and task_complete events (skip context_query).
    Returns fraction of procedure steps that have at least one matching event.
    """
    relevant = [e for e in session_events 
                if e.type.startswith("remember:") or e.type == "task_complete"]
    if not relevant:
        return 0.0
    
    step_embs = [encode(step) for step in procedure_steps]
    matches = 0
    for step_emb in step_embs:
        scores = [cosine(step_emb, e.embedding) for e in relevant if e.embedding is not None]
        if scores and max(scores) >= match_threshold:
            matches += 1
    return matches / len(procedure_steps)
```

Simplification from v1: dropped the LCS order check. With 3\u20137 events, order validation is noise \u2014 just check presence.

### Feedback Application

- `coverage >= 0.5` AND `outcome == success` \u2192 `apply_feedback(useful)`
- `coverage >= 0.5` AND `outcome == failure` \u2192 `apply_feedback(wrong)`
- `coverage < 0.5` \u2192 no signal (too sparse to judge)

Note: threshold lowered from 0.7 to 0.5 because the event stream is sparse. A 2-step procedure where only 1 step is matched = 0.5 coverage \u2014 partial but still signal.

### When Coverage Will Be Too Low

With sparse events, `coverage < 0.5` will be common. This is not a failure \u2014 it correctly means "session too sparse to determine procedure adherence." The system degrades gracefully: no signal means no feedback, which means procedures are neither reinforced nor penalized. This is the right behavior for sparse data.

### Schema

```sql
ALTER TABLE sessions ADD COLUMN goal TEXT;
ALTER TABLE sessions ADD COLUMN outcome TEXT;
```

These columns are the canonical source of truth. The enforcement tracker reads `sessions.goal` + `raw_events` for the session. The existing `promote_candidates_from_feedback()` continues to read `context_feedback_events.goal` (no change needed).

---

## 3. Tier 2: Evolve the Existing Miner (replaces v1 \u00a73)

### v1 vs v2

| Aspect | v1 (Subsequence Mining) | v2 (Evolve Existing Miner) |
|---|---|---|
| Data source | raw_events across all sessions | context_feedback_events (already filtered for success) |
| Grouping key | Goal embedding cluster | (goal, task_type) string \u2014 already working |
| Pattern detection | Frequent subsequence over event-type labels | Extract step content from remember:* events in associated sessions |
| Step content | Cluster representative text | Deduplicated remember:* content across sessions |
| Cold start | Needs 3+ sessions with rich events | Already works with existing feedback data |
| Complexity | High (clustering + subsequence mining) | Low (add step extraction to existing function) |

### Current State of `promote_candidates_from_feedback()`

The function (procedural.py:467) produces steps like:
```python
steps = [
    "Reuse the memory cluster that was useful before: sch_12, sch_34, sch_56.",
    "Preserve recurring requirements: testing, authentication.",
    "Apply this workflow for goal 'fix auth bug' and task type 'debugging'."
]
```

These are generic references to memory IDs and requirements. They don't describe *what actions to take*.

### Proposed Evolution: Step Content from Session Events

After a feedback group passes thresholds, enrich the steps by pulling in the actual `remember:*` events from the associated sessions:

```python
def promote_candidates_from_feedback(self) -> dict[str, Any]:
    # ... existing grouping logic (unchanged) ...
    
    for (goal, task_type), group in groups.items():
        if len(group) < self.cfg.replay_min_group_size:
            continue
        # ... existing distinct_contexts and dedup checks ...
        
        # NEW: Extract step content from the sessions that produced these feedback events
        session_ids = list({r["session_id"] for r in group if r["session_id"]})
        step_candidates = _extract_remember_content(self.db, session_ids)
        
        # Deduplicate semantically equivalent steps across sessions
        steps = _deduplicate_steps(step_candidates, threshold=0.7)
        
        # Fall back to existing generic steps if extraction yields nothing
        if not steps:
            steps = _legacy_generic_steps(used_memory_ids, requirements, goal, task_type)
        
        # ... rest unchanged ...

def _extract_remember_content(db, session_ids: list[str]) -> list[str]:
    """Get remember:* event content from the given sessions, ordered by recency."""
    rows = db.connect().execute(
        """SELECT content FROM raw_events 
           WHERE session_id IN ({})
             AND type LIKE 'remember:%'
           ORDER BY ts, id""".format(",".join(["?"] * len(session_ids))),
        session_ids
    ).fetchall()
    return [r["content"] for r in rows]

def _deduplicate_steps(candidates: list[str], threshold: float = 0.7) -> list[str]:
    """Deduplicate semantically equivalent step candidates via embedding cosine.
    Returns the most representative candidate from each cluster, preserving order."""
    if len(candidates) <= 1:
        return candidates
    embs = [encode(c) for c in candidates]
    seen_clusters = []
    result = []
    for i, emb in enumerate(embs):
        matched = False
        for cluster_idx, cluster_centroid in seen_clusters:
            if cosine(emb, cluster_centroid) >= threshold:
                matched = True
                break
        if not matched:
            seen_clusters.append((len(result), emb))
            result.append(candidates[i])
    return result
```

### What This Achieves

- **Zero new infrastructure.** Reuses existing `context_feedback_events`, `raw_events`, and the promotion loop.
- **Meaningful steps.** Instead of "Reuse memory cluster sch_12", you get "ran pytest -k test_auth, all 23 tests passed" and "fixed null pointer in auth.py:42".
- **Cross-session consensus.** `_deduplicate_steps` merges semantically equivalent actions from different sessions ("ran tests" + "ran pytest" \u2192 one step).
- **Graceful fallback.** If sessions have too few remember events, the generic placeholder steps still work.

---

## 4. Dual-Pathway Model (unchanged)

| Pathway | Brain Analogue | Slowave Mechanism |
|---|---|---|
| **Implicit** (experience) | Basal ganglia / procedural learning | `promote_candidates_from_feedback()` (evolved) |
| **Explicit** (declared) | Prefrontal cortex declarative override | `slowave_remember(type="procedure")` or latent classifier |

Both produce `status=candidate` procedures validated by the same feedback loop.

---

## 5. Full Procedure Lifecycle (unchanged)

```
BIRTH
\u251c\u2500\u2500 Explicit: remember("when X, do Y then Z") \u2192 classifier \u2192 procedure (conf=0.6)
\u2514\u2500\u2500 Implicit: promote_candidates_from_feedback() finds 3+ successes \u2192 procedure (conf=0.5\u20130.65)

VALIDATION (Tier 1 enforcement tracking at each session_end)
\u2502  coverage >= 0.5 + success \u2192 reinforce
\u2502  coverage >= 0.5 + failure \u2192 penalize
\u2502  coverage < 0.5 \u2192 no signal

PROMOTION
\u2502  success_count >= 3 AND confidence >= 0.7 \u2192 active

DEMOTION / SUPERSESSION
\u2502  confidence < 0.55 \u2192 back to candidate
\u2514\u2500\u2500 confidence < 0.35 OR failures >= 3 \u2192 deprecated
```

---

## 6. Implementation: Files and Changes (revised)

### New Files

| File | Purpose |
|---|---|
| `slowave/core/procedural_enforcement.py` | `compute_step_coverage()`, session-end adherence tracking |
| `slowave/latent/classifier.py` | `MemoryTypeClassifier` (from 20260622 doc) |

### Removed from v1

| File | Reason |
|---|---|
| `slowave/core/procedural_extraction.py` | Replaced by evolving `promote_candidates_from_feedback()` in procedural.py |

### Modified Files

| File | Change |
|---|---|
| `slowave/core/engine.py` | Store `goal` in `session_start`; store `outcome` in `session_end`; call enforcement tracker; wire classifier in `remember()` |
| `slowave/core/procedural.py` | Evolve `promote_candidates_from_feedback()` with `_extract_remember_content()` and `_deduplicate_steps()`; add `superseded_by_id` column usage |
| `slowave/mcp/tools.py` | Pass `goal` through `session_start`; pass `outcome` to `session_end`; make `type` optional on `remember` |
| `slowave/core/services/consolidation.py` | Call `procedures.promote_candidates_from_feedback()` during consolidation (it already exists but is wired only to engine.py) |
| `slowave/storage/schema.sql` | `sessions.goal`, `sessions.outcome`, `procedural_memories.source`, `procedural_memories.superseded_by_id` |
| `slowave/storage/sqlite_db.py` | Migration entries for new columns |

### Data Flow (revised)

```
activate(goal="fix auth bug")
  \u2192 session_start(goal=...)              \u2190 NEW: goal stored on sessions row
  \u2192 context_brief(goal=...)              \u2190 existing: goal in context_recall_events

[agent works]
  \u2192 remember("ran pytest")                \u2192 raw_events: remember:decision
  \u2192 remember("fixed auth.py:42")          \u2192 raw_events: remember:fact
  \u2192 reinforce(feedback=useful)            \u2192 context_feedback_events (goal persisted)

commit(outcome="success")
  \u2192 session_end(outcome=...)             \u2190 NEW: outcome stored
     \u2192 form_episodes                      \u2190 existing
     \u2192 procedural_enforcement.track()    \u2190 NEW (Tier 1)

[later, in worker]
  \u2192 replay_once()                         \u2190 existing
  \u2192 consolidate()                          \u2190 existing
  \u2192 promote_candidates_from_feedback()    \u2190 existing (enhanced with step extraction)
```

---

## 7. Brain-Inspired Fidelity Review (revised)

| Brain Property | Implementation | Fidelity | Notes |
|---|---|---|---|
| Implicit acquisition | Evolved `promote_candidates_from_feedback()` | **High** \u2705 | Feedback-gated, not event-mined. Matches the dopamine model better than subsequence mining. |
| Sequence chunking | Step extraction from remember events | **Low-Medium** \u26a0\ufe0f | No hierarchy; steps are declarative snapshots, not motor sequences. Richness depends on Option A (enriched capture). |
| Context gating | `goal` + `trigger_pattern` filtering | **High** \u2705 | |
| Dopamine learning | `apply_feedback()` with success_alpha/failure_beta | **High** \u2705 | |
| Retroactive interference | Supersession via `superseded_by_id` | **High** \u2705 | |
| Gradual automation | Candidate (0.5) \u2192 Active (0.7) | **High** \u2705 | |
| Trace richness | Sparse remember events | **Gap** \ud83d\udd34 | Without enriched capture, steps are from remember:* only \u2014 declarative, not motor. This is the load-bearing fidelity risk. |

---

## 8. Performance Measurement (unchanged from v1)

### Level 1: Mechanical Correctness

| Test | What it verifies |
|---|---|
| `test_coverage_exact_match` | Returns 1.0 for exact match |
| `test_coverage_partial_match` | Returns correct fraction for sparse events |
| `test_coverage_no_match` | Returns 0.0 for unrelated events |
| `test_feedback_routing` | Coverage >= 0.5 + success \u2192 useful feedback |
| `test_feedback_no_signal` | Coverage < 0.5 \u2192 no feedback |
| `test_candidate_promotion` | 3+ successes \u2192 active |
| `test_extract_remember_content` | Correctly pulls remember events from session IDs |
| `test_deduplicate_steps` | Merges semantically equivalent steps |
| `test_step_enrichment` | Evolved miner produces meaningful steps from real sessions |
| `test_supersession_chain` | P2 supersedes P1 |
| `test_cold_start` | Fresh DB \u2192 fallback to schemas |

### Level 2: Acquisition Quality

Synthetic sessions with known ground truth:
- 10 seed procedures, N sessions each (N=3, 5, 10)
- Measure: do enriched steps match ground-truth actions?

### Level 3: Downstream Utility

Dashboard metrics: procedure activation rate, follow rate, success rate delta.

---

## 9. Open Questions

1. **Enriched capture (Option A).** Should the agent system prompt be updated to log `remember:action` events for significant actions? This would enrich both enforcement tracking and step extraction. Cost: more raw_events rows. Benefit: richer trace for both tiers.
2. **Goal clustering.** Cluster by goal embedding similarity rather than exact string match? The existing miner uses exact string, which is fragile to paraphrasing.
3. **session_procedure_adherence table.** Is a dedicated table needed, or should we reuse `procedural_memory_evidence` (schema.sql:369) which already stores per-procedure outcome/feedback per session?
4. **Coverage threshold calibration.** The 0.5 threshold is a starting point. Needs empirical calibration against real session data.

---

## 10. Relationship to 20260622 Redesign

| Source | Mechanism | When it fires |
|---|---|---|
| `slowave_remember(content)` | Latent classifier (20260622) | At remember time |
| Feedback events + remember content | Evolved `promote_candidates_from_feedback()` (this doc) | During consolidation |
| `slowave_remember_procedure(steps)` | Explicit (to be deprecated) | User declares |

---

## 11. Implementation Order (revised)

1. **Resolve event granularity.** Before coding either tier, decide: enrich capture (Option A) or accept sparse events (Option B default). If Option A, update system prompt guidance first.
2. **Schema migration.** Add `sessions.goal`, `sessions.outcome`, `procedural_memories.source`, `procedural_memories.superseded_by_id`. These are needed by everything else.
3. **Tier 1: Enforcement tracking.** `procedural_enforcement.py` + hook in `session_end`. Smallest surface, highest leverage, validates the feedback loop.
4. **Evolve the existing miner.** Replace generic placeholder steps in `promote_candidates_from_feedback()` with `_extract_remember_content()` + `_deduplicate_steps()`. Builds on proven infrastructure.
5. **20260622 classifier.** Auto-routing `remember` calls. Depends on multilingual encoder upgrade (20260622 gap #8).
6. **Deprecate `remember_procedure`.** Only after all three acquisition paths (classifier, evolved miner, explicit) are working.
