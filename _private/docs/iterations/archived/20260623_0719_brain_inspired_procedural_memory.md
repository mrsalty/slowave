> **⚠️ REVISED VERSION AVAILABLE:** This v1 document has known issues identified during code review. See [`20260623_0719_brain_inspired_procedural_memory_v2.md`](./20260623_0719_brain_inspired_procedural_memory_v2.md) for the revised plan. Key changes: (1) event stream is too sparse for subsequence mining — v2 pivots to evolving the existing `promote_candidates_from_feedback()`; (2) enforcement tracking thresholds and mechanism adjusted for sparse events.

# Brain-Inspired Procedural Memory: Enforcement, Extraction, and Implementation Plan

**Date:** 2026-06-23  
**Status:** Design — superseded by v2  
**Previous document:** `20260622_procedural_memory_redesign.md`  
**Topic:** Brain-inspired procedural memory acquisition from action sequences with outcome-gated storage; step-coverage enforcement tracking; high-level implementation plan; performance measurement strategy

---

## 1. Core Thesis

Procedural memory in the brain is NOT a predefined list of steps that someone explicitly declares. It is the **crystallization of repeated, successful action sequences** — the basal ganglia records `input1 → input2 → input3 → outcome(success) → store procedure`. The feedback (dopamine reward) is the trigger for encoding, not the content classification.

Slowave already has the plumbing for this:
- Sessions have ordered event streams (actions)
- Sessions have goals (context)
- Sessions have outcomes (dopamine signal)
- The replay engine does offline consolidation
- `ProceduralMemoryStore` has `candidate → active → deprecated` lifecycle
- `apply_feedback()` already reinforces/suppresses based on success/failure

The missing piece: detecting when a session follows a procedure, and mining frequent action patterns across successful sessions.

---

## 2. Enforcement Tracking

### The Mechanism: Step-Coverage Scoring

A session has a `goal`, an ordered event stream (via `event_append`), and an `outcome` (from commit). A procedure has `goal`, `procedure_steps`, and `trigger_pattern`.

At session end, for each active procedure matching the session goal:

1. Embed each procedure step (once, stored)
2. For each session event (already embedded), compute cosine similarity to each step
3. Find best event match per step
4. If `order_matters=True`, validate matches preserve order via longest common subsequence
5. Coverage = matched_steps / total_steps

Then feedback is applied:
- `coverage >= 0.7` AND `outcome == success` → `apply_feedback(useful)`
- `coverage >= 0.7` AND `outcome == failure` → `apply_feedback(wrong)`
- `coverage < 0.3` → no signal (procedure wasn't followed)
- `0.3 <= coverage < 0.7` → `apply_feedback(partially_useful)`

### Key Insight: Event Content IS the Action Trace

The agent already records its actions via `slowave_remember` calls (`"ran pytest, all passed"`, `"decided to use SQLite"`). These content strings have embeddings that semantically match procedure steps. Zero new encoding is needed — reuse the existing embeddings in `raw_events`.

### Schema Requirement

Goal and outcome must be stored on the session to correlate at `session_end`:

```sql
ALTER TABLE sessions ADD COLUMN goal TEXT;
ALTER TABLE sessions ADD COLUMN outcome TEXT;
```

`slowave_activate` passes `goal` to `session_start`; `slowave_commit` passes `outcome` to `session_end`.

---

## 3. Sequence Pattern Extraction

### Algorithm: Frequent Subsequence Mining

Runs during consolidation (worker), after replay:

1. **Group sessions** by `(goal_embedding_cluster, scope)` — semantically similar goals
2. **Filter to successful sessions** (outcome=success) within each group
3. **Cluster events** across sessions by embedding (cosine > 0.7 → same "action type")
4. **Convert each session** to a sequence of action-type labels
5. **Mine frequent subsequences** appearing in ≥N sessions (min_support=3)
6. **Extract best pattern** — highest support × length → procedure spine
7. **Create candidate procedure** with `confidence = support_count / total_sessions`, `source=implicit`

### Boundary Detection: Emergent

Subsequence mining naturally handles variable-length procedures:
- Short patterns (2–3 steps) when that's the consistent spine
- Long patterns (8–10 steps) when data supports them
- No pattern when there's high entropy → nothing to encode

This mirrors the brain: chunking granularity is emergent from the data.

### No LLM Required

- Clustering: embedding cosine similarity (already stored)
- Pattern mining: deterministic frequent episode mining over labels
- Step extraction: representative content from each cluster becomes step text

Brain-only mode preserved. No Ollama, no cloud service.

---

## 4. Dual-Pathway Model

| Pathway | Brain Analogue | Slowave Mechanism |
|---|---|---|
| **Implicit** (experience) | Basal ganglia / procedural learning | Pattern extractor mines from successful sessions |
| **Explicit** (declared) | Prefrontal cortex declarative override | `slowave_remember(type="procedure")` or latent classifier |

Both produce `status=candidate` procedures. The feedback loop validates both identically:
- Followed + success → confidence increases → promotes to active
- Followed + failure → confidence decreases → demotes
- Never followed → stays candidate forever (self-correcting)

Explicit procedures start at `confidence=0.6` (higher than auto-detected 0.5) because the user is telling us something, but they are still subject to the same feedback validation.

---

## 5. Full Procedure Lifecycle

```
BIRTH (two pathways)
│
├── Explicit: remember("when X, do Y then Z") → latent classifier → procedure
│   └── confidence=0.6, status=candidate, source=explicit
│
└── Implicit: pattern extractor finds 3+ successful sessions with same goal
    └── confidence=0.5, status=candidate, source=implicit

VALIDATION (enforcement tracking at each session_end)
│
│  Session with goal=X, outcome=success|failure
│  → coverage_score against all matching procedures
│  → apply_feedback based on coverage + outcome
│  → success_count / failure_count / confidence updated

PROMOTION
│
│  success_count >= 3 AND confidence >= 0.7
│  → status: candidate → active
│  → now fires automatically on activate

DEMOTION / SUPERSESSION
│
│  confidence < 0.55 → active → candidate (re-evaluate)
│  confidence < 0.35 OR failures >= 3 → deprecated
│  New procedure with trigger overlap > 0.6 → supersedes old
```

---

## 6. Implementation: Files and Changes

### New Files

| File | Purpose |
|---|---|
| `slowave/core/procedural_enforcement.py` | `compute_step_coverage()`, session-end adherence tracking |
| `slowave/core/procedural_extraction.py` | Subsequence mining, procedure crystallization |
| `slowave/latent/classifier.py` | `MemoryTypeClassifier`: procedure/fact centroids (from 20260622 doc) |

### Modified Files

| File | Change |
|---|---|
| `slowave/core/engine.py` | Store `goal` in `session_start`; store `outcome` in `session_end`; call enforcement tracker; wire classifier in `remember()` |
| `slowave/mcp/tools.py` | Pass `goal` through `session_start`; pass `outcome` through `commit → session_end`; make `type` optional on `remember` |
| `slowave/core/services/consolidation.py` | Add `ProceduralExtractor.extract_once()` stage after replay |
| `slowave/storage/schema.sql` | `sessions.goal`, `sessions.outcome`, `procedural_memories.source`, `procedural_memories.superseded_by_id`, `session_procedure_adherence` table |
| `slowave/storage/sqlite_db.py` | Migration entries for new columns |

### Data Flow

```
activate(goal="fix auth bug")
  → session_start(goal=...)              ← goal stored in DB
  → context_brief(goal=...)              ← goal used for recall

[agent works — event_append calls]
  → raw_events stream (content + embedding)

commit(outcome="success")
  → session_end(outcome=...)             ← outcome stored
     → form_episodes                      ← existing
     → procedural_enforcement.track()     ← NEW (Tier 1)
        ├─ retrieve active procedures matching goal
        ├─ compute step_coverage(proc.steps, events)
        └─ apply_feedback(proc_id, feedback, outcome)

[later, in worker]
  → replay_once()                         ← existing
  → consolidate()                          ← existing
  → procedural_extraction.extract_once()   ← NEW (Tier 2)
     ├─ group sessions by goal embedding cluster
     ├─ for each cluster, filter successful sessions
     ├─ cluster events across sessions (embedding)
     ├─ mine frequent subsequences
     └─ create candidate procedures
```

---

## 7. Brain-Inspired Fidelity Review

| Brain Property | Implementation | Fidelity |
|---|---|---|
| Implicit acquisition (experience → procedure) | Pattern extractor mines from sessions | **High** ✅ |
| Sequence chunking (actions → chunks) | Subsequence mining | **Medium** ⚠️ — no hierarchy |
| Context gating (fire only in right context) | `goal` + `trigger_pattern` filtering | **High** ✅ |
| Dopamine learning (success/reward → strengthen) | `apply_feedback()` with success_alpha/failure_beta | **High** ✅ |
| Retroactive interference (new habit suppresses old) | Supersession via `superseded_by_id` | **High** ✅ |
| Gradual automation (candidate → automatic) | Candidate (0.5) → Active (0.7) | **High** ✅ |
| Exploration/annealing (vary low-confidence, exploit high) | Not implemented | **Gap** |
| Hierarchical chunking (sub-procedures) | Not implemented | **Gap** |
| Semantic goal clustering (not string equality) | Goal embedding > exact string | **Mitigation suggested** |

Overall: ~70% faithful. Core loop is well-represented. Gaps are incremental, not architectural.

---

## 8. Performance Measurement

### Level 1: Mechanical Correctness (Unit Tests)

| Test | What it verifies |
|---|---|
| `test_coverage_exact_match` | Returns 1.0 for exact match |
| `test_coverage_partial_match` | Returns correct fraction |
| `test_coverage_wrong_order` | Penalizes out-of-order |
| `test_coverage_no_match` | Returns 0.0 for unrelated events |
| `test_feedback_routing` | Coverage >= 0.7 + success → useful feedback |
| `test_feedback_no_signal` | Coverage < 0.3 → no feedback |
| `test_candidate_promotion` | 3+ successes → active |
| `test_supersession_chain` | P2 supersedes P1 |
| `test_cold_start` | Fresh DB → fallback to schemas |

### Level 2: Acquisition Quality (Seeded Benchmark)

Synthetic sessions with known ground-truth procedures:
- 10 seed procedures, N sessions each (N=3, 5, 10)
- 80% follow procedure, 20% noise; 70% success rate
- Metrics: precision, recall, F1, steps Jaccard

### Level 3: Downstream Utility (Real Usage)

Dashboard metrics from `session_procedure_adherence`:
- Procedure activation rate (% of sessions with matching procedure)
- Follow rate (% of matched sessions with coverage >= 0.7)
- Success rate delta (followed vs unfollowed)
- Confidence drift over time

---

## 9. Open Questions

1. **Goal clustering**: Cluster by goal embedding similarity (cosine > 0.85) rather than exact string match?
2. **Event granularity**: Are `slowave_remember` calls sufficient as action traces, or do we need finer-grained events?
3. **Exploration/variation**: Should procedures mutate when variations consistently succeed?
4. **Computation gating**: Should the extractor gate on "N new successful sessions since last run"?

---

## 10. Relationship to 20260622 Redesign

The two documents are **complementary**:

| Source | Mechanism | When it fires |
|---|---|---|
| `slowave_remember(content)` | Latent classifier (20260622) | At remember time — "this looks like a procedure" |
| Session events + outcome | Sequence pattern extractor (this doc) | During consolidation — "this sequence reliably succeeds" |
| `slowave_remember_procedure(steps)` | Explicit (to be deprecated) | User declares a procedure |

All three feed the same `ProceduralMemoryStore` with the same lifecycle.

---

## 11. Recommended Implementation Order

1. **Tier 1 first** — Enforcement tracking (smallest surface, highest leverage, uses only existing data)
2. **Tier 2 second** — Sequence extraction (depends on Tier 1 for validation feedback)
3. **20260622 classifier third** — Auto-routing `remember` calls (can be done independently)
4. **Deprecate `remember_procedure` last** — Only after all three acquisition paths are working
