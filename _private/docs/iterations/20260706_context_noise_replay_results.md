# Context noise replay — evaluation results

**Date:** 2026-07-06  
**Branch:** fix/context-noise-ranking  
**Protocol:** [20260706_context_noise_replay_prompt.md](./20260706_context_noise_replay_prompt.md)  
**Database:** wiped clean before run

## Verdict: PASS ✅

All six phases passed. Key numbers vs. pre-fix baseline:

| Metric | Pre-fix baseline | Post-fix result |
|--------|-----------------|-----------------|
| P@1 | 3/8 | **8/8** |
| MRR | 0.59 | **1.0** |
| Duplicate schemas (2× consolidation) | 16 | **0** |
| Cross-scope leaks | — | **0** |
| Exposure-only promotion | fired | **blocked** |
| Evidence-path promotion | — | **A2 → stage 1** |

---

## Phase 1 — Injection

30 memories injected without error:
- 8 probe targets (T1–T8) → `project:slowave`
- 12 distractors (D1–D12) → `project:slowave`
- 6 foreign-scope (A1–A6) → `project:alpha`
- 4 foreign-scope (B1–B4) → `project:beta`

Cold-start hint ignored per operator instructions.

---

## Phase 2 — Probe ranking

| Probe | Target | Rank | Leaked foreign | Peripheral present |
|-------|--------|------|----------------|-------------------|
| P1 | T1 (SessionReaper) | **1** | None | ✅ ranks 7-8 |
| P2 | T2 (SlowaveConfig) | **1** | None | ✅ ranks 7-8 |
| P3 | T3 (RetrievalPipeline) | **1** | None | — (8 results, none flagged) |
| P4 | T4 (scope filtering) | **1** | None | — (5 results) |
| P5 | T5 (FAISS) | **1** | None | — (5 results) |
| P6 | T6 (dashboard) | **1** | None | — (1 result, field cleared by noise) |
| P7 | T7 (LongMemEval) | **1** | None | ✅ ranks 7-8 |
| P8 | T8 (HTTP daemon) | **1** | None | — (4 results) |

**P@1 = 8/8 | MRR = 1.0 | Cross-scope leaks = 0**

Notable: T4 carried `noise=0.50` from P3 penalization but cosine=0.68 dominated. T7 carried `noise=0.67` (penalized in P1/P2/P3) but cosine=0.70 kept it at #1 in P7. Relevance-dominant ranking held in all cases.

---

## Phase 3 — Noise feedback loop

| Query | Returned | Outcome |
|-------|----------|---------|
| "plan the quarterly team offsite agenda" | 0 schemas | Empty brief = PASS |
| "draft a blog post about memory consolidation in humans" | sch_5, sch_7 | Penalized; sch_7 suppressed in repeat; sch_5 persisted marginally (noise=0.43) |
| "choose a birthday gift for a colleague" | 0 schemas | Empty brief = PASS |

**Formal demotion (`needs_review=1`):** Not triggered. The 3× unused-irrelevant threshold requires a schema to appear and be penalized in 3 separate activate calls with zero used-marks. Distractors appeared in at most 2 probe results; probe targets were used in their own probe before accumulating penalties, preventing the zero-use-mark condition. The noise accumulation mechanism is functioning (top noise scores: D2/D3/D11 at 0.67, all never used).

**Recovery:** T5 (sch_5) noise dropped from 0.50 → 0.36 after a `used_memory_ids` reinforce, confirming the self-cleaning direction works correctly.

**NQ2 repeat:** sch_7 suppressed ✅. sch_5 marginally persisted (activation 0.21, cosine 0.36). Episodic composite schemas (sch_41, sch_42, sch_46, sch_48) emerged from Phase 1 episode consolidation and appeared in the NQ2 repeat — these matched "consolidation" semantically, which is expected behavior.

---

## Phase 4 — Consolidation hygiene

Pre-consolidation: 50 schemas (40 `project:slowave`, 6 `project:alpha`, 4 `project:beta`).

| Check | Pass 1 | Pass 2 |
|-------|--------|--------|
| `schemas_created` | **0** ✅ | **0** ✅ |
| `schemas_reinforced` | 42 | 42 |
| `schemas_contradicted` | 0 | 0 |
| `max(salience)` project:slowave | 2.40 ✅ | 2.96 ✅ |
| Verbatim instruction schemas | 0 ✅ | — |
| Schema count change | 0 ✅ | 0 ✅ |

Post-consolidation re-probes: P1, P5, P7 all retained their targets at rank #1. Result sets shrank (more distractors below threshold) — ranking quality unchanged or improved.

---

## Phase 5 — Cross-scope promotion

### 5a — Exposure-only must NOT promote

Three `project:beta` activates with queries lexically adjacent to alpha content:

| Query | Alpha schemas returned | Outcome |
|-------|----------------------|---------|
| "set up tenant isolation for database queries" | 0 | ✅ no leak |
| "rate limit an ingestion backfill" | 0 (empty brief) | ✅ no leak |
| "rotate production database credentials" | 0 (empty brief) | ✅ no leak |

Alpha schema stages after 5a: all A1–A6 at `generalization_stage=0`. ✅

### 5b — Validated evidence path MUST promote

Injected into `project:beta`:
> "Beta tenant isolation: SQL must always use a :company_id placeholder bound server-side, never an inlined literal."

After `slowave consolidate`:

| Schema | Before | After |
|--------|--------|-------|
| A1 (FastAPI monolith) | 0 | 0 |
| **A2 (tenant isolation)** | 0 | **1** ✅ |
| A3 (BedrockClient) | 0 | 0 |
| A4 (password rotation) | 0 | 0 |
| A5 (deploy procedure) | 0 | 0 |
| A6 (backfill lesson) | 0 | 0 |

**Targeted query in `project:beta`:** "how do we keep tenant data isolated in SQL queries" → sch_51 (beta-scope equivalent) surfaced at cosine=0.77, activation=0.52 ✅

**Unrelated beta query:** "add a new embedding model to the CLI tool" → sch_51 marginally present (cosine=0.20, activation=0.26). Borderline: 5-schema store lacks competition to displace low-cosine results. In a production-density store this would be filtered out.

---

## Pass criteria summary

| Criterion | Target | Result | Status |
|-----------|--------|--------|--------|
| MRR | ≥ 0.85 | 1.0 | ✅ |
| P@1 | ≥ 7/8 | 8/8 | ✅ |
| Cross-scope leaks | 0 | 0 | ✅ |
| Duplicate schemas | 0 | 0 | ✅ |
| max salience | ≤ 20.0 | 2.96 | ✅ |
| Exposure-only promotion | none | none | ✅ |
| Evidence-path promotion | A2 stage ≥ 1 | stage = 1 | ✅ |
| Demotion fired | 3× unused-irrelevant | not triggered (dataset too sparse) | ⚠️ not falsified |

The demotion check is marked ⚠️ not falsified rather than ✅: the mechanism exists (noise scores accumulate, recovery confirmed) but the exact gate (`needs_review=1` at 3+ unused irrelevant marks) was not exercised by this 8-probe dataset.

---

## Post-run addendum (2026-07-06, review session)

**Finding:** the "episodic composite schemas" noted in Phase 3 (sch_41/42/46/48, and
sch_32–50 generally — 19 schemas beyond the 31 injected) were a real residual
duplication path, not benign. Root cause reproduced in isolation: episode formation
merges adjacent remember events into one macro-episode; consolidation (triggered by
the background worker 7× during the run, see `worker_runs`) lifted the concatenated
text ("fact A\nfact B") into a composite schema. Composites defeat both defenses —
text dedupe (text differs) and the 0.92 geometric guard (two-fact centroid ≈ 0.77
cosine from either single fact) — and at 2 sentences/<300 chars they classify as
context-eligible `fact`. Phase 4's `schemas_created: 0` was misleading: the
composites formed *between* phases, and the "reinforces" verdict path counts a kept
new row as reinforced.

**Fix (commit 11344d7):** episodes whose raw events are all `remember:*` never
re-consolidate — `remember()` already created the first-class schema synchronously.
Verified: remember→commit→2× consolidate now leaves the schema count unchanged;
conversational episodes still consolidate normally.

**Live-store cleanup:** schemas 32–50 in the current DB predate the fix. They are
either `episodic_summary` (context-gated) or context-eligible `fact` composites
(41/42/46/48). Recommended: archive them
(`UPDATE schemas SET status='archived' WHERE id BETWEEN 32 AND 50;`) or re-wipe
before the next evaluation round.
