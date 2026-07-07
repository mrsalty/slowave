# UX Refactor Design — MCP API Friction Reduction

**Date:** 2026-06-10  
**Status:** Design / pre-implementation  
**Branch:** main (baseline commit `845abc3`)

---

## Problem Statement

Current MCP protocol exposes internal implementation details as required agent rituals:

```
[TASK START]   slowave_session_start + slowave_context   ← 2 calls
[EVERY TURN]   slowave_event(session_id, ...)            ← 2N calls
[WHEN NEEDED]  slowave_remember(...)                     ← M calls
[TASK END]     slowave_session_end + retrieval_feedback  ← 2 calls
```

Minimum: 3 calls. Realistic: 8–20+ per task. Agents skip session management silently.

**North star: the human brain.** Hippocampal encoding is passive and automatic. You only consciously engage when something is worth saving. Slowave should work the same way.

**Root cause:** The session lifecycle is an internal episode-formation boundary that leaked into the public API. Same with feedback: `goal`, `task_type`, `scope_id` are re-supplied by the agent even though the server stored them in `context_recall_events` at context-call time.

---

## New Tool Surface

Keep existing names, add one endpoint, make sessions invisible.

```
slowave_context(query, scope?, goal?, task_type?, requirements?, situation?, ...)
  → creates implicit session server-side (fire-and-forget)
  → returns session_id in response (agent receives but does not manage it)

slowave_remember(content, type, scope?, session_id?)  ← unchanged

slowave_recall(query, top_k?, evidence?)              ← unchanged

slowave_feedback(retrieval_id, feedback, used_memory_ids?, outcome?, ...)
  → renamed from slowave_retrieval_feedback
  → server auto-derives goal, task_type, scope_id, session_id,
    situation, requirements from context_recall_events JOIN on retrieval_id

slowave_done(session_id?, outcome?)
  → NEW: replaces session_end + outcome feedback in one optional call
  → idle-timeout auto-closes if never called
```

**Retired (deprecated, kept for compat):** `session_start`, `session_end`, `event`, `retrieval_feedback`, `context_feedback`

**Call counts:** minimum 1, good citizen 3–5, zero per-turn ceremony.

**"breathe_in/breathe_out" rejected** — too poetic, semantically wrong. Reuses existing vocabulary instead.

---

## What We Lose

Without per-turn `event` calls, sessions contain: context query + remember events + done event. `form_episodes` still produces valid micro+macro episodes (remember events get +0.6 salience boost in `ingest.py`).

| Signal lost | Severity | Mitigation |
|---|---|---|
| Conversation arc micro-episodes → TransitionModel training density | Medium | Auto-log context query + done outcome as events server-side (2 per session, zero agent cost) |
| Ambient turn pairs → LoCoMo recall of non-remembered content | Low–Med | Only affects content never explicitly remembered |
| Per-event prediction_surprise salience variance | Low | Computed from remember events |

**Benchmark estimate:** LoCoMo ~3–7pp on ambient-detail queries. LongMemEval/StaleMemory: no regression. Procedural auto-promotion fully preserved.

**Key insight:** A simpler protocol agents actually follow produces better data than a perfect protocol they skip.

---

## Data Contract Review

### `slowave_context` — inputs

| Field | Classification | Reason |
|---|---|---|
| `query` | CRITICAL | Drives encoder, FTS, cosine search, procedure trigger matching |
| `scope` | CRITICAL | ±0.55 activation swing (match +0.20, mismatch −0.35); procedure scope_affinity |
| `goal` | IMPORTANT | Procedure weight 0.25 (highest); `promote_candidates_from_feedback()` hard filter `AND f.goal IS NOT NULL` — without it no procedures ever auto-promote |
| `task_type` | IMPORTANT | Procedure weight 0.15; second component of `(goal, task_type)` auto-promotion grouping key |
| `requirements` | IMPORTANT | Highest penalty weight in procedure scoring (0.30 mismatch); without it incompatible procedures surface |
| `situation` | IMPORTANT | Procedure weight 0.15; feeds `_merge_dict_values()` for auto-promotion situation_signature |
| `limit` | USEFUL | Controls result set; default 8 correct |
| `topics` / `entities` | OPTIONAL | Broaden cue lexical expansion; subsumed by descriptive query |
| `mode` | OPTIONAL | Default "default" always correct |
| `application` | REMOVE | Analytics only; zero effect on retrieval or learning |
| `session_id` (input) | REMOVE | Becomes output only |

### `slowave_context` — outputs

**Keep:** `retrieval_id`, `session_id` (new), `rendered`

**Per-memory keep:** `id`, `text`, `activation`, `source_kind`, `schema_class`, `confidence` (only when < 0.7)

**Per-procedure keep:** `id`, `goal`, `task_type`, `trigger_pattern`, `procedure_steps`, `confidence`, `score`

**Remove echoes:** all input fields echoed back, `count`, `memory_ids`, `procedure_ids`, `retrieval_type`, `context_id`

**Remove per-schema bloat:** `memory_id` (dup), `memory_type` (always "schema"), `rank` (list pos), full `facets` blob, `tags`, `status` (always "active"), `salience` (internal), `supports`, `contradicts`, `needs_review` (default)

**Remove per-procedure bloat:** `memory_id`, `memory_type`, `rank`, `origin_scope_id`, `status`, `success_count`, `failure_count`, `content` (dup of steps), `reason` (default)

**Token reduction:** ~600–800 → ~120–180 tokens per 8 memories (3–5× compression)


---

### `slowave_feedback` — inputs

| Field | Classification | Reason |
|---|---|---|
| `retrieval_id` | CRITICAL | FK to `context_recall_events`; enables all server-side auto-derives |
| `feedback` | CRITICAL | Learning signal → `salience_delta`, `confidence_delta`, `needs_review` on schemas |
| `used_memory_ids` | IMPORTANT | Schemas that get +0.10 salience reinforcement |
| `outcome` | IMPORTANT | Drives procedure `success_count`/`failure_count`; `outcome_reward` |
| `used_procedure_ids` | IMPORTANT | Confidence update + status promotion candidate→active |
| `irrelevant_memory_ids` | IMPORTANT | −0.05 salience penalty |
| `stale_memory_ids` | IMPORTANT | −0.15 salience + `needs_review=True` |
| `wrong_memory_ids` | IMPORTANT | −0.25 salience + `needs_review=True` (strongest negative signal) |
| `irrelevant/stale/wrong_procedure_ids` | IMPORTANT | Confidence decay and demotion |
| `goal` | AUTO-DERIVE | `SELECT goal FROM context_recall_events WHERE context_id = retrieval_id` |
| `task_type` | AUTO-DERIVE | Same JOIN — needed for auto-promotion grouping key |
| `scope_id` | AUTO-DERIVE | Same JOIN — drives `transfer_count` for procedure generalisation |
| `session_id` | AUTO-DERIVE | Same JOIN — evidence table FK |
| `situation` | AUTO-DERIVE | Same JOIN — `_merge_dict_values()` for auto-promotion |
| `requirements` | AUTO-DERIVE | Same JOIN — `_top_list_values()` for auto-promotion |
| `retrieval_type` | AUTO-DERIVE | Infer from prefix: `ctx_` → context, `rec_` → recall |
| `missing_context` | REMOVE | Only active if `cfg.missing_creates_memory=True` (off by default) |
| `notes` | REMOVE | Stored only; zero learning effect |

---

### `slowave_remember` — inputs

| Field | Classification | Reason |
|---|---|---|
| `content` | CRITICAL | Schema text, embedding, FTS, supersession detection |
| `type` | IMPORTANT | `schema_class` + `memory_layer` (+0.12 "profile", +0.06 "domain"); `_eligible()` filter |
| `scope` | IMPORTANT | `scope_id` on schema (±0.55 activation swing); scopes supersession search |
| `session_id` | OPTIONAL | Prevents double episode formation when called mid-session |

**Output:** trim to `{"stored": true, "scope": scope}`. `event_id` never used by any caller.

---

### `slowave_done` — inputs

| Field | Classification | Reason |
|---|---|---|
| `outcome` | IMPORTANT | Applied to most recent context recall for session; drives procedure success/failure counts |
| `session_id` | OPTIONAL | From context response; server finds latest open session if omitted |

**Output:** `{"session_id": sid, "episodes": N}`

---

### `slowave_recall` — unchanged inputs, trimmed outputs

Inputs `query`, `top_k`, `evidence` already minimal — keep as-is.

**Output keep:** `retrieval_id`, `memories[].id`, `memories[].text`, `memories[].activation` (after bug fix), `memories[].reason`, `memories[].source_kind`

**Output remove:** `retrieval_type`, `format`, `query`, `count`, `memory_ids`


---

## Bug: `compact.py` activation calculation

```python
# CURRENT (wrong): schema salience is 0.01–3.0; /20 collapses to 0.0005–0.15
# Every recalled memory appears equally unimportant
activation = min(1.0, max(0.0, salience / 20.0))

# FIX: pass the actual cosine score from search_embedding() through to CompactSchema
# That score is already a 0–1 similarity signal — the correct activation representation
```

---

## Implementation Phases

**Phase 1 — backward-compatible:**
1. `slowave_context` creates implicit session (fire-and-forget); returns `session_id`
2. Idle-watchdog auto-closes sessions (already in `server.py`)
3. `slowave_feedback` JOINs `context_recall_events` to auto-derive all goal/task_type/scope context
4. Fix `compact.py` activation bug
5. Trim output echoes (no DB schema changes needed)
6. Add `slowave_done`

**Phase 2 — deprecate old tools:**
1. Mark `session_start`, `session_end`, `event`, `retrieval_feedback`, `context_feedback` deprecated
2. Update `CLAUDE.md` and `slowave setup` injected prompts to 3-step protocol
3. Update all integration docs

**Phase 3 — optional clean break:**
1. Remove deprecated tools
2. Evaluate folding `slowave_recall` into `slowave_context` with `recall_only=True`

---

## Files to Change

| File | Change |
|---|---|
| `slowave/mcp/server.py` | Implicit session in context; new done tool; trimmed contracts; auto-derive in feedback; deprecate old tools |
| `slowave/mcp/compact.py` | Fix activation score bug |
| `slowave/core/engine.py` | Lazy `session_start` from `context_brief`; new `done()` method |
| `slowave/core/services/feedback.py` | Auto-derive from context snapshot JOIN |
| `CLAUDE.md` | Update to 3-step protocol |
| `docs/install.md` | Update lifecycle instructions |
| `docs/manual_setup.md` | Update lifecycle instructions |
| `integrations/*/README.md` | Update per-client lifecycle instructions |
| `slowave/cli/setup.py` | Update injected system prompts |

---

## Updated Agent Protocol (post-refactor)

```
1. slowave_context(scope, query, goal?, task_type?)
   → get memory brief; implicit session created server-side; returns session_id

2. [for durable facts]:
   slowave_remember(content, type, scope)

3. [on task complete]:
   slowave_done(session_id, outcome)   ← optional but valuable for procedural learning
```


---

## Endpoint Naming — Final Decision

**Date:** 2026-06-10 (same session)

Reviewed all endpoint names against neuroscience first principles. Goal: each name should describe what the *brain* does at that moment, not what the software does.

### Final names

| Old name | New name | Neuroscience basis | Notes |
|---|---|---|---|
| `slowave_context` | **`slowave_activate`** | Spreading activation — cues activate relevant memory traces into working memory | Considered: `prime`, `focus`, `surface`, `orient`, `ground`. `activate` chosen as the most accurate neuroscience term and completely unambiguous |
| `slowave_remember` | **`slowave_remember`** | Intentional encoding — consciously committing something to long-term memory | Kept. Most natural word for what a human does when they want something to stick |
| `slowave_recall` | **`slowave_recall`** | Deliberate retrieval — bringing a memory back into working memory | Already correct |
| `slowave_feedback` | **`slowave_reinforce`** | Dopaminergic reinforcement / Hebbian strengthening — useful memories strengthen, wrong/irrelevant ones suppress | |
| `slowave_done` | **`slowave_consolidate`** | Offline consolidation — hippocampal replay transfers episode to long-term storage (the sleep analogue) | |

### The cognitive cycle in plain English

```
activate    → working memory primed with relevant context
remember    → explicitly encode what matters
recall      → deliberate mid-task retrieval
reinforce   → strengthen what was useful, suppress what wasn't
consolidate → close episode, trigger offline memory consolidation
```

### Naming options considered for the context/retrieval call

- `prime` — cue-triggered priming; accurate but slightly awkward as a verb
- `focus` — attention narrows to task; clean, one syllable, very readable
- `activate` — **chosen** — the actual neuroscience term for spreading activation through memory network
- `surface` — memories surface into working memory when cued; evocative
- `orient` — orienting response when entering new context; precise but less common
- `ground` — situational grounding; implies "get your bearings"



---

## Review Feedback (2026-06-10, post-design)

Code-grounded review against current `server.py`, `compact.py`, `feedback.py`,
`ingest.py`. Direction is right; risks listed below need addressing before Phase 1.

### What the design gets right

| Area | Why it's solid |
|---|---|
| Auto-derive in `slowave_feedback` | Values already persisted in `context_recall_events` at `record_retrieval()` (`feedback.py:75-94`). Single `SELECT ... WHERE context_id = ?` replaces 6 params with zero learning-signal loss. |
| Compact activation bug | Confirmed at `compact.py:71`: salience `[0.01, 3.0]` ÷ 20 collapses to `[0.0005, 0.15]` — every memory looks unimportant. Threading cosine score through `CompactSchema` is the right fix and the highest-leverage change in the doc. |
| Output trimming | Current response echoes ~15 input fields plus dup `memory_id`, constant `memory_type`, list-position `rank`, default-valued `status`/`salience`. 3–5× compression at no information cost. |
| Removing `application`/`notes`/`missing_context` | Verified inert: never gate retrieval; `missing_creates_memory=False` by default; `notes` is pure stored text. Safe to drop. |
| Endpoint name `activate` | Defensible — `context_brief` literally performs spreading activation. |

### Issues to resolve before Phase 1

**1. Implicit session ≠ free — `remember()` still needs a session link.**
If agents skip threading the implicit `session_id`, every `remember()` opens
an ad-hoc session in `engine.remember()` (`engine.py:416`), encoding one
micro+macro episode per claim → near-duplicate fragments + supersession
churn. Specify a server-side current-session-per-scope resolver: keep
`current_session_by_scope` keyed off `(process, scope)`, set on first
`activate()`, used as the default when `remember(session_id=None)`.

**2. "Idle-watchdog auto-closes sessions (already in `server.py`)" is wrong.**
`server.py:710-765` watchdog calls `os._exit(0)` on the *process*, not
`session_end()` on open sessions. Open sessions stay `status='open'` forever
and never form episodes. Phase 1 must add a new session-idle reaper.

**3. Loss of per-turn `event` is bigger than the table admits.** Missing:
(a) macro-episode degenerates into schema duplication — `ingest.py:93-123`
mean-embeds events; with only [activate, remember×N, done] the macro is
dominated by content already in the schemas just written → extra FAISS slots
and `episodes` rows (dedup at `server.py:116-125` masks at read time).
(b) micro window collapses to 1 (`ingest.py:61`), zeroing the TransitionModel
contribution. Mitigation: fire-and-forget server-side logging of the
`activate` query and `consolidate` outcome as actual session events so
micro-windows still get ≥2 events.

**4. `retrieval_type` auto-derive by id prefix is fragile.** Derive from the
`context_recall_events.retrieval_type` column (`schema.sql:235`), not from
`ctx_` / `rec_` string prefixes.

**5. Trimming `memory_ids`/`procedure_ids` breaks `record_retrieval`.**
`feedback.py:67-70` reads them off the response dict. Keep them in the
*internal* response passed to `_bg_record_context_recall`; strip them only
from the value returned to the client.

**6. `slowave_consolidate` name collides with existing CLI.** `slowave
consolidate` already exists (schema consolidation / procedure promotion).
Either pick a different neuro-term for the per-task close (`encode`,
`commit`, `seal`), or rename the existing CLI first
(`slowave reconsolidate` / `slowave replay`).

**7. Drop Phase 3.2.** Folding `recall` into `context(recall_only=True)`
re-introduces the polymorphic-endpoint anti-pattern the rest of the design
removes. `context` is scoped + procedure-matched; `recall` is free semantic
search. Different ranking and shape — keep separate.

### Impact summary

| Dimension | Direction | Magnitude |
|---|---|---|
| MCP calls per task | ↓↓↓ | 8–20 → 1–3 |
| SQLite write contention | ↓↓ | Removes per-turn `event_append` (hottest write path) |
| Episode count growth | ↑ slight | Only if issue #1 path A occurs |
| TransitionModel signal density | ↓ | Acceptable; track the cost |
| Per-memory token cost | ↓↓↓ | ~600–800 → ~120–180 per brief, dominated by activation-bug fix |
| Feedback fidelity | = | Auto-derive matches or beats agent-supplied echoes |
| Procedure auto-promotion | = | Preserved while `goal`/`task_type` flow through `activate` |

### Recommended sequencing

**Ship now (high value, low risk):** activation-bug fix, auto-derive in
`slowave_feedback` reading `retrieval_type` from the DB column (fix #4),
output trimming with internal id arrays preserved (fix #5), session-idle
reaper (fix #2).

**Design carefully before shipping:** implicit-session + `remember()`
fallback resolver (fix #1); rename existing `slowave consolidate` CLI before
adopting the MCP tool name (fix #6).

**Reconsider / drop:** Phase 3.2 (fix #7); validate LoCoMo regression
empirically before deprecating per-turn `event`; if regression exceeds
estimate, keep `slowave_event` as a power-user tool.

---

## Production-Data Validation (2026-06-10)

Inspection of `~/.slowave/slowave.db` after ~1 week of real use (Claude Code +
Cline as primary clients, two active projects: slowave, cimmeria). The data
both validates the refactor motivation and surfaces three pre-existing bugs
that are independent of the redesign.

### Snapshot

| Table | Count | Notes |
|---|---|---|
| sessions | 93 | **44 open, 37 with zero events** |
| raw_events | 127 | dominated by `user_message` (35), `task_complete` (23), `remember:*` (29 across types) |
| episodic_memories | 119 | 73 micro + 46 macro |
| schemas | 44 | 40 active, 4 cleanly superseded |
| semantic_prototypes | 8 | |
| procedural_memories | 2 | only 1 with any feedback (2 succ, 1 fail) |
| context_recall_events | 30 | 21 context, 9 recall |
| context_feedback_events | 7 | 23% feedback rate vs retrievals |
| schema_evidence | 167 | rich linkage |

Scopes are healthy: 25 schemas `project:slowave`, 17 `project:cimmeria`,
2 NULL (personal-life facts). Supersession works (4 cleanly superseded
benchmark results).

### Findings that validate the refactor

**1. Open-session pile-up — 47% of sessions never closed.** 44 of 93 sessions
remain `ended_ts IS NULL`; 31 of those from `claude-code`, 9 from `cline-tui`.
Confirms review fix #2 (process-level watchdog ≠ session reaper). The events in
these open sessions will never form episodes until a real session-idle reaper
is added. A one-shot migration can close them all.

**2. Empty-session noise — 40% of sessions have zero events.** 37 of 93
sessions have no `raw_events` rows (27 from `claude-code`). Sessions were
started, then per-turn event logging was skipped entirely. This is the
strongest empirical argument for the refactor: agents *demonstrably* ignore
the per-turn event ritual in practice. Implicit sessions inside `activate`
eliminate this row class entirely.

**3. Compact-activation bug is hitting production rankings now.** Active-schema
salience distribution: 25 schemas cluster at 1.3–1.8, 7 in the 4–20 range, 7
above 20 (peak 298.6 on `schema #12 "doctor appointment"`). Current
`activation = salience / 20` clamps #12 to 1.0 while collapsing the
spaghetti-preference schema (confidence 0.96, salience 1.4) to 0.07 — a 14×
displayed-activation gap between two equally-confident, equally-valid
memories. The activation-bug fix lands immediately on existing data with no
migration.

**4. Feedback loop is mostly skipped (23%).** Only 7 feedback events vs 30
retrievals. Of the 7: 4 useful, 2 partially_useful, 1 wrong. Auto-derive
reduces the parameter count from ~12 to ~4 — plausibly bumps the response
rate.

**5. Procedural-memory auto-promotion is starved.** Only 2 procedures despite
a week of use. `promote_candidates_from_feedback()` hard-requires
`goal IS NOT NULL`; several of the 30 retrievals omit `goal`. Refactor
correctly keeps `goal`/`task_type` as IMPORTANT inputs — no regression — but
the agent system prompts should be updated to encourage passing them.

### Pre-existing bugs surfaced (independent of refactor)

**A. Salience runaway.** Schema #12 at salience 298.6 is ~200× the median.
Repeated `useful` feedback (+0.10 each) compounds without decay or cap. Add
either `salience = min(salience + delta, MAX_SALIENCE ≈ 10.0)` or an
exponential decay. Independent ticket.

**B. Episode salience flatlined at ~0.01.** Both micro (73) and macro (46)
episodes show avg salience 0.01. Either the TransitionModel barely
contributes (consistent with §"Loss of per-turn `event`" — micro window
collapses to 1 on short sessions) or the `+0.6` boost for `remember:*` events
is not firing. Worth instrumenting. Note: this means the refactor's "signal
loss" from dropping per-turn events is *already* minimal in practice.

**C. `needs_review` never tripping.** 0 schemas flagged despite 1 `wrong`
feedback. Either the wrong-feedback did not land on a `used_memory_id` or the
threshold is not triggered. Independent ticket.

### Data × refactor verdict

| Concern | Verdict |
|---|---|
| Will refactor lose good data? | **No** — schemas, prototypes, evidence, procedures, episodes all preserved. |
| Will refactor fix observable problems? | **Yes** — open-session pile-up, empty-session noise, broken compact activation ranking. |
| Will refactor create new problems on this data? | **Only if review fix #1 is skipped.** Without the implicit-session resolver, every `remember()` opens an ad-hoc session → proliferation of micro+macro episode duplicates. With fix #1, none. |
| Pre-existing bugs the refactor does *not* fix | Salience runaway, flat episode salience, `needs_review` never tripping. Separate tickets. |

### Suggested one-shot cleanup (safe today, independent of refactor)

```sql
-- Drop empty open sessions accumulated by client noise (37 rows)
DELETE FROM sessions WHERE ended_ts IS NULL
  AND NOT EXISTS (SELECT 1 FROM raw_events r WHERE r.session_id = sessions.id);

-- Close all remaining open sessions (one-shot; idle reaper takes over after)
UPDATE sessions SET ended_ts = strftime('%s','now') WHERE ended_ts IS NULL;
```

After cleanup, run `slowave consolidate` to form episodes for the
just-closed sessions that had events.

### Bottom line

Your data is solid and the refactor — with the seven review fixes applied —
strictly helps it. The data itself validates the proposal: 47% open sessions
and 40% empty sessions are direct evidence that the per-turn event ritual is
being ignored in practice, exactly as the design argues. The compact-activation
fix alone will materially improve every recall response against the existing
44 active schemas.

