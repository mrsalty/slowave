# Strict Slowave client/memory contract

**Date:** 2026-07-06  
**Status:** Proposal  
**Audience:** Slowave core, MCP/CLI client integration, and lifecycle instruction authors

---

## Executive summary

This document defines a stricter client/Slowave contract for the five-verb lifecycle:

```text
activate → remember → recall → reinforce → commit
```

The lifecycle shape is right, but the contract between the AI client and Slowave must be tighter. The client can currently complete a task after `activate` and `commit` without producing durable memory, and Slowave has no hard way to distinguish:

1. a session that genuinely learned nothing durable, from
2. a session where the agent forgot to encode what it learned.

The correct enforcement point is **commit**.

The proposed rule:

> A session cannot close ambiguously. At commit time the client must either have encoded durable memory claims, or provide a structured memory audit explaining why no durable memory should be stored.

Equally important:

> A zero-memory session is often correct. Injecting unrelated, trivial, or low-confidence content into a scope is worse than storing nothing.

This changes the contract from:

> “Please remember things; Slowave may warn if you did not.”

to:

> “A task is not complete until Slowave receives scope-relevant durable memory or an explicit no-memory audit.”

This is the core contract Slowave needs. The client instruction block remains the highest-leverage wiring, but server-side enforcement must back it. The target is not maximum memory volume; the target is maximum memory quality.

---

## Goals

1. Make the client/Slowave interaction unambiguous.
2. Prevent silent zero-memory sessions.
3. Improve the quality of remembered facts, not only the quantity.
4. Preserve the five-verb cognitive cycle where possible.
5. Allow breaking endpoint changes if they produce a cleaner contract.
6. Keep enforcement local to the current session rather than relying on delayed heuristics.
7. Preserve scope isolation and evidence provenance, because Slowave uses them for correctness and promotion.
8. Treat retrieval feedback as a first-class learning signal, not optional cleanup.
9. Prefer audited empty sessions over noisy or scope-irrelevant memories.

---

## Non-goals

1. Do not force every trivial task to store a memory.
2. Do not treat `episodes_formed` as proof that durable knowledge was encoded.
3. Do not rely on consolidation-time guesses as the primary enforcement mechanism.
4. Do not add vague quality fields that agents will fill arbitrarily.
5. Do not depend on client-specific behavior that cannot be enforced by Slowave.
6. Do not collapse explicit memories and derived episodic summaries into one quality category.
7. Do not weaken scope requirements for convenience; scope correctness is core memory correctness.
8. Do not optimize for `remember_count` alone; a higher count of bad memories is a worse outcome.

---

## Current failure mode

The current lifecycle is structurally present but under-enforced:

| Step | Intended purpose | Current weakness |
|------|------------------|------------------|
| `activate` | Start session and retrieve context | Good entry point, but memory contract is prose-only |
| `remember` | Encode durable facts | Optional in practice; free-text input is too loose |
| `recall` | Fill context gaps | Useful, but not always tied to feedback obligations |
| `reinforce` | Train retrieval quality | Required by instruction, not enforced by commit |
| `commit` | Close session | Can close with zero memories and no explanation |

The agent can perform real investigation, discover durable implementation facts, and still end with zero `remember` calls. This starves future sessions while the lifecycle appears successful.

The opposite failure is also dangerous: the agent may remember something merely to satisfy a quota. That pollutes memory and can be worse than forgetting. A weather question asked inside a project session must not become project memory. A casual aside, a transient status update, or a low-confidence guess must not be stored as a durable project fact.

Therefore the contract must distinguish:

| Session outcome | Meaning | Health |
|-----------------|---------|--------|
| Encoded durable, scope-relevant memories | Useful facts were learned and stored | Healthy |
| Audited empty | No durable/scope-relevant memory should be stored | Healthy |
| Ambiguous empty | No memories and no explanation | Invalid |
| Noisy remembered | Irrelevant/trivial/wrong-scope content stored | Invalid / damaging |

The goal is not “remember something.” The goal is “remember only what should survive into future retrieval.”

---

## What the acceptance tests show

The acceptance suite exercises Slowave as a black box through the CLI and demonstrates how stored information is actually used. The contract should be designed around these behaviors, not around endpoint aesthetics.

### 1. Explicit `remember` is the highest-quality ingestion path

The suite injects durable facts, warnings, constraints, preferences, and lessons with explicit `remember` calls. Those calls immediately create schemas that later appear in `activate` and `recall` results.

Example memory classes used by the suite:

- `fact` — implementation facts such as daemon port binding and session reaper behavior
- `warning` — hazards such as FAISS rebuild cost
- `constraint` — invariants such as no LLM calls in consolidation
- `preference` — user/project formatting preferences
- `lesson` — reusable implementation guidance such as exponential backoff with jitter

This confirms that `remember` is not a sidecar. It is the main path for high-quality, durable, retrievable schemas.

### 2. Session events can become memories, but they are not equivalent to explicit memories

The suite also creates raw session events with `session start → event → session end → consolidate`. Those events can produce derived episodic-summary schemas and prototype edges.

That path is useful, but it is different from explicit memory:

- explicit memories are immediate, typed, high-salience schemas
- derived event memories depend on episode formation and consolidation
- derived schemas can decay differently from explicitly remembered/recalled schemas

Therefore, a closed session with formed episodes is not proof that the agent encoded durable knowledge intentionally.

### 3. Reinforcement is part of Slowave's learning loop

Acceptance tests use `reinforce` to:

- reward relevant activation results with `useful`
- mark distractors/noise as `irrelevant`
- signal `missing` when a useful memory was absent before being remembered
- demote noisy schemas to `needs_review`

This means retrieval feedback is not optional polish. It is part of how Slowave tunes retrieval quality and suppresses bad context.

### 4. Scope is a correctness boundary

Acceptance tests verify that project-scoped memories do not leak into unrelated project scopes, and that cross-scope promotion only happens when enough evidence exists across scopes.

This means `scope` cannot remain a soft recommendation. For project work, scope is part of correctness.

### 5. Repeated cross-scope evidence drives promotion

The promotion ladder test remembers the same lesson across many scopes. Slowave uses the repeated evidence to promote a schema through generalization stages until it can be admitted globally/domain-wide.

This has a direct contract implication: `remember` should preserve evidence provenance, including session and scope. A structured memory claim should strengthen this, not obscure it.

### 6. Supersession is part of memory hygiene

The suite verifies that remembering an updated fact can supersede an older schema, flipping old state or creating a relation when similarity thresholds are met.

The client contract must therefore make corrections explicit: when a remembered fact updates prior knowledge, the client should provide `supersedes`/`replaces` IDs where available.

### 7. Legitimate zero-memory sessions exist

Some acceptance-test sessions exist only to register scopes or probe retrieval. They may produce no durable new facts. A strict contract must not force fake memories for those sessions.

The correct behavior is not “always remember.” The correct behavior is:

```text
remember durable facts OR explicitly audit why there are none
```

---

## Critical metric correction

`episodes_formed` is not a valid enforcement signal.

Episodes can form from raw events that are not durable memories, including lifecycle/task events. Therefore:

```text
episodes_formed > 0
```

does **not** imply:

```text
durable memories were encoded
```

The correct signal is direct memory encoding:

```sql
COUNT(*)
FROM raw_events
WHERE session_id = ?
  AND type LIKE 'remember:%'
```

Eventually this should be persisted as:

```sql
ALTER TABLE sessions
ADD COLUMN remember_count INTEGER NOT NULL DEFAULT 0;
```

But phase 1 does not need to wait for the schema migration. `commit` can query `raw_events` directly first, then move to a persisted counter later.

---

## Core invariant

Every session must end in one of two valid states. The invariant is **not** “every session must remember.” The invariant is **every session must make an explicit memory decision**.

### State A — memories encoded

```text
remember_count > 0
```

At least one durable, scope-relevant memory was stored for the session.

### State B — no-memory audit accepted

```text
remember_count == 0
AND memory_audit.no_new_memory_reason is present
AND memory_audit.skipped_candidates is present when applicable
```

The client explicitly declares that it considered memory candidates and no durable/scope-relevant memory should be stored.

This is a healthy outcome, not a degraded outcome. For trivial, unrelated, duplicate, or low-confidence interactions, audited empty is safer than storing noise.

### Invalid state — ambiguous close

```text
remember_count == 0
AND no valid memory_audit exists
```

This must reject commit and leave the session open.

### Invalid state — noisy memory

```text
remember_count > 0
AND remembered content is unrelated to scope, transient, trivial, unsupported, or low-confidence masquerading as fact
```

This is worse than audited empty. It should be caught by remember-quality validation where possible, and by retrieval feedback/demotion if it slips through.

---

## Proposed endpoint contract

The five verbs can remain, but their contracts should tighten.

---

## 1. `slowave_activate`

### Purpose

Start a task session, retrieve relevant memories, and return a machine-readable memory contract.

### Required inputs

```json
{
  "query": "verbatim user request",
  "scope": "project:<basename(cwd)>",
  "goal": "3-6 word verb-noun phrase",
  "task_type": "coding|debugging|review|writing|planning|other",
  "mode": "strict_scope",
  "limit": 8
}
```

### Contract changes

- `scope` should become required for project work.
- `query` must be verbatim user input, not a summary.
- `goal` should remain short and stable enough to improve retrieval overlap.
- The response must include the memory contract, not only a prose brief.

### Proposed response additions

```json
{
  "session_id": "sess_...",
  "retrieval_id": "ctx_...",
  "rendered": "...",
  "schemas": [],
  "memory_contract": {
    "version": 1,
    "commit_requires": "remember_or_audit",
    "scope_required": true,
    "session_id_required_after_activate": true,
    "remember_policy": "store_only_durable_scope_relevant_claims",
    "allow_no_memory_with_audit": true,
    "noisy_memory_is_contract_violation": true,
    "quality_rules": [
      "one atomic claim per remember call",
      "blank-slate phrasing",
      "scope-relevant durable content only",
      "include source/evidence when possible",
      "include novelty_basis",
      "do not encode transient task state"
    ]
  },
  "scope_health": {
    "total_sessions": 47,
    "empty_sessions": 14,
    "empty_rate": 0.298,
    "schema_count": 3,
    "status": "poor"
  }
}
```

### Why this matters

The client should not infer the contract only from instruction prose. Slowave should return a machine-readable contract on every activation, and the client instruction block should require the agent to obey it.

---

## 2. `slowave_remember`

### Purpose

Encode one durable, atomic, high-quality memory claim.

The claim must preserve the evidence that Slowave uses later: scope, session, source, and whether the new claim corrects/supersedes older knowledge.

### Problem with current shape

Current shape:

```text
slowave_remember(content, type, scope, session_id)
```

This is too loose. It permits vague, context-dependent text such as:

```text
Fixed it by adding the field.
```

Slowave needs blank-slate durable claims with quality metadata.

### What must not be remembered

The client must not call `remember` merely to avoid an empty session. These are contract violations:

| Candidate | Correct action |
|-----------|----------------|
| Weather/chitchat while in a project scope | audited empty with `unrelated_to_scope` or `user_chitchat` |
| “I edited file X” task progress | audited skip with `ephemeral_task_state` |
| A fact already retrieved unchanged | audited skip with `duplicate_of_retrieved_memory` |
| Unsupported guess | audited skip with `insufficient_confidence` or store as `open_question` only if durable |
| Sensitive/private content that should not persist | audited skip with `sensitive_or_should_not_store` |
| Vague text such as “fixed it” | reject and ask for blank-slate rewrite |

Noisy memory should be treated as a failed write, not as a successful memory cycle.

### Proposed breaking contract

```json
{
  "session_id": "sess_...",
  "scope": "project:slowave",
  "claim": {
    "content": "Commit enforcement must use remember_count instead of episodes_formed because task_complete events can form episodes without durable memories.",
    "type": "constraint",
    "confidence": 0.95,
    "source": "code_review",
    "evidence": [
      {
        "kind": "file",
        "ref": "slowave/core/services/ingest.py:52-60",
        "quote": "embeddable events exclude context_query but may include task_complete"
      }
    ],
    "novelty_basis": "Not present in activate results; discovered by reviewing commit and ingest paths.",
    "supersedes": [],
    "tags": ["memory-cycle", "commit-contract", "enforcement"]
  }
}
```

### Required claim fields

| Field | Required | Reason |
|-------|----------|--------|
| `content` | Yes | The durable claim |
| `type` | Yes | Memory class and retrieval behavior |
| `scope` | Yes | Prevents memory bleed |
| `confidence` | Yes | Indicates certainty; must be defined semantically |
| `source` | Yes | Distinguishes user preference, code review, docs, test failure, etc. |
| `novelty_basis` | Yes | Forces comparison against retrieved context |
| `evidence` | Recommended | Grounds the claim and improves trust |
| `supersedes` | Optional | Supports corrections |
| `tags` / `entities` | Optional | Improves retrieval and filtering |

### Provenance requirement

Acceptance behavior depends on evidence provenance. Cross-scope promotion, scope isolation, supersession, and schema evidence checks all depend on knowing where a memory came from.

Therefore a structured remember call must not merely create a schema. It must preserve:

- `session_id`
- `scope`
- raw remember event ID
- source kind
- evidence links
- supersession/correction intent when known

### Confidence semantics

If `confidence` is added, it must have defined semantics:

| Range | Meaning |
|-------|---------|
| `0.95-1.0` | Direct user statement, verified code fact, or passing-test-backed result |
| `0.75-0.94` | Strong inference from code/docs, not independently tested |
| `0.50-0.74` | Plausible but uncertain observation; should often be `needs_review` |
| `<0.50` | Usually should not be stored as fact; use `open_question` or skip |

### Proposed response

```json
{
  "stored": true,
  "event_id": "evt_456",
  "schema_id": "sch_123",
  "quality": {
    "status": "accepted",
    "score": 0.91,
    "warnings": []
  },
  "session_memory": {
    "remember_count": 3,
    "quality_avg": 0.86
  }
}
```

### Rejection example

Input:

```json
{
  "claim": {
    "content": "Fixed it by adding the field",
    "type": "fact"
  }
}
```

Response:

```json
{
  "stored": false,
  "rejected": true,
  "reason": "memory_content_not_blank_slate",
  "hint": "Rewrite as a durable claim understandable without this session context."
}
```

---

## 3. `slowave_recall`

### Purpose

Retrieve additional memory when activate is insufficient.

### Contract changes

- Require `scope` for project work.
- Require specific semantic queries.
- Return a `retrieval_id` that must be reinforced before commit if memories were returned.

### Proposed response addition

```json
{
  "retrieval_id": "rec_...",
  "memories": [],
  "feedback_required": true
}
```

---

## 4. `slowave_reinforce`

### Purpose

Give Slowave retrieval-quality feedback.

### Problem

The instruction says reinforce is mandatory after retrieval, but commit does not enforce it.

Acceptance behavior shows why this matters: reinforcement is used to reward relevant retrievals, mark irrelevant distractors, signal missing memories, and push noisy schemas toward `needs_review`. Without reliable feedback, Slowave cannot learn which memories are useful and which memories pollute context.

### Proposed enforcement

Track retrieval IDs opened in a session and require feedback before successful commit when retrieved memories were returned.

Commit may warn at first, then reject in strict mode:

```json
{
  "warning": "retrieval_feedback_missing",
  "missing_retrieval_ids": ["ctx_...", "rec_..."]
}
```

Future schema addition:

```sql
ALTER TABLE sessions
ADD COLUMN reinforce_count INTEGER NOT NULL DEFAULT 0;
```

or a dedicated table mapping session retrieval obligations to feedback events.

---

## 5. `slowave_commit`

### Purpose

Close the task session only when Slowave has received durable memory or an explicit no-memory audit.

### Proposed breaking contract

```json
{
  "session_id": "sess_...",
  "scope": "project:slowave",
  "outcome": "success",
  "memory_audit": {
    "encoded_schema_ids": ["sch_123", "sch_124"],
    "no_new_memory_reason": null,
    "skipped_candidates": [
      {
        "candidate": "The user asked for a review of the current document.",
        "skip_reason": "transient_task_request"
      }
    ],
    "retrieval_feedback_done": true
  }
}
```

### Valid no-memory commit

Some sessions are legitimately empty: scope registration, pure retrieval probes, trivial interactions, unrelated user questions, or simple formatting tasks may teach nothing durable. Those sessions should close with an explicit audit, not with fake memories.

Accepted `no_new_memory_reason` categories:

| Reason | Use when |
|--------|----------|
| `trivial_interaction` | The interaction has no future utility |
| `unrelated_to_scope` | The request is not about the active scope, e.g. weather in a project session |
| `no_durable_information` | The task used existing knowledge and produced no reusable fact |
| `duplicate_of_retrieved_memory` | The only candidate facts were already returned by activate/recall |
| `ephemeral_task_state` | The candidate was only about what happened in this session |
| `user_chitchat` | Casual conversation with no durable preference/fact |
| `insufficient_confidence` | The agent cannot justify storing the claim |
| `sensitive_or_should_not_store` | The content should not persist |

```json
{
  "session_id": "sess_...",
  "scope": "project:slowave",
  "outcome": "success",
  "memory_audit": {
    "encoded_schema_ids": [],
    "no_new_memory_reason": "trivial_interaction",
    "explanation": "No durable facts, constraints, preferences, decisions, procedures, warnings, or lessons were learned. The task was a simple formatting-only edit.",
    "skipped_candidates": [
      {
        "candidate": "Changed Markdown spacing in one document.",
        "skip_reason": "ephemeral_task_state"
      }
    ],
    "retrieval_feedback_done": true
  }
}
```

Example unrelated-to-scope audit:

```json
{
  "session_id": "sess_...",
  "scope": "project:slowave",
  "outcome": "success",
  "memory_audit": {
    "encoded_schema_ids": [],
    "no_new_memory_reason": "unrelated_to_scope",
    "explanation": "The user asked about the weather while a project scope was active. The interaction contained no durable project-relevant information.",
    "skipped_candidates": [
      {
        "candidate": "Weather discussion",
        "skip_reason": "unrelated_to_scope"
      }
    ],
    "retrieval_feedback_done": true
  }
}
```

### Commit acceptance rule

Commit succeeds iff:

```text
remember_count > 0
OR valid memory_audit.no_new_memory_reason exists
```

For reporting, use distinct health statuses:

| Status | Meaning |
|--------|---------|
| `encoded` | One or more accepted memories were stored |
| `audited_empty` | No memory stored, with valid no-memory audit |
| `rejected_ambiguous_empty` | No memory and no valid audit |
| `rejected_noisy_memory` | Remember call was rejected for quality/scope reasons |

In strict mode, also require:

```text
all retrievals with returned memories have reinforcement feedback
```

### Rejection response

```json
{
  "closed": false,
  "session_id": "sess_...",
  "error": "memory_audit_required",
  "message": "This session encoded zero durable memories. Before commit, either call slowave_remember for durable facts or provide memory_audit.no_new_memory_reason with skipped candidates.",
  "remember_count": 0,
  "required_action": "remember_or_commit_with_audit"
}
```

### Important behavior change

Commit must be able to fail without closing the session.

This is a breaking change, but it is the enforcement anchor. If commit always closes, the contract remains advisory.

---

## Revised client instruction block

The installed lifecycle block should be rewritten around a contract, not a ritual.

```markdown
## MANDATORY — Slowave memory contract

Slowave is the long-term memory system. Your task is not complete until Slowave receives high-quality feedback.

### Contract

1. Start every task with `slowave_activate`.
   - Pass the verbatim user request as `query`.
   - Pass `scope="project:<basename(cwd)>"`.
   - Store `session_id`, `retrieval_id`, and `memory_contract`.

2. During the task, call `slowave_remember` immediately when you learn a durable, scope-relevant fact.
   A durable fact is anything that could save a future session in this scope from rediscovering it:
   - project constraints
   - user preferences
   - architectural decisions
   - surprising bugs/root causes
   - procedures
   - warnings/hazards
   - durable open questions or TODOs

3. Every memory must be atomic and blank-slate.
   Bad: "fixed it by adding the field"
   Good: "Commit enforcement must use remember_count instead of episodes_formed because task_complete events can form episodes without durable memories."

4. Do not skip memory silently.
   If you considered a candidate and skipped it, record the skip in the commit memory audit.

   Do not remember irrelevant content just to avoid an empty session. Weather, chitchat, transient task state, duplicate retrieved facts, and unsupported guesses should be audited as skipped, not stored.

5. After every activate/recall that returned memories, call `slowave_reinforce`.
   Penalize stale, wrong, irrelevant, and noisy memories. Do not default to useful.

6. Before final response, perform a memory audit:
   - If durable facts were learned, call `slowave_remember` for each.
   - If no durable facts were learned, prepare `memory_audit.no_new_memory_reason`.
   - If the interaction was unrelated to scope, use `unrelated_to_scope`.
   - Commit rejects ambiguous zero-memory sessions.

7. End with `slowave_commit(session_id, scope, outcome, memory_audit)`.
   Successful commit requires remembered durable scope-relevant facts OR an explicit no-memory audit.
```

---

## Ideas to keep, modify, or discard

### Keep

- Reframe `remember` as the purpose of the cycle.
- Track `remember_count` directly.
- Surface scope-level encoding health during `activate`.
- Fold cold-start schema/session ratio into the same health path.
- Add a pre-commit checkpoint.
- Treat audited empty sessions as healthy when the interaction is trivial, unrelated, duplicate, low-confidence, or non-durable.

### Modify

- Change `commit` from warning-only to **enforced audit**.
- Expand `confidence` into a structured claim contract.
- Treat `episodes_formed` as a diagnostic only, never an enforcement signal.
- Replace any “remember minimum” framing with “scope-relevant durable memory or audit.”

### Discard or defer

- Discard `hard reject after N empty sessions` as the primary mechanism. Per-session enforcement is clearer.
- Discard any policy that rewards memory volume alone. It incentivizes noisy writes.
- Defer consolidation-time missed-opportunity detection unless clients also log external tool activity to Slowave.
- Defer confidence-only changes; confidence without evidence/source/novelty metadata is too weak.

---

## Why consolidation-time detection is not enough

The proposal to detect missed opportunities during consolidation using `event_count > threshold AND remember_count == 0` is only valid if Slowave sees real client activity.

Current MCP raw events mainly capture Slowave lifecycle events, such as:

- `context_query`
- `remember:*`
- `task_complete`

They do not necessarily include external reads, edits, searches, tests, and code-review discoveries. Therefore raw `event_count` is not a reliable proxy for investigation depth.

If this detection is desired later, add a client activity endpoint:

```text
slowave_note_event(type="tool_read|tool_edit|test_run|finding|decision", content, metadata)
```

Until then, missed memory encoding must be enforced at client-instruction and commit-audit time.

---

## Breaking changes worth making

### 1. Require `scope`

For project work, scope omission should be invalid. Scope bleed is worse than a breaking change.

### 2. Require explicit `session_id` after activate

Implicit session resolution is ergonomic but hides client bugs. A strict contract should require clients to carry `session_id` through `remember`, `reinforce`, and `commit`.

Migration path:

1. warn when omitted,
2. require in strict mode,
3. make required globally.

### 3. Replace free-text remember with structured claims

This is the largest memory-quality improvement.

### 4. Add `memory_audit` to commit

This is the core enforcement mechanism.

### 5. Let commit fail without closing the session

Without this, the contract remains advisory.

---

## Implementation plan

### Phase 1 — enforce the contract with minimal schema work

1. Update the lifecycle block to the strict memory-contract wording.
2. Add optional `memory_audit` parameter to `slowave_commit`.
3. In `commit`, compute `remember_count` directly from `raw_events`.
4. If `remember_count == 0` and no valid audit is provided, return `closed=false` and do not end the session.
5. Keep `episodes_formed` in the response only as a diagnostic.
6. Update CLI/MCP callers and acceptance helpers so legitimate no-memory commits pass an explicit audit.
7. Add tests:
   - zero remembers + no audit rejects
   - zero remembers + valid audit accepts
   - remembers present accepts
   - `episodes_formed` is not used for enforcement
   - scope-registration/probe sessions close with audited-empty status
   - unrelated weather/chitchat sessions close with audited-empty status
   - attempts to remember unrelated content are rejected or warned as noisy memory

### Phase 2 — persistence and observability

1. Add `sessions.remember_count`.
2. Increment it in `engine.remember()`.
3. Add `scope_health` to `activate`.
4. Add dashboard visibility for empty/audited/healthy sessions.
5. Track retrieval feedback obligations per session.

### Phase 3 — structured quality contract

1. Change `slowave_remember` to accept structured `claim` objects.
2. Add quality validation and reject vague/context-dependent memories.
3. Add confidence/source/evidence/novelty metadata to schema facets or evidence rows.
4. Require explicit `session_id` after activate.
5. Require `scope` on all project endpoints.
6. Preserve backwards compatibility temporarily by translating legacy `content,type,scope,session_id` calls into structured claims with `source="legacy_client"` and quality warnings.

### Phase 4 — optional client activity logging

1. Add `slowave_note_event` only if missed-opportunity analysis needs real client activity.
2. Use logged tool activity to identify high-investigation zero-memory sessions.
3. Feed those metrics into dashboard and activate health.

---

## Test scenarios

### 1. Ambiguous zero-memory session rejects

```text
activate → commit(no audit)
```

Expected:

```json
{
  "closed": false,
  "error": "memory_audit_required"
}
```

### 2. Legitimate no-memory session accepts

```text
activate → commit(memory_audit.no_new_memory_reason present)
```

Expected:

```json
{
  "closed": true,
  "remember_count": 0,
  "encoding_health": "audited_empty"
}
```

### 3. Memory session accepts

```text
activate → remember → commit
```

Expected:

```json
{
  "closed": true,
  "remember_count": 1,
  "encoding_health": "encoded"
}
```

### 4. Bad memory quality rejects

```text
remember(content="fixed it")
```

Expected:

```json
{
  "stored": false,
  "reason": "memory_content_not_blank_slate"
}
```

### 5. Missing reinforcement warns or rejects in strict mode

```text
activate(returns schemas) → remember → commit(no reinforce)
```

Expected phase 1:

```json
{
  "closed": true,
  "warning": "retrieval_feedback_missing"
}
```

Expected strict mode:

```json
{
  "closed": false,
  "error": "retrieval_feedback_required"
}
```

### 6. Unrelated interaction should not be remembered

```text
activate(scope="project:slowave") → user asks about weather → commit(audit: unrelated_to_scope)
```

Expected:

```json
{
  "closed": true,
  "remember_count": 0,
  "encoding_health": "audited_empty",
  "memory_audit": {
    "no_new_memory_reason": "unrelated_to_scope"
  }
}
```

### 7. Noisy memory write rejects

```text
activate(scope="project:slowave") → remember("The weather is sunny today.", type="fact", scope="project:slowave")
```

Expected:

```json
{
  "stored": false,
  "rejected": true,
  "reason": "memory_not_scope_relevant"
}
```

---

## Final recommendation

Implement the strict commit audit before investing in consolidation heuristics.

The best contract is not:

> remember if possible, warn if not.

It is also not:

> remember something in every session.

The best contract is:

> remember durable, scope-relevant knowledge or explicitly audit why there is nothing safe and useful to remember; otherwise the task cannot close.

That creates a crystal-clear client/Slowave handshake, makes failure local and actionable, and produces higher-quality input for Slowave over time. Empty audited sessions are acceptable. Noisy memories are not.
