# Review & counter-proposal: Strict memory contract

**Date:** 2026-07-06  
**Status:** Proposal  
**References:** `docs/iterations/20260706_strict_memory_contract.md`, `docs/iterations/20260706_enforcing_memory_cycle.md`  

---

## Executive summary

The strict-memory-contract proposal is **80% correct** in its diagnosis and its core mechanism, but it over-engineers the client-facing `memory_audit` payload and pushes semantic quality judgments server-side where they are unreliable.

The correct contract is simpler:

> **Client says what it learned** (`slowave_remember`) **or why it learned nothing** (`no_new_memory_reason`).  
> **Server counts, tracks, and gates** — rejecting commit when neither is present.

This document validates each idea from the original proposal, identifies what to keep / modify / discard, and proposes the concrete endpoint design and the rewritten client-instruction block that should ship.

---

## 1. What the original proposal gets right

These ideas are correct and should be implemented as-is or with minor adjustments.

| # | Idea | Verdict |
|---|------|---------|
| 1 | **Commit must be able to fail** (`closed: false`). Without this the contract remains advisory. | **Keep.** This is the only non-negotiable change. |
| 2 | **`remember_count` is the enforcement signal**, not `episodes_formed`. `task_complete` events also form episodes; `episodes_formed > 0` is a false positive for "I learned something." | **Keep.** |
| 3 | **Pre-defined `no_new_memory_reason` categories** force the client to think about *why* nothing was remembered. | **Keep.** |
| 4 | **Reinforcement is a learning signal**, not optional polish. Commit should warn (then reject in strict mode) when reinforce was not called after retrieval. | **Keep.** |
| 5 | **Reframe `remember` as the purpose of the cycle** in the instruction block. The lifecycle block is the highest-leverage text in the system. | **Keep.** |
| 6 | **Audited empty is healthy; noisy forced memories are damaging.** The four-session-outcome taxonomy (encoded, audited empty, ambiguous empty, noisy remembered) is correct. | **Keep.** |
| 7 | **Scope is a correctness boundary.** Scope-registration and pure-probe sessions close with audited-empty status. | **Keep.** |
| 8 | **`encoding_health` surfaced in activate** improves visibility at session start. | **Keep.** |
| 9 | **Fold cold-start ratio into the same encoding-health code path.** | **Keep.** |

---

## 2. What needs modification

### 2.1 The `memory_audit` payload is too heavy

The original proposes this commit payload:

```json
"memory_audit": {
  "encoded_schema_ids": ["sch_123"],
  "no_new_memory_reason": null,
  "skipped_candidates": [
    {"candidate": "...", "skip_reason": "..."}
  ],
  "retrieval_feedback_done": true
}
```

**Three of these four fields are self-attested by the client and carry zero enforcement value.**

- `encoded_schema_ids`: The server already has them — `raw_events` rows where `type LIKE 'remember:%'`. Making the client duplicate this invites inconsistency.
- `skipped_candidates`: The client can trivially fabricate these. The `no_new_memory_reason` string is sufficient to explain why nothing was stored.
- `retrieval_feedback_done`: The server already knows which retrieval_ids were returned and whether `reinforce` was called.

**Recommended:** Commit should only need ONE new field from the client:

```
no_new_memory_reason: "trivial_interaction" | "unrelated_to_scope" | ... | null
```

The server derives everything else:

| Server derives | From |
|----------------|------|
| `remember_count` | `raw_events WHERE type LIKE 'remember:%'` for this session |
| `encoding_health` | `remember_count > 0` → `"encoded"`; `remember_count == 0 AND reason` → `"audited_empty"`; neither → rejected |
| `retrieval_feedback_missing` | Active retrieval_ids vs. reinforcement events seen |

The client's obligation: remember what you learned, or state why you learned nothing. Nothing more.

### 2.2 Server-side quality validation of `remember` is the wrong layering

The original proposes rejecting `remember` calls for:
- `"fixed it"` → `memory_content_not_blank_slate`
- `"The weather is sunny today."` → `memory_not_scope_relevant`

**Problem:** Both are LLM-level judgments. The server cannot reliably detect context-dependent pronouns through regex or embeddings. Cosine similarity of content to scope tokens (`"slowave"`) has too much false-positive risk.

**Recommended:** These belong in the **client instruction block**, not the server.

The server should validate only structural invariants:

| Check | Action |
|-------|--------|
| Content is empty | Reject |
| Content length < minimum threshold (e.g. 12 chars) | Reject |
| Type is not a valid enum member | Reject |
| Scope is missing for project-scoped work | Warn (Phase 1) → Reject (strict mode) |

Quality and relevance are the client's responsibility, enforced by the lifecycle block.

### 2.3 Single reinforcement obligation, not per-retrieval_id

Track a single boolean on the session rather than per-retrieval_id tracking. If activate/recall returned schemas and no reinforce was called before commit, warn (Phase 1) → reject (strict mode).

---

## 3. What to discard

| Idea | Why |
|------|-----|
| `skipped_candidates` array in commit | Self-attested, zero enforcement value. The reason code is sufficient. |
| `retrieval_feedback_done: true` in commit | Server should derive from session state, not trust client self-report. |
| `encoded_schema_ids` in commit | Server already has them from raw_events. Client duplication invites inconsistency. |
| Server-side `remember` semantic quality rejection | LLM-level judgments; unreliable geometrically. Client instruction block is the enforcement point. |
| Server-side `remember` scope relevance rejection | Cosine-to-scope-token is too fragile. Client must self-police. |
| Phase 3: structured `claim` objects (`confidence`, `source`, `evidence`, `novelty_basis`, `supersedes`) | Over-engineered. `content` + `type` + `scope` is sufficient. Confidence is 1.0 for explicit memories by design. The server already handles supersession geometrically. |
| Phase 4: `slowave_note_event` client activity logging | The commit audit solves the problem without this. |
| Require explicit `session_id` after activate | The implicit session resolver already works reliably. Making this required would cause failures without quality gains. |

---

## 4. Recommended contract design

### 4.1 Endpoints

```
slowave_activate(query: str, scope: str?, goal: str?, task_type: str?,
                 mode: str, limit: int)
  → session_id, retrieval_id, rendered, schemas,
    cold_start, cue_terms, suppressed, encoding_health

slowave_remember(content: str, type: str, scope: str?, session_id: str?)
  → stored: bool, schema_id: str?, memory_type: str, scope: str?,
    warnings: [str]      ← structural only

slowave_recall(query: str, scope: str?, top_k: int, evidence: bool, mode: str)
  → retrieval_id, memories, episodes?, raw_events?

slowave_reinforce(retrieval_id: str, feedback: str, outcome: str,
                  used_memory_ids: [str]?, irrelevant_memory_ids: [str]?,
                  stale_memory_ids: [str]?, wrong_memory_ids: [str]?)
  → applied: {reinforced, penalized, marked_review}

slowave_commit(scope: str?, outcome: str?, session_id: str?,
               no_new_memory_reason: str?)
  → closed: bool,
    encoding_health: "encoded" | "audited_empty" | "rejected_ambiguous_empty",
    remember_count: int,
    episodes_formed: int,
    retrieval_feedback_missing: bool,
    warning: str?,
    error: str?
```

### 4.2 Commit acceptance rules

```
IF remember_count == 0 AND no_new_memory_reason is None:
    → closed: false
    → encoding_health: "rejected_ambiguous_empty"
    → error: "memory_audit_required"
    → Session is NOT ended

IF remember_count == 0 AND no_new_memory_reason is a valid code:
    → closed: true
    → encoding_health: "audited_empty"
    → Session IS ended normally

IF remember_count > 0:
    → closed: true
    → encoding_health: "encoded"
    → Session IS ended normally

IF active_retrieval_ids exist AND no reinforce was called:
    → Phase 1: warning: "retrieval_feedback_missing"
    → Strict mode: closed: false, error: "retrieval_feedback_required"
```

### 4.3 `no_new_memory_reason` valid codes

| Code | Use when |
|------|----------|
| `trivial_interaction` | The interaction has no future utility |
| `unrelated_to_scope` | The request is not about the active scope |
| `no_durable_information` | The task used existing knowledge; produced no reusable fact |
| `duplicate_of_retrieved_memory` | The only candidate facts were already returned by activate/recall |
| `ephemeral_task_state` | The candidate was only about what happened in this session |
| `insufficient_confidence` | The agent cannot justify storing the claim |
| `sensitive_or_should_not_store` | The content should not persist |

### 4.4 Test scenarios

**Scenario 1 — Ambiguous zero-memory session rejects:**
```
activate → commit(no_reason=null)
→ closed: false, error: "memory_audit_required"
```

**Scenario 2 — Legitimate no-memory session accepts:**
```
activate → commit(no_reason="trivial_interaction")
→ closed: true, encoding_health: "audited_empty", remember_count: 0
```

**Scenario 3 — Memory session accepts:**
```
activate → remember → commit(no_reason=null)
→ closed: true, encoding_health: "encoded", remember_count: 1
```

**Scenario 4 — Unrelated interaction audited empty:**
```
activate(scope="project:slowave") → user asks about weather → commit(no_reason="unrelated_to_scope")
→ closed: true, encoding_health: "audited_empty", remember_count: 0
```

**Scenario 5 — Missing reinforcement warns:**
```
activate(returns schemas) → remember → commit(no reinforce)
→ closed: true, warning: "retrieval_feedback_missing"
```
---

The current v3 lifecycle block is already good. The changes below reframe `remember` as the purpose
and add the commit audit checkpoint.

> **Note:** The block uses `v4` markers. Bump the version in `setup.py` when deploying.

### Key changes from v3 to v4

| v3 | v4 |
|----|----|
| "5-verb cognitive cycle" header | "Memory contract" header — framing it as a contract, not a ritual |
| Step 2 starts with "Novelty gate — skip if..." | Step 2 starts with "the purpose of this cycle" |
| Step 5: "Non-negotiable. Scope must match..." | Step 5: "Before calling commit, perform a memory audit" with reason codes |
| No commit audit | Commit rejects without memories or a reason |
| No mention of `no_new_memory_reason` | Full audit taxonomy + rejection warning |
| Anti-patterns: 14 items | Anti-patterns: 17 items (+3: pass `no_new_memory_reason` for real changes, remember chitchat to avoid rejection, skip audit) |

### Full v4 lifecycle block

The block below replaces the current `_LIFECYCLE_BLOCK_TEMPLATE` in `slowave/cli/setup.py`.

```
<!-- slowave-lifecycle-start v4 -->
## MANDATORY — Slowave memory contract

Slowave is your long-term memory. Your task is not complete until Slowave
receives high-quality feedback. Do not respond until step 1 completes.
Do not end the task without step 5.

**1 — `slowave_activate` (before your first response)**
`slowave_activate(query="<verbatim task>", goal="<short goal>", scope="project:<basename(cwd)>")`
→ store `session_id`, `retrieval_id`.
- `query`: the task verbatim — do not summarize (raw text drives retrieval).
- `goal`: 3–6 word verb-noun phrase, e.g. `"fix auth null pointer"`.
- `scope`: `project:<name>` (or `user:<id>` / `domain:<topic>`). Never omit.
- Call ONCE.

   **Cold start gate — if `cold_start: true`:**
   - Find the first existing file: CLAUDE.md, README.md, AGENTS.md.
   - For each fact in it, ask: is it durable AND not already observable in this context?
     If yes to both, call `slowave_remember()` — one call per fact.
   - Exhaust that document before responding. Do NOT scan the full codebase.

**2 — `slowave_remember` (the purpose of this cycle)**
`slowave_remember(content, type, scope="project:<basename(cwd)>")`
- Turning what you learn into durable knowledge IS the purpose. Activate finds context,
  recall fills gaps, reinforce tunes retrieval — but remember saves what matters for
  future sessions.
- ONE fact per call (never bundle — it blurs the embedding).
- Blank-slate phrasing: write so a reader with zero session context understands it.
  WRONG: `"fixed it by adding the field"`
  RIGHT: `"SessionReaper idle timeout defaults to 3600s; the HTTP daemon disables it (0)"`
- `type` (pick the most specific; default `decision`):
  `fact` · `preference` · `decision` · `constraint` · `procedure` ·
  `lesson` · `warning` · `open_question` · `task` · `artifact`
- If a remembered fact changed: flag the old one via `stale_memory_ids`/`wrong_memory_ids`
  in step 4.
- **Do NOT remember irrelevant content just to avoid rejection.** Weather, chitchat,
  transient state, duplicate retrieved facts, and unsupported guesses should be audited
  as skipped — not stored.

**3 — `slowave_recall` (only when activate fell short)**
`slowave_recall(query, scope="project:<basename(cwd)>")` — specific, semantic query.
Always pass `scope`. Store the returned `retrieval_id`. Not a substitute for activate.

**4 — `slowave_reinforce` (after ANY retrieval — reward hits, suppress noise)**
Call whenever activate/recall returned memories — not only when you used some.
`slowave_reinforce(retrieval_id, feedback, outcome, used_memory_ids=[...],
  irrelevant_memory_ids=[...], stale_memory_ids=[...], wrong_memory_ids=[...])`
- `used_memory_ids`: IDs you actually relied on (strengthens them).
- Penalty-ID lists: this is how the store self-cleans. Use real IDs only.
- `feedback` and `outcome`: honest, not optimistic.
- **Commit warns when reinforcement is missing after retrieval.**

**5 — `slowave_commit` (memory audit + session close)**
`slowave_commit(scope="project:<basename(cwd)>", outcome="success|partial|failure",
  no_new_memory_reason=...)`
- **Before calling commit, perform a memory audit:**
  - Did you learn durable, scope-relevant facts during this task?
    → YES: call `slowave_remember` for each, then commit without `no_new_memory_reason`.
    → NO: pass one of these reason codes to commit:
      `trivial_interaction` | `unrelated_to_scope` | `no_durable_information`
      `duplicate_of_retrieved_memory` | `ephemeral_task_state`
      `insufficient_confidence` | `sensitive_or_should_not_store`
- **Commit REJECTS** (`closed: false`) if you neither remembered nor passed a reason code.
  The session stays open and the task is incomplete. Re-attempt with memories or a reason.
- An audited empty session is healthy. A noisy forced memory is not.

Anti-patterns: skip activate · `remember` without `scope` · bundle facts in one call ·
context-dependent phrasing · re-encode facts already surfaced · leave a superseded fact
unflagged · reinforce only hits and never penalize noise · default feedback to `useful` ·
invent memory IDs · report `success` when partial/failed · pass `no_new_memory_reason` for
sessions that made real code changes · remember weather/chitchat to avoid rejection ·
skip reinforce or commit.
<!-- slowave-lifecycle-end v4 -->
```
---

## 6. Implementation plan

### Phase 1 — Enforcement anchor (highest priority, ~80 lines total)

| # | Change | Effort | Files |
|---|--------|--------|-------|
| 1 | Add `remember_count` column to `sessions` table + increment in `engine.remember()` | ~5L SQL + ~3L Python | `storage/schema.sql`, `engine.py` |
| 2 | Add `no_new_memory_reason` parameter to `ops.py:commit()` | ~2L | `ops.py` |
| 3 | Compute `remember_count` in commit; reject `closed: false` when zero + no reason | ~25L | `ops.py` |
| 4 | Update `slowave_commit` tool signature to accept `no_new_memory_reason` | ~3L | `mcp/tools.py` |
| 5 | Update CLI `commit` command to accept `--no-new-memory-reason` | ~5L | `cli/main.py` |
| 6 | Tests: zero-remembers-no-reason rejects, zero-remembers-reason accepts, remembers-present accepts | ~40L | `tests/` |

### Phase 2 — Lifecycle block (highest impact, ~40 lines changed)

| # | Change | Effort | Files |
|---|--------|--------|-------|
| 7 | Replace v3 block with v4 block in `_LIFECYCLE_BLOCK_TEMPLATE` | ~30L changed | `cli/setup.py` |
| 8 | Update reference in `CLAUDE.md` and `docs/install.md` to match v4 wording | ~10L | various |

### Phase 3 — Observability & warnings (~40 lines)

| # | Change | Effort | Files |
|---|--------|--------|-------|
| 9 | Add `encoding_health` to `activate` response (scope-level stats) | ~15L | `ops.py`, `engine.py` |
| 10 | Track reinforcement obligations in session state; warn/reject in commit | ~15L | `ops.py` |
| 11 | Structural validation in `remember` (empty, too short, invalid type) | ~10L | `ops.py` |

### Phase 4 — Strict mode (optional, later)

| # | Change | Effort |
|---|--------|--------|
| 12 | Require scope on all project endpoints | ~5L |
| 13 | Reject commit when reinforcement is missing (not just warn) | ~5L |

---

## 7. Core insight

The original proposal's framing is correct:

> *Remember durable, scope-relevant knowledge or explicitly audit why there is nothing safe and useful to remember; otherwise the task cannot close.*

What changes is **how** the client expresses this. The client should not assemble a complex `memory_audit` JSON object — it should call `slowave_remember` when it learns, and pass a single reason string to commit when it doesn't. The server handles counting, tracking, and gating.

The contract that produces the highest-quality input for Slowave is the one that asks for the **minimum honest signal** from the client and derives everything else server-side.

| What the server derives | What the client must provide |
|--------------------------|------------------------------|
| `remember_count`, `encoding_health` | `slowave_remember()` calls when facts are learned |
| `retrieval_feedback_missing` | `slowave_reinforce()` when memories were retrieved |
| `closed` gating | `no_new_memory_reason` (one string) when no memories were stored |

This is the contract described here.