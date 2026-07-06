# Enforcing the slowave memory cycle

**Date:** 2026-07-06
**Context:** Observed that an agent performing a thorough investigation (two bugs fixed across consolidation/decay pipeline, working-memory gate, and MMR dedup) called `slowave_remember` only twice — and only during the first task. The second investigation (Phase 7 decay) produced zero `remember` calls despite uncovering durable facts about `_write_latent_schema`, `reinforce_schema` salience deltas, `decay_unused` eligibility, and the `prototypes_for_episodes([])` all-prototypes behavior.

The agent confirmed: tunnel-vision on the fix suppressed the encode step. The fix is transient; the *understanding* is what a future session needs.

---

## Problem

The 5-step slowave cycle is structurally present but `remember` is treated as optional:

| Step | Instructions | Agent behavior |
|------|-------------|----------------|
| 1. `activate` | "before your first response" — clear gate | Always called |
| 2. `remember` | "call per durable fact" with novelty gate | Skipped when fix-focused |
| 3. `recall` | "only when activate fell short" | Only when needed |
| 4. `reinforce` | "after ANY retrieval" | Called when activate returned memories |
| 5. `commit` | "always — non-negotiable" | Always called |

The gap: an agent can run activate → commit with zero `remember` calls and the system silently accepts it. The knowledge base starves while the ritual looks complete.

---

## Proposed enforcement mechanisms

### 1. Reframe `remember` as the purpose, not a sidecar (low effort, high impact)

Flip the system-prompt language. Currently `remember` reads as an optional encode step. Replace with:

> **The purpose of this cycle is to write durable knowledge into memory.** Activate finds context, recall fills gaps, reinforce tunes retrieval — but `remember` IS the point. If you finish an investigation and called `remember` zero times, you wasted the session. No exceptions.

Make it as loud as activate/commit. Remove the soft "novelty gate" framing that invites judgment calls.

### 2. `commit` should warn or reject empty sessions (medium effort)

If `episodes_formed == 0` and zero `remember` calls were made, `commit` returns a diagnostic:

```json
{
  "session_id": "...",
  "episodes_formed": 0,
  "warning": "no durable knowledge encoded — did you learn nothing?",
  "hint": "call slowave_remember(content, type, scope) for facts worth keeping"
}
```

Optionally: hard-reject after N warnings. A client-side counter (`empty_sessions_in_a_row`) could escalate.

### 3. Consolidation should detect missed-opportunity sessions (medium effort)

The consolidate pass already processes session events. Add a heuristic:

- Tag sessions where `event_count > threshold` (many reads, edits, searches = investigation) but `remember_count == 0`
- Store `missed_encoding_opportunity: true` on the session
- Accumulate a scope-level metric: `empty_investigation_sessions / total_sessions`

### 4. `activate` should surface scope-level encoding health (low effort)

On activate, include a health line in the rendered output:

```
[14 of 47 sessions in this scope encoded nothing — prior agents investigated but rarely remembered]
```

This makes the gap VISIBLE at session start, creating social/behavioral pressure.

### 5. `cold_start` hint when scope has sessions but few schemas (low effort)

Currently cold start says "Memory is empty." Add context when the scope ISN'T empty but has a poor schema-to-session ratio:

```
No memories found, but this scope has 47 prior sessions and only 3 schemas. 
Agents investigated but rarely called remember. Encode anything durable you discover.
```

---

## Recommendation

Start with (1)+(5)+(4) — all low-effort prompt/output changes. They create immediate visibility without API changes. Follow with (2) — the hard gate — once the behavioral patterns shift. (3) is a nice-to-have consolidation-time signal that can wait.

The core insight: the system currently trusts agents to self-regulate encoding. Agents under fix-pressure won't. The system must make the gap impossible to ignore.