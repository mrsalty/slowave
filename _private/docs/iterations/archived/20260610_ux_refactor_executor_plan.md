# UX Refactor — Executor Plan (Phase 1, hard break)

**Source design:** `docs/iterations/20260610_ux_refactor_design.md`
**Branch:** `feat/ux-refactor-phase1` from `main` (`845abc3`)
**Compatibility policy:** hard break — old MCP tools are deleted.
**Reading order:** design doc first, then this doc.

This document tells the executor *what* to do, *how to validate* each step,
and *what to document*. It deliberately does not include code: implement
each step from first principles, guided by the design doc, the existing
`server.py` / `compact.py` / `feedback.py` patterns, and the acceptance
criteria below.

---

## Resolved design decisions (reference)

| # | Decision | Resolved |
|---|---|---|
| D1 | Per-task close verb | `slowave_commit` |
| D2 | Naming | Full rename: `activate / remember / recall / reinforce / commit` |
| D3 | Old tools | Hard break — delete in Phase 1 |
| D4 | Implicit session | In-memory per-scope map, 1h age guard, code-documented |
| D5 | Synthetic events | Server logs `activate` query + `commit` outcome as events |
| D6 | Session reaper | 60 min default, new env `SLOWAVE_SESSION_IDLE_TIMEOUT` |
| D7 | `retrieval_type` source | DB column `context_recall_events.retrieval_type` |
| D8 | Deprecated feedback args | Removed from signature entirely |
| D9 | Compact activation fix | `recall` only; `context/activate` already uses gate score |
| D10 | Auto-fire feedback on commit | No — enforce explicit feedback via setup prompts |
| D11 | Regression gates | ≤5pp LoCoMo, 0pp LongMemEval, full unit suite green |

---

## Final endpoint surface (post-Phase 1)

The new cognitive cycle:

```
activate    → prime working memory with context; opens implicit session
remember    → encode a durable typed claim
recall      → semantic retrieval mid-task
reinforce   → strengthen / suppress memories from a retrieval
commit      → close the task; form episodes
```

| New MCP tool | Replaces (deleted) | Behaviour notes |
|---|---|---|
| `slowave_activate` | `slowave_context`, `slowave_session_start` | Implicit session opens server-side; returns `session_id` (informational); fires synthetic `context_query` event |
| `slowave_remember` | `slowave_remember` (kept) | Session inferred from per-scope resolver if not passed |
| `slowave_recall` | `slowave_recall` (kept) | Threads cosine activation; trimmed output |
| `slowave_reinforce` | `slowave_retrieval_feedback`, `slowave_context_feedback` | Auto-derives goal/task_type/scope/session/situation/requirements/retrieval_type from DB |
| `slowave_commit` | `slowave_session_end` | Closes session; fires synthetic `task_complete` event; clears resolver binding |
| `slowave_stats` | unchanged | |
| `slowave_remember_procedure` | unchanged | |

**Deleted Phase 1:** `slowave_context`, `slowave_session_start`,
`slowave_session_end`, `slowave_event`, `slowave_retrieval_feedback`,
`slowave_context_feedback`.

---


## Pre-flight (do once, in order)

**P1. Environment**
- Working tree clean. New branch `feat/ux-refactor-phase1` from `main`.
- `uv sync` (or `pip install -e ".[dev]"`).
- Run the full test suite. **Must be green. STOP if not.**
- Stash baseline output to `/tmp/baseline_tests.txt`.

**P2. DB cleanup migration** (`scripts/migrations/20260610_cleanup_sessions.sql`)
- Single idempotent transaction:
  - DELETE sessions with `ended_ts IS NULL` AND no `raw_events` rows.
  - UPDATE remaining open sessions to `ended_ts = now()`.
- Apply against a backup copy of `~/.slowave/slowave.db`.
- Run `uv run slowave consolidate` afterwards.
- **Validate:** `SELECT COUNT(*) FROM sessions WHERE ended_ts IS NULL` returns `0`.
- Commit message: `chore(db): one-shot cleanup of empty + stale-open sessions`.

**P3. Baseline benchmarks (D11 gate)**
- If a LoCoMo / LongMemEval runner exists under `tests/temporal_eval/`,
  run it and stash to `/tmp/baseline_bench.txt`. If absent, document in the
  PR that the regression gate is unit-tests-only.

---

## Step order

Implement steps 1–8 **in order**. Each step ends with: acceptance tests
green, conventional commit, brief PR note.

| # | Step | Risk |
|---|---|---|
| 1 | Fix compact-activation bug; thread cosine through `recall` | low |
| 2 | Implicit-session resolver (per-scope, in-memory, 1h TTL) | medium |
| 3 | Server-side synthetic event logging | low |
| 4 | Session-idle reaper (60-min default) | medium |
| 5 | `feedback.py` auto-derive from `context_recall_events` | medium |
| 6 | New MCP tool surface; delete old tools | medium |
| 7 | Client integration updates | low |


---

## Step 1 — Compact activation fix + cosine passthrough

**Goal.** `compact.py:CompactSchema.from_schema` currently maps salience to
activation via `/20`, collapsing typical values to ~0.07. Replace with: (a)
explicit `activation` parameter; (b) saturating fallback over salience.

**Where to change.**
- `slowave/mcp/compact.py` — change `from_schema` to accept
  `activation: float | None = None`; fix fallback math (log-saturating).
- `slowave/core/services/retrieval.py` — extend `RecallResult` with
  `schema_activations: dict[int, float]`; populate inside `recall()` from
  existing `schema_scores`.
- `slowave/core/engine.py` — sync the duplicate `RecallResult` dataclass.
- `slowave/mcp/server.py` — in `slowave_recall`, pass the activation through.

**Acceptance** (`tests/unit/test_compact_activation.py`):
- Explicit `activation` preserved verbatim.
- Fallback for salience `1.4` returns > 0.2 (old bug returned ~0.07).
- Fallback for spike (`298.6`) saturates in `(0.9, 1.0]`.

**Validate end-to-end.** Run `slowave recall "<query>"` against a temp DB
and confirm activations are not uniformly tiny.

**Document.** PR description bullet under "Behaviour changes": *Recall
activations now reflect cosine similarity; salience fallback uses a
saturating curve.*

**Commit.** `fix(mcp): thread cosine activation through CompactSchema`.

---

## Step 2 — Implicit-session resolver

**Goal.** Fast, scope-keyed lookup so `slowave_remember(session_id=None)`
can find the implicit session opened by `slowave_activate`.

**Where.** New module `slowave/mcp/session_resolver.py`.
Public API: `bind(scope, session_id)`, `resolve(scope) -> str | None`,
`clear(scope)`, `snapshot()`.

**Design constraints.**
- In-process, thread-safe (`threading.Lock`).
- Stored value: `(session_id, set_at_ts)`.
- `resolve()` drops entries older than `MAX_IMPLICIT_SESSION_AGE_S = 3600`
  (1 hour) and returns `None` (→ caller falls back to ad-hoc).
- Key is `scope` (string or `None`). One binding per scope.
- Module docstring must document: why in-memory not DB, why the age guard,
  what happens on process restart.

**Wiring is done in Step 6.** `activate` calls `bind`; `remember` calls
`resolve` when `session_id is None`; `commit` calls `clear`.

**Acceptance** (`tests/unit/test_session_resolver.py`):
- bind → resolve returns the bound id.
- resolve on unknown scope returns None.
- After artificially backdating an entry past TTL, resolve returns None
  and removes the entry.
- clear() removes the binding.
- Two scopes are isolated.

**Commit.** `feat(mcp): add per-scope implicit session resolver with 1h age guard`.

---

## Step 3 — Server-side synthetic event logging

**Goal.** Compensate for the removal of per-turn `slowave_event` by writing
two synthetic events per task: `context_query` (on activate) and
`task_complete` (on commit). Keeps `ingest.py` micro-window meaningful.

**Where.** Inside the new `slowave_activate` / `slowave_commit` bodies (Step
6). Use the existing `_bg_*` fire-and-forget pattern. Log via
`eng.event_append`. Never block the response.

**Acceptance.** Covered by Step 6's `test_lifecycle_minimal.py`: assert
`raw_events` count ≥ 2 after a full `activate → remember → commit` cycle
with no explicit `event` calls.

**Commit.** Folded into the Step 6 commit.

---

## Step 4 — Session-idle reaper (60-min default)

**Goal.** Real session-level reaper, distinct from the existing process
watchdog. Closes sessions whose last event is older than
`SLOWAVE_SESSION_IDLE_TIMEOUT` (default `3600`) via
`session_end(consolidate=False)`. Disable with `=0`.

**Where.** New module `slowave/mcp/session_reaper.py`:
- `start(build_engine, poll_interval_s=120) -> threading.Thread | None`
- `_reap_once(build_engine, timeout_s) -> list[str]` (testable seam)

**Reaper SQL idea.** Sessions with `ended_ts IS NULL` AND
`COALESCE(MAX(raw_events.ts), sessions.started_ts) < now - timeout_s`
(LEFT JOIN).

**Wiring.** `session_reaper.start(...)` from `server.main()`, after the
existing process-watchdog block, before `mcp.run()`.

**Acceptance** (`tests/unit/test_session_reaper.py`):
- An old open session with no events is closed by `_reap_once(timeout_s=0)`.
- A session with a fresh `event_append` is *not* closed by
  `_reap_once(timeout_s=3600)`.

**Validate manually.** Set `SLOWAVE_SESSION_IDLE_TIMEOUT=10`, run the MCP
server, call `activate`, wait 15s, inspect DB: session closed, episodes
formed.

**Document.** README + CHANGELOG: new env var
`SLOWAVE_SESSION_IDLE_TIMEOUT`, default 3600, distinct from
`SLOWAVE_MCP_IDLE_TIMEOUT`.

**Commit.** `feat(mcp): add session-idle reaper (default 60 min)`.

---

## Step 5 — Feedback auto-derive

**Goal.** Strip redundant inputs from `retrieval_feedback`; fill from
`context_recall_events` via single SELECT keyed on `retrieval_id`.

**Where.** `slowave/core/services/feedback.py:retrieval_feedback()`.

**New contract (kept inputs).**
- `retrieval_id`, `feedback`, `outcome`
- `used_memory_ids`, `irrelevant_memory_ids`, `stale_memory_ids`,
  `wrong_memory_ids`
- `used_procedure_ids`, `irrelevant_procedure_ids`,
  `stale_procedure_ids`, `wrong_procedure_ids`

**Dropped inputs (now DB-derived).** `retrieval_type`, `session_id`,
`scope_id`, `goal`, `task_type`, `situation`, `requirements`,
`missing_context`, `notes`.

**Behaviour on missing parent row.** Keep today's fallback path (insert
feedback with nulls); do not crash.

**Acceptance.** Extend `tests/unit/test_context_feedback.py`:
- Record a context with explicit `goal=g1`, `task_type=tt1`,
  `scope_id=s1`, `situation={"x":1}`, `requirements=["r"]`.
- Call new-minimal-signature `retrieval_feedback`.
- Assert the inserted `context_feedback_events` row carries those values.
- Add a test for unknown `retrieval_id`: writes feedback row with NULLs,
  does not crash.

**Document.** Update the function docstring listing each auto-derived field
and its DB source.

**Commit.** `refactor(feedback): auto-derive context fields from DB; drop redundant inputs`.



---

## Step 6 — New MCP tool surface; delete old tools

**Goal.** Implement the 5-verb surface and delete old tools in one commit.

**Where.** `slowave/mcp/server.py` only.

### 6.1 `slowave_activate`
- Inputs: `query` (required), `scope?`, `goal?`, `task_type?`,
  `situation?`, `requirements?`, `topics?`, `entities?`, `mode?`, `limit?`.
- Behaviour:
  1. Open implicit session via `eng.session_start(agent="mcp", scope=…)`.
  2. `session_resolver.bind(scope, sid)`.
  3. Call `eng.context_brief(...)` and `eng.retrieve_procedures(...)`.
  4. Build the trimmed public response (see 6.5).
  5. Schedule `_bg_record_context_recall(...)` with the full internal payload.
  6. Schedule `_bg_log_event(eng, sid, "context_query", query)`.
- Public return: `{retrieval_id, session_id, rendered, schemas[], procedures[]}` (+ `activation_trace` when `mode=="debug"`).

### 6.2 `slowave_remember`
- Inputs: `content`, `type`, `scope?`, `session_id?`.
- Behaviour: if `session_id is None`, resolve via
  `session_resolver.resolve(scope)`; pass result to `eng.remember(...)`.
- Return: `{event_id, type, scope}`.

### 6.3 `slowave_recall`
- Inputs unchanged.
- Behaviour identical to today except `CompactSchema.from_schema` receives
  `activation=r.schema_activations.get(s.id)` (Step 1).
- Public output: drop `query`, `format`, `count`, `retrieval_type`,
  `memory_ids`. Keep `retrieval_id`, `memories[]`.

### 6.4 `slowave_reinforce`
- Inputs: per Step 5 contract.
- Behaviour: delegate to `eng.retrieval_feedback(...)`.

### 6.5 `slowave_commit`
- Inputs: `outcome?`, `scope?`, `session_id?`.
- Behaviour:
  1. Resolve `session_id` from `session_resolver` if not provided.
  2. Schedule synthetic event `task_complete` with `outcome` payload.
  3. Call `eng.session_end(sid, consolidate=False)`.
  4. `session_resolver.clear(scope)`.
  5. Return `{session_id, episodes}`.
- **Do not** auto-fire feedback (D10).

### 6.6 Delete old tools
Remove `slowave_context`, `slowave_session_start`, `slowave_session_end`,
`slowave_event`, `slowave_retrieval_feedback`, `slowave_context_feedback`.
Update module docstring.

### 6.7 Acceptance tests
- `tests/integration/test_lifecycle_minimal.py`: activate → remember
  (session_id=None) → commit. Assert single `session_id` flows through;
  `ended_ts` set; `raw_events` ≥ 2; ≥ 1 episode formed; resolver cleared.
- `tests/integration/test_reinforce_autoderive.py`: activate with `goal=g1`,
  `task_type=tt1`; reinforce with new minimal signature; assert
  `context_feedback_events` row has `goal='g1'` and `task_type='tt1'`.
- `tests/integration/test_old_tools_deleted.py`: inspect `FastMCP` registry;
  assert the six old tool names are absent.

**Expected casualties.** `tests/unit/test_remember_session.py` if it imports
old tool names. Confirm `tests/unit/test_context_feedback.py` after Step 5.

**Commit.** `feat(mcp): new endpoint surface (activate/remember/recall/reinforce/commit); delete old tools`.

---

## Step 7 — Client integration updates

**Goal.** Move every doc / injected prompt to the new surface. Enforce
explicit feedback (D10).

**Find usages.**
`rg -l 'slowave_(context|session_start|session_end|event|retrieval_feedback|context_feedback)'`
— expected: `CLAUDE.md`, `slowave/cli/setup.py`, `docs/install.md`,
`docs/manual_setup.md`, `integrations/*/README.md`.

**Document this protocol in every affected file.**
1. Task start: `slowave_activate(scope, query, goal, task_type)`.
2. Per durable fact: `slowave_remember(content, type, scope)`.
3. Mid-task lookup: `slowave_recall(query)`.
4. **Mandatory after using retrieved memories:**
   `slowave_reinforce(retrieval_id, feedback, outcome, used_memory_ids)`.
   State plainly: *Feedback is not auto-fired; if you skip it, slowave
   cannot learn.*
5. Task end: `slowave_commit(scope, outcome)`.

**Acceptance.**
- `rg` for old tool names across `docs/`, `integrations/`, `CLAUDE.md`,
  `slowave/cli/setup.py` returns nothing.
- `uv run slowave setup --dry-run` emits prompts referencing the 5 new
  tools and the explicit-feedback rule.

**Commit.** `docs: update client integrations and setup prompts for new MCP surface`.



---

## Step 8 — Regression gate + PR

**Goal.** Prove the refactor meets D11 thresholds.

**Run.**
- `uv run pytest -x -q` — must be green.
- If a LoCoMo / LongMemEval harness exists, run and diff against the P3
  baseline.
  - Block merge if LoCoMo regression > 5pp.
  - Block merge if LongMemEval regression > 0pp.

**Manual end-to-end smoke.**
1. Temp DB. Configure Claude Code / Cline against the branch.
2. Run a real-ish task: activate → remember×3 → recall → reinforce → commit.
3. DB checks:
   - 1 session, `ended_ts` non-null.
   - ≥ 4 `raw_events` including `context_query` and `task_complete`.
   - ≥ 1 episode formed.
   - 1 row each in `context_recall_events` and `context_feedback_events`.
   - ≥ 1 schema created.

**PR description checklist.**
- [ ] Pre-flight cleanup migration applied and validated.
- [ ] Each step 1–7 has its own commit and is independently revertible.
- [ ] Acceptance tests per step present and green.
- [ ] Regression numbers vs baseline reported.
- [ ] CHANGELOG entry written.
- [ ] README + CLAUDE.md updated.
- [ ] Manual smoke transcript attached.

**CHANGELOG (under "Breaking changes").**
- MCP tool surface replaced. Old tools (`slowave_context`,
  `slowave_session_*`, `slowave_event`, `slowave_*_feedback`) removed.
  New tools: `slowave_activate`, `slowave_remember`, `slowave_recall`,
  `slowave_reinforce`, `slowave_commit`.
- New env var `SLOWAVE_SESSION_IDLE_TIMEOUT` (default `3600`).
- Bug fix: recall activations now reflect real similarity.

**Tag.** `v0.X.0-uxrefactor` once merged.

---

## Out of scope for Phase 1

- Renaming the existing `slowave consolidate` CLI (D1's `commit` resolves
  the collision; deferred).
- Folding `recall` into `activate` (design §"Phase 3.2 — drop it").
- Salience runaway fix (separate ticket).
- Episode salience flatline investigation (separate ticket).
- `needs_review` threshold tuning (separate ticket).

---

## Rollback plan

1. `git revert` of the Step 6 commit alone restores the old tool surface;
   Steps 1–5 are internal improvements and can stay.
2. The P2 cleanup migration is one-way for empty sessions but harmless;
   `~/.slowave/slowave.db.bak-pre-ux-refactor` is the full DB rollback.
3. `SLOWAVE_SESSION_IDLE_TIMEOUT=0` disables the new reaper without code
   change.

---

## Validation summary (one-glance)

| Step | Unit test file | Integration test file |
|---|---|---|
| 1 | `tests/unit/test_compact_activation.py` | — |
| 2 | `tests/unit/test_session_resolver.py` | — |
| 3 | — | covered by Step 6 lifecycle test |
| 4 | `tests/unit/test_session_reaper.py` | — |
| 5 | extend `tests/unit/test_context_feedback.py` | — |
| 6 | — | `test_lifecycle_minimal.py`, `test_reinforce_autoderive.py`, `test_old_tools_deleted.py` |
| 7 | — | `rg` sweep returns nothing |
| 8 | full suite | LoCoMo / LongMemEval diff |

| 8 | Regression gate + PR | mandatory |
