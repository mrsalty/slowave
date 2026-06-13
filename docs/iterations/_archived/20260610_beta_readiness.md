# Beta Readiness — Next Steps
_Generated: 2026-06-10_

---

## Context

Slowave is currently at v0.4.9 / just shipped 0.5.0 (UX Refactor Phase 1, hard breaking MCP tool surface change). PyPI classifier is still `Development Status :: 3 - Alpha`. This document captures the next steps needed to credibly call Slowave **beta**.

---

## 🔴 Blockers

### 1. Schema Migration Story
`docs/limitations.md` explicitly says: _"We do not yet guarantee schema migration between versions."_

This is the single most user-hostile thing to leave open before beta. The 0.5.0 release introduced a hard breaking change (full MCP tool surface replaced), and users who upgrade have no safe migration path for their existing `~/.slowave/slowave.db`.

- **Schema versioning**: stamp the DB with a schema version at creation time.
- **Migration runner**: `slowave migrate` or auto-migration on startup via `init_schema` (already has migration logic, but needs to cover all past-to-current paths).
- Document what `slowave setup` does to an existing DB on upgrade.

### 2. Promote PyPI Classifier from Alpha → Beta
`pyproject.toml` still has `Development Status :: 3 - Alpha`. The classifier is the visible stability gate for users. Updating it requires the migration story to be solid plus a few stability commitments below — but it is the single most visible signal to the ecosystem.

---

## 🟡 High Priority

### 3. Lifecycle Reliability & Error Paths

The 5-verb cycle introduced in 0.5.0 needs hardening:

- **`slowave_activate` cold-start path**: on a blank DB the cold-start response instructs the agent to read README.md — fine for this repo, potentially confusing for end-users. Needs a cleaner empty-state response.
- **`slowave_commit` robustness**: if an agent crashes mid-session without calling `commit`, the session-idle reaper fires after 1 hour. That's correct behavior, but up to 1 hr of data could be in limbo. Surface this in `slowave doctor`.
- **`slowave_reinforce` with stale/invalid `retrieval_id`**: should degrade gracefully with a clear error, not silently drop.

### 4. `slowave doctor` Coverage for 0.5.0

The `doctor` command was built during 0.1.x. After 0.5.0's breaking tool surface change, it may not validate:
- Whether the correct 5-verb tool definitions are injected in each client's MCP config.
- Whether an old pre-0.5.0 config (with `slowave_context`, `slowave_session_start`, etc.) is still lurking.
- DB schema version vs expected version.

A `doctor` that catches "you have an old config" dramatically reduces upgrade support burden.

### 5. Test Coverage Gaps for the 0.5.0 MCP Surface

`test_old_tools_deleted.py` and `test_reinforce_autoderive.py` exist in `tests/integration/`, and `test_session_reaper.py` exists in unit tests. Still missing:
- Unit test for `session_resolver.py` cold-start path (implicit session threading when no prior `activate` in scope).
- Unit test for `slowave_remember` without a prior `activate` (session inference fallback).
- Unit test for `slowave_activate` on a blank DB (empty-state behavior).

### 6. Windows Compatibility Completeness

There is a fix for `SIGHUP` (guarded signal registration), but Windows support is essentially untested. If Windows isn't fully supported, `slowave setup` should say so explicitly rather than silently misconfiguring.

---

## 🟢 Nice-to-Have (Stretch Goals)

### 7. Benchmarks — Independent Verification

The benchmarks page is admirably honest: _"Alpha-stage numbers. Internal runs, not independently verified."_ For beta, the single highest-credibility move is to have **one external person run the reproduction script** on the LoCoMo eval and post the result. The scripts are already published. Even one verified external number transforms the benchmark section's credibility.

### 8. `slowave setup` — Idempotency on Upgrade

The README says `slowave setup` is idempotent. But with the 0.5.0 tool surface change, re-running setup on an existing install needs to **replace** old tool definitions, not append. Worth a specific test/smoke for the upgrade path.

### 9. Preference Inference Gap (Partial Mitigation)

The 20 pp gap on `single-session-preference` in LME (76.7% vs Mem0 96.7%) is the most visible benchmark weakness. One pragmatic mitigation that doesn't violate the zero-LLM constraint: **pattern-match explicit preference markers** at `remember()` time (phrases like "I prefer…", "I usually…", "please always…") and flag those schemas with a `preference` type + higher salience. Wouldn't close the implicit inference gap but would reduce the explicit preference miss rate.

---

## Summary Roadmap to Beta

| Priority | Item | Effort |
|---|---|---|
| 🔴 Blocker | Schema migration guarantee + `slowave migrate` | Medium |
| 🔴 Blocker | Promote classifier to Beta + stability promise | Trivial |
| 🟡 High | `slowave doctor` 0.5.0 config detection | Small |
| 🟡 High | `slowave_activate` empty-state / cold-start UX | Small |
| 🟡 High | Unit test coverage for session_resolver cold path | Small |
| 🟡 Medium | Windows setup completeness or explicit unsupported notice | Small |
| 🟢 Nice-to-have | One external benchmark verification | External |
| 🟢 Nice-to-have | Preference schema type tagging at `remember()` time | Small |

---

## Bottom Line

The **#1 thing** holding this back from a credible beta label is the **migration story** — everything else is polish. Once users can upgrade without fear of losing their memory store, the rest is about confidence building.
