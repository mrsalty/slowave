# Agent Feedback: Proposed Improvements

> **Source:** Claude Code review of slowave (June 2026).  
> **Status:** Pending — pick up tomorrow.  
> **Key constraint:** Every change must be validated as brain-inspired before implementation.

---

## Already shipped (2026-06-09)

### FK error: `event_append` with unknown session_id
**Fix:** `RawLog.session_exists()` + auto-register ad-hoc session in `event_append` + MCP warning for placeholder values.  
**Brain validity:** ✅ Hippocampus encodes continuously without a formal session boundary. Session is a retrieval convenience, not an encoding prerequisite.

---

## Proposed changes

### P1 — Schema temporal decay for volatile memory types
**Effort:** 2–3h | **Brain validity:** ✅

**Problem:** All schema types decay at the same rate (none). A `procedure` from last sprint has the same confidence as a foundational `fact`. Agents give stale advice.

**Proposed change:**
- Add `volatile: bool` to `remember()` and the schema store
- `volatile=True` (default for `procedure`) → steeper confidence decay over time
- `volatile=False` (default for `fact`, `constraint`, `preference`) → slow/no decay
- Decay applied **lazily at retrieval**: `score * decay_factor(age_days, volatile)` — no background job

**Brain analogy:** Synaptic consolidation rates differ by type and rehearsal. Unrehearsed procedural memories weaken faster than consolidated semantic facts (Ebbinghaus forgetting curves).

**Open questions:**
1. Per-type default + per-instance override? → Yes, both.
2. Decay function? → Exponential. Suggested default: 30-day half-life for `volatile=True`.
3. Lazy or eager? → Lazy (compute at retrieval, never write back — keeps store append-friendly).

**Files:** `slowave/latent/schema.py`, `slowave/symbolic/schema_store.py`, `slowave/core/engine.py`, `slowave/mcp/server.py`

---

### P2 — Memory age in recall output (stopgap only — do P1 first)
**Effort:** 30 min | **Brain validity:** ⚠️

The brain doesn't surface raw age to the cortex — forgetting curves handle staleness implicitly through retrieval strength. `age_days` as a field is a workaround for the missing decay, not a brain-inspired feature.

**Recommendation:** Implement P1 first. Retrieval score will then encode staleness naturally. If P1 is blocked, add `_debug_age_days` (underscore prefix = temporary) as a stopgap.

---

### P3 — Return `auto_session_id` from implicit session creation
**Effort:** 1h | **Brain validity:** ✅

**Problem:** Today's ad-hoc fix auto-registers a session but doesn't return the generated ID. Agents can't chain follow-up events to it without calling `session_start`.

**Proposed change:** When `session_id=None` is passed to `event_append`, auto-create a session and return both `event_id` and `auto_session_id`. Agent can use `auto_session_id` for all subsequent events — zero ceremony.

**Brain analogy:** Hippocampal encoding is continuous; no "start recording" signal is required.

**Files:** `slowave/core/engine.py`, `slowave/mcp/server.py`

---

### P4 — Simplified feedback tool
**Effort:** 45 min | **Brain validity:** ✅

**Problem:** `slowave_retrieval_feedback` has 15+ params. Agents use 1–2; the rest is noise.

**Proposed change:** `slowave_feedback(retrieval_id, signal: "useful"|"not_useful"|"wrong", note?)` as a thin alias. Full tool stays for power use.

**Brain analogy:** Dopaminergic reward signals are scalar. The reinforcement signal modulating synaptic weights is simple — the 15-field breakdown is an analytical overlay.

**Files:** `slowave/mcp/server.py`, `slowave/core/services/feedback.py`

---

### P5 — Make `scope` prominent / near-required
**Effort:** 15 min | **Brain validity:** ✅

**Problem:** `scope` is optional but is the primary mechanism preventing cross-project memory bleed. Agents routinely omit it.

**Changes:**
- `slowave_session_start` description: mark `scope` as *strongly recommended* for project work
- `slowave_recall` description: note cross-scope bleed risk when scope omitted
- `CLAUDE.md`: add "Always set scope=project:X for sustained project work"

**Brain analogy:** Hippocampal retrieval is context-sensitive — environmental cues gate recall. Scope is the context cue.

**Files:** `slowave/mcp/server.py` (docstrings), `CLAUDE.md`

---

### P6 — Document what NOT to store in `remember()`
**Effort:** 10 min | **Brain validity:** ✅

**Problem:** Agents over-store ephemeral state (current PR, in-progress bug) polluting the schema store.

**Addition to `slowave_remember` description:**
> Use for durable architectural facts, constraints, preferences, and procedures that repeat across sessions.  
> Do NOT store ephemeral task state (current PR, in-progress bug, temp workarounds) — that belongs in session events and is encoded into episodic memory automatically.

**Brain analogy:** Semantic LTM stores durable knowledge; working memory handles transient state. The brain filters most working memory out before consolidation.

**Files:** `slowave/mcp/server.py` (docstring only)

---

## Implementation order

| # | Item | Effort | Brain validity | Impact |
|---|------|--------|---------------|--------|
| 1 | P6 — `remember()` docstring: what NOT to store | 10 min | ✅ | Medium |
| 2 | P5 — `scope` prominent + CLAUDE.md note | 15 min | ✅ | Medium |
| 3 | P4 — Simplified `slowave_feedback` alias | 45 min | ✅ | Medium |
| 4 | P3 — Return `auto_session_id` from implicit session | 1h | ✅ | High |
| 5 | P1 — Schema temporal decay for volatile types | 2–3h | ✅ | High |
| 6 | P2 — `_debug_age_days` stopgap (only if P1 blocked) | 30 min | ⚠️ | Low |
