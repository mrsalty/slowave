# Slowave Synthetic Long-Session Evaluation Review

## Executive Summary

I ran Slowave locally in the sandbox and executed a synthetic multi-session evaluation using a deterministic semantic stub encoder, so no external model download or LLM calls were needed.

I also ran a targeted unit test subset:

```text
36 passed in 17.46s
```

Tested files:

```text
tests/unit/test_engine_recall.py
tests/unit/test_engine_consolidate.py
tests/unit/test_remember_session.py
tests/unit/test_procedural_memory.py
```

Generated synthetic run artifact:

```text
/mnt/data/slowave_synthetic_run/report.json
```

---

## What I Tested

I created a fresh local Slowave DB and simulated:

```text
project:slowave
project:payments
global/profile memory
```

Then I tested:

- explicit `remember`
- cross-session recall
- session event ingestion
- synchronous consolidation
- schema creation
- FAISS index refresh
- context brief / working-memory gating
- cross-scope behavior
- contradiction / supersession behavior
- feedback learning path
- procedural memory creation and retrieval
- decay dry-run
- raw evidence tracing

Final stats from the synthetic run:

```json
{
  "episodes": 24,
  "prototypes": 22,
  "schemas": 12,
  "procedures": 1,
  "edges": 265
}
```

Basic recall checks:

```text
7 / 7 passed
```

Queries included:

```text
What database does Slowave use?
How does Slowave retrieve vectors locally?
What should setup do before modifying configs?
What benchmark language should be used?
What file is too large in the dashboard?
What queues does the payments project use?
What does the user prefer in answers?
```

---

## High-Level Result

Slowave performs well on **explicit memory + scoped recall + working-memory injection**.

The strongest features are real:

1. **Explicit memories become immediately recallable**
2. **Evidence is traceable back to raw events**
3. **Cross-session continuity works**
4. **Context brief ranking is useful and inspectable**
5. **Scope helps, but does not fully isolate**
6. **Salience reinforcement works**
7. **Consolidation produces prototypes, schemas, and graph edges**
8. **The API surface is usable for agent integration**

The weaker features are also clear:

1. **Contradiction/supersession is not reliable enough yet**
2. **Scope leakage can still occur**
3. **Procedural memory creation works, but retrieval is too strict / brittle**
4. **Feedback reduces confidence/salience but does not strongly suppress wrong memories**
5. **Consolidated session summaries can become too broad**
6. **Repeated explicit memories appear duplicated in episode recall**
7. **Recall ranking can over-prioritize semantically nearby but wrong-scope facts**

---

## Strong Feature 1: Explicit Remember Works Very Well

I inserted memories such as:

```text
Slowave primary database is SQLite, not Postgres.
Slowave uses FAISS for local vector retrieval.
Setup must create backups before modifying Claude, Cline, Cursor, or Windsurf config files.
For public release, keep benchmark claims directional and cite scorer differences.
```

All were immediately recallable.

Example query:

```text
How does Slowave retrieve vectors locally?
```

Top schema:

```text
Slowave uses FAISS for local vector retrieval.
```

This path is solid and should remain the main advertised value.

Verdict:

```text
Strong.
```

---

## Strong Feature 2: Evidence Tracing Works

With `evidence=True`, Slowave returned raw events linked to recalled schemas/episodes.

Example result had:

```text
raw_events: 13
```

This is important because it gives Slowave a credibility advantage over vague “memory” systems. You can show not only “what I remember,” but also “where this came from.”

This should become a major product point:

```text
Every memory can be traced to supporting evidence.
```

Verdict:

```text
Strong and marketable.
```

---

## Strong Feature 3: Context Brief / Working-Memory Gating Is Useful

For `project:slowave`, context brief selected:

```text
Slowave must not call an LLM during ingest, consolidation, or recall.
Setup must create backups before modifying Claude, Cline, Cursor, or Windsurf config files.
For public release, keep benchmark claims directional and cite scorer differences.
Slowave primary database is SQLite, not Postgres.
Slowave uses FAISS for local vector retrieval.
The dashboard is useful but dashboard/app.py is too large and should be split later.
```

This is exactly the kind of injected context a coding assistant would benefit from.

Even better: the activation reasons are inspectable:

```text
cosine=0.37,cue_overlap=0.60,salience=0.08,constraint,utility=0.23,profile,explicit,scope_match=project:slowave
```

That is good. It makes the system debuggable.

Verdict:

```text
Very strong.
```

---

## Strong Feature 4: Scoped Context Mostly Works

For `project:payments`, context brief selected:

```text
The Payments project uses RabbitMQ queues for enrichment requests.
Payments project stores bookkeeping data in PostgreSQL.
```

So the project boundary does help.

This is important for your core use case: one memory store across multiple coding agents and projects.

Verdict:

```text
Strong, but needs stricter isolation mode.
```

---

## Weak Feature 1: Scope Leakage Still Happens

In the `project:payments` context brief, one Slowave-specific memory also appeared:

```text
Slowave primary database is SQLite, not Postgres.
```

Reason included:

```text
scope_mismatch
```

This means the gate admitted it despite recognizing the mismatch.

That may be acceptable in “broad mode,” but for coding assistants it can be dangerous. If I ask about a customer project, I usually do not want unrelated Slowave facts leaking in.

Recommended fix:

Add context modes:

```text
strict_scope
default
broad
debug
```

Behavior:

```text
strict_scope:
  only current scope + global profile memories

default:
  current scope + profile + very high-confidence cross-scope memories

broad:
  allow cross-scope transfer

debug:
  show everything with reasons
```

For MCP `activate`, I would default to stricter behavior for project scopes.

---

## Weak Feature 2: Contradiction/Supersession Is Not Strong Enough

I inserted:

```text
Slowave primary database is SQLite, not Postgres.
```

Then later inserted:

```text
Slowave primary database has moved to DuckDB for local storage.
```

Recall for:

```text
What is Slowave primary database now?
```

returned both, with the old SQLite memory ranked first:

```text
Slowave primary database is SQLite, not Postgres.
Slowave primary database has moved to DuckDB for local storage.
```

Both remained:

```text
status: active
```

So explicit contradiction handling did not supersede the older fact in this synthetic test.

This is a major area to improve because temporal validity is one of Slowave’s central claims.

Recommended fix:

For explicit `remember`, add a stronger deterministic supersession path:

```text
same scope
+ same entity/topic
+ conflicting value
+ newer timestamp
= old schema marked superseded or needs_review
```

For example, extract lightweight slots without an LLM:

```text
subject/entity: Slowave primary database
attribute: database/storage_backend
old value: SQLite
new value: DuckDB
```

This does not require full NLP. You can start with pattern-based attribute extraction for common forms:

```text
X uses Y
X is Y
X moved to Y
X switched from Y to Z
X no longer uses Y
X now uses Y
```

The current cosine-threshold approach is not enough.

---

## Weak Feature 3: Feedback Does Not Suppress Wrong Memory Aggressively Enough

I marked the SQLite memory as wrong:

```text
feedback = wrong
outcome = failed
wrong_memory_ids = ["sch_1"]
```

Slowave applied feedback:

```json
{
  "marked_review": ["sch_1"],
  "salience_delta": -0.25,
  "confidence_delta": -0.3
}
```

After feedback, the memory changed to:

```text
salience: 1.40
confidence: 0.70
status: active
```

But it still appeared first in recall.

This means feedback works mechanically, but the retrieval policy does not punish wrong/stale memories strongly enough.

Recommended fix:

For `wrong` feedback:

```text
confidence <= 0.7 should not be enough
```

I would do one of these:

Option A:

```text
wrong + failed => status = needs_review
needs_review => lower ranking unless explicitly requested
```

Option B:

```text
wrong + failed => salience multiplier 0.2 for retrieval
```

Option C:

```text
wrong + failed + newer conflicting schema exists => superseded
```

For a memory system, “wrong” feedback must have immediate visible effect.

---

## Weak Feature 4: Procedural Memory Retrieval Failed in My Synthetic Run

I created a procedure:

```text
Goal: Prepare Slowave public release
Task type: release_review
Requirements: clean repo, run tests
Steps:
1. Remove generated artifacts and pyc files.
2. Fix package version source of truth.
3. Run fresh-venv install and pytest.
4. Review benchmark claims and limitations.
5. Record release notes and migration warnings.
```

Procedure count became:

```text
procedures: 1
```

But retrieval returned:

```text
[]
```

This happened despite querying:

```text
How should I prepare the Slowave release?
```

with matching scope, goal, task type, and requirement.

Likely cause: score threshold / text overlap / requirement mismatch penalty is too strict or the lexical matching is brittle.

This is important because procedural memory is one of the coolest Slowave features. If it fails on a clean synthetic example, it needs attention before public emphasis.

Recommended fix:

Add a debug command:

```bash
slowave procedure debug "How should I prepare the Slowave release?"
```

It should show:

```text
procedure_id
score
threshold
goal_match
task_type_match
requirements_match
trigger_match
scope_affinity
confidence
reason rejected
```

Also consider storing trigger terms automatically from goal + task_type + steps, not only from `trigger_pattern`.

For the created procedure, trigger terms should include:

```text
slowave
release
public
clean
repo
tests
pytest
benchmark
claims
```

---

## Weak Feature 5: Consolidated Schemas Can Become Too Broad

After one session with four notes, consolidation created schemas like:

```text
We reviewed slowave setup and decided dry-run must show exact modified files.
We found pyproject version is 0.4.9 while __init__ version was stale.
```

and another broader one:

```text
We reviewed slowave setup and decided dry-run must show exact modified files.
We found pyproject version is 0.4.9 while __init__ version was stale.
We agreed benchmark reproduction should produce summary.json and summary.md artifacts.
We discussed not exposing too much brain jargon in README.
```

This is useful as an episode summary, but risky as a semantic schema. It mixes multiple independent facts.

Recommended fix:

Distinguish more clearly between:

```text
episodic_summary
semantic_schema
task_note
decision
```

A broad multi-fact session summary should not compete equally with precise schemas like:

```text
Setup must create backups before modifying config files.
```

You already have memory layers/facets; use them more aggressively during retrieval.

---

## Weak Feature 6: Duplicate Episode Recall

For explicit memories, recall often returned duplicate episode text:

```text
[2026-06-10] Remember: Slowave uses FAISS for local vector retrieval.
[2026-06-10] Remember: Slowave uses FAISS for local vector retrieval.
```

This is probably due to explicit `remember()` creating event-backed episodes and retrieval returning similar stored traces.

This is not catastrophic, but it wastes context budget.

Recommended fix:

Add episode deduplication before returning `episode_texts`:

```text
normalize content_text
dedupe exact / near-exact
prefer highest salience or newest
```

For working memory injection, duplication should be almost impossible.

---

## What I Would Change in the Evaluation Harness

The synthetic test I ran is useful but still small. I would formalize it into a repo benchmark:

```text
tests/eval/test_synthetic_long_session.py
```

or:

```text
benchmarks/synthetic_long_session.py
```

It should produce metrics like:

```text
explicit_recall@k
scope_precision@k
profile_injection@k
temporal_update_accuracy
wrong_feedback_suppression
procedural_recall@k
context_token_budget
duplicate_rate
evidence_coverage
```

I would add specific expected failures too. For example:

```text
test_new_fact_supersedes_old_fact
test_wrong_feedback_removes_memory_from_top_3
test_strict_scope_excludes_other_project
test_procedure_retrieved_by_goal_and_requirement
test_context_brief_has_no_duplicate_items
```

Those tests would directly align with Slowave’s public claims.

---

## Current Slowave Scorecard After Local Run

```text
Explicit remember/recall              8.5 / 10
Evidence traceability                 8.0 / 10
Cross-session continuity              8.0 / 10
Working-memory context brief          8.0 / 10
Scope handling                        6.5 / 10
Consolidation                         6.5 / 10
Contradiction / supersession          4.5 / 10
Feedback learning                     5.5 / 10
Procedural memory retrieval           4.5 / 10
Release-readiness                     6.0 / 10
```

Overall:

```text
Core memory substrate: strong.
Adaptive/cognitive claims: promising but uneven.
Public beta readiness: not yet.
Controlled alpha readiness: yes.
```

---

## Most Important Next Fixes

### 1. Add Strict Scope Mode

This directly improves the coding-agent use case.

```text
project context should not leak unrelated project facts unless explicitly broad/debug mode.
```

### 2. Make Wrong/Stale Feedback Visibly Affect Ranking

A memory marked wrong should not remain top-ranked.

### 3. Implement Deterministic Supersession for Explicit Memories

Especially for:

```text
X now uses Y
X moved from A to B
X no longer uses A
Prefer Y instead of X
```

### 4. Fix Procedural Retrieval

Procedural memory is too important to be brittle.

### 5. Deduplicate Episode Recall

Reduce repeated identical memories in returned context.

### 6. Separate Broad Session Summaries from Precise Semantic Schemas

Broad summaries should be evidence/context, not top semantic facts.

---

## Bottom Line

Slowave’s **core value proposition is real**. It already works well as a local shared memory substrate for AI tools.

But the features that make it sound “cognitive” — contradiction handling, feedback adaptation, procedural retrieval, temporal validity — are currently the weakest parts and need targeted hardening before leaning too heavily on those claims publicly.
