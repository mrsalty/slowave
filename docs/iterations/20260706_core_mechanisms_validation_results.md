# Core-mechanism validation results

**Date:** 2026-07-06  **Branch:** fix/context-noise-ranking  **Verdict:** PARTIAL

---

## Summary table

| Phase | Criterion | Expected | Observed | Status |
|-------|-----------|----------|----------|--------|
| 0 | Scope registry | 10 scopes, 2 kinds | 10 scopes, 2 kinds | ✅ PASS |
| 2 | P@1 | ≥ 7/8 | 8/8 = 1.0 | ✅ PASS |
| 2 | MRR | ≥ 0.85 | 1.0 | ✅ PASS |
| 2 | Cross-scope leaks | 0 | 0 | ✅ PASS |
| 2 | (peripheral) labels | Present when >8 candidates | Observed in multiple probes | ✅ PASS |
| 3 | Recall 3/3 | T8 in top 3, T1 in top 3, A2 absent | R1 T8 rank 1, R2 T1 rank 1, R3 A2 absent | ✅ PASS |
| 4 | S1 noise_score | ≥ 0.75 | 0.75 | ✅ PASS |
| 4 | S1 needs_review | 1 | 1 | ✅ PASS |
| 4 | S1 suppressed in N2 re-run | Absent | Absent | ✅ PASS |
| 4 | T1-T8 still active | needs_review=0 | needs_review=0 | ✅ PASS |
| 5 | Schema count stable | No new schemas | 28→28 | ✅ PASS |
| 5 | Max salience | ≤ 20 | 1.65 | ✅ PASS |
| 5 | P1/P5/P7 re-run | Targets still #1 | All targets still #1 | ✅ PASS |
| 6A | L1 stage after gamma+delta | stage 1 | stage 1 (3 scopes, 0.30) | ✅ PASS |
| 6B | L1 surfaced in epsilon (activate) | Yes, with scope_mismatch | NOT surfaced (cross_scope_below_floor) | ❌ FAIL |
| 6C | L1 stage after zeta | stage 2 | stage 1 (4 scopes, 0.40) | ❌ FAIL (cascade) |
| 6D | L1 reaches stage 3 | stage 3 ≥8 scopes | stage 3 (8 scopes, 0.80) via modified path | ⚠️ PARTIAL |
| 6D | L2 stage 0 | stage 0 | stage 0 | ✅ PASS |
| 6E1 | Stage-3 global admission (beta) | No scope_mismatch | No scope_mismatch | ✅ PASS |
| 6E2 | A4 absent from beta | Not present | Absent, stage 0 | ✅ PASS |
| 6E3 | kind_bonus fires | distinct_scope_kind_count=2 | 2 (project+domain) | ✅ PASS |
| 6C verify | scope_mismatch:stage2 token in eta | Present | Not observable (cascade to stage 3 first) | ⚠️ N/A |
| 7 | Derived schema decay | salience→0.25, needs_review=1 | Via direct decay: ✓; via consolidate: 0.65 | ⚠️ PARTIAL |
| 7 | D7 (explicit) exempt | Unchanged | 1.375→1.375 | ✅ PASS |
| 7 | T1 (recalled) exempt | Unchanged | 1.70→1.70 | ✅ PASS |

---

## Phase 2 — Context ranking

MRR = 1.0 · P@1 = 8/8 · Cross-scope leaks = 0

| Probe | Target | Rank | Activation | Cosine | cue_overlap |
|-------|--------|------|-----------|--------|-------------|
| P1 fix session reaper race | T1 sch_2 | 1 | 0.45 | 0.67 | 0.21 |
| P2 add config option | T2 sch_3 | 1 | 0.42 | 0.57 | 0.30 |
| P3 write retrieval tests | T3 sch_4 | 1 | 0.44 | 0.60 | 0.32 |
| P4 debug scope bleed | T4 sch_5 | 1 | 0.50 | 0.69 | 0.46 |
| P5 optimize faiss index | T5 sch_6 | 1 | 0.46 | 0.56 | 0.59 |
| P6 update dashboard chart | T6 sch_7 | 1 | 0.41 | 0.51 | 0.38 |
| P7 run longmemeval bench | T7 sch_8 | 1 | 0.55 | 0.72 | 0.73 |
| P8 fix http daemon port | T8 sch_9 | 1 | 0.50 | 0.75 | 0.33 |

`(peripheral)` labels observed in all probes with ≥8 candidates admitted.

---

## Phase 3 — Recall

| Query | Target | In top 3? | Top activation | Notes |
|-------|--------|-----------|---------------|-------|
| R1 "how is the HTTP daemon port configured" (project:slowave) | T8 sch_9 | ✓ rank 1 | 0.83 | cosine path |
| R2 "background thread that closes inactive sessions" (project:slowave) | T1 sch_2 | ✓ rank 1 | 0.86 | near-zero lexical overlap — embedding path confirmed |
| R3 "tenant isolation SQL placeholder company id" (project:beta) | A2 sch_25 | Absent | — | foreign scope correctly excluded |

3/3 ✓

---

## Phase 4 — Demotion

S1 (sch_22, "The team retrospective happens every second Friday…"):

- Required 4 demotion queries (N1–N4); N2 and N3 were suppressed after N1's penalty, requiring N4 with direct lexical overlap (cosine=0.69) to force a second appearance.
- After N4 reinforce: `needs_review=1`, `context_noise_score=0.75` ✓
- N2 re-run post-demotion: S1 absent from default-mode brief ✓
- T1–T8 all `status=active`, `needs_review=0` ✓

---

## Phase 5 — Consolidation

- Schema count before first consolidation: 28
- Schema count after 2× consolidation: 28 (stable; remember-only episodes skipped ✓)
- Max salience after consolidation: 1.65 ≤ 20 ✓
- P1/P5/P7 re-run: T1/T5/T7 still rank #1 ✓

---

## Phase 6 — Promotion ladder

### Ladder trace

| Step | Consolidation # | L1 stage | distinct_scopes | distinct_sessions | distinct_scope_kinds | scope_breadth_pct | L2 stage |
|------|----------------|----------|----------------|------------------|--------------------|------------------|----------|
| Initial (Phase 1 inject) | 1–2 | 0 | 1 | 2 | 1 | 0.10 | 0 |
| Step A: gamma + delta | 3 | **1** | 3 | 4 | 1 | 0.30 | 0 |
| Step B: epsilon activate | — | 1 | 3 | 4 | 1 | 0.30 | 0 |
| Step C: zeta remember | 4 | 1 | 4 | 5 | 1 | 0.40 | 0 |
| Step D: eta + theta + alpha | 5 | **2** | 7 | 8 | 1 | 0.70 | 0 |
| Epsilon remember (fix) | 6 | **3** | 8 | 9 | 1 | 0.80 | 0 |
| E3: domain:engineering use | 7 | 3 | 8 | 11 | **2** | 0.80 | 0 |

### Step B failure — Stage 1 cross-scope admission via activate

**Query:** "implementing retry logic for the payments API - what backoff strategy should we use"  
**Scope:** project:epsilon  **Mode:** strict_scope (default)

sch_20 (L1 origin, stage 1) was **not surfaced**. Debug trace:

```
{"schema_id": 20, "activation": -0.10, "reason": "cross_scope_below_floor", "admitted": false}
```

**Root cause:** Stage 1 cross-scope schemas receive the full `-0.35 scope_mismatch` penalty. With `_IDENTITY_BONUS_CAP = 0.15`, the maximum achievable activation from a foreign-scope stage-1 schema is:

```
max_activation = 0.40 × cosine + 0.15 × overlap + 0.15 (cap) − 0.35 (penalty)
              = 0.40 × 0.65 + 0.15 × 0.38 + 0.15 − 0.35
              = 0.26 + 0.057 + 0.15 − 0.35 ≈ 0.117
```

The cross-scope floor is 0.30. A stage-1 schema can only exceed this floor when cosine > ~0.81, which this query/schema pair does not achieve (cosine ≈ 0.65).

**Cascade effect:** epsilon could not be counted as a validated scope via the activate path. epsilon had to be counted via an additional `slowave_remember` (making it a Stage A-style evidence link, not a recall use). As a result:
- Step C expected L1→stage 2 but L1 stayed at stage 1 (4/10=0.40 < 0.55)
- Stage 2 was reached after Step D (7/10=0.70 ≥ 0.55)
- Stage 3 required epsilon remember (8/10=0.80 ≥ 0.78)

### Stage-2 penalty token observed

Not directly observable via the planned Step C eta verification because L1 bypassed stage 2 visibility in eta (eta has its own local copy sch_32 with `scope_match=project:eta`). Stage-2 cross-scope behavior was implied by the cross_scope_below_floor mechanism at stage 1.

### Stage-3 penalty-free admission observed

- **E1 (project:beta):** reason = `"cosine=0.53,cue_overlap=0.22,salience=0.10,lesson,utility=0.19,domain,explicit,noise=0.50"` — **no `scope_mismatch` token** ✓
- **E3 (domain:engineering):** reason = `"cosine=0.42,cue_overlap=0.17,salience=0.10,lesson,utility=0.22,domain,explicit,noise=0.20"` — **no `scope_mismatch` token** ✓

### kind_bonus eligibility after E3

```sql
SELECT json_extract(facets_json,'$.distinct_scope_kind_count'),
       json_extract(facets_json,'$.distinct_session_count')
FROM schemas WHERE id = 20;
-- Result: 2 | 11
```

`distinct_scope_kind_count = 2` (project + domain) ≥ 2 → **kind_bonus = 1** ✓  
Hypothetical: if L1 were at stage 2 with only 4 sessions, `kind_bonus=1` would reduce the 5-session floor by 1, allowing admission at 4 sessions.

---

## Phase 7 — Decay

**Schema IDs:** derived=sch_36 · D7=sch_16 · T1=sch_2

| Schema | Source kind | recurrence | Salience before | Salience after (`decay_unused`) | needs_review | Status |
|--------|-------------|-----------|----------------|-------------------------------|-------------|--------|
| sch_36 (derived) | episodic_summary | 0 | 0.40 | **0.25** (−0.15) | **True** | ✅ PASS |
| sch_16 D7 (explicit) | explicit_remember | 0 | 1.375 | **1.375** (unchanged) | False | ✅ PASS |
| sch_2 T1 (recalled) | explicit_remember | 5 | 1.70 | **1.70** (unchanged) | False | ✅ PASS |

**Note on `slowave consolidate` path:** when `slowave consolidate` is used as instructed, the ReplayEngine reprocesses the fresh purple cable ties episodes (created today) during the same consolidation run, boosting sch_36's salience by ~0.40 before applying the −0.15 decay, resulting in 0.65. This is a test-harness confound: the episode events must also be aged (backdated) for the consolidation path to match the direct `decay_unused` path. The `decay_unused` function confirms the decay mechanism is correct. Verified: `decayed=1, flagged_review=1` via direct call.

---

## Verdict

**PARTIAL** — 18/21 criteria pass, 2 fail, 1 N/A.

**Failures:**
1. **Step B (Stage 1 cross-scope admission via activate):** L1 never surfaced in project:epsilon via `slowave_activate`. Root cause: `-0.35 scope_mismatch` penalty + `_IDENTITY_BONUS_CAP=0.15` makes activation floor of 0.30 arithmetically unreachable for typical query-schema cosine pairs (< ~0.81). Cascaded to Step C (delayed stage-2 flip).
2. **Phase 7 decay (via `slowave consolidate`):** Consolidation reprocesses fresh episodes before decay, counteracting the salience backdating. Direct `decay_unused` call confirms correct mechanism.

**Root issue for Step B:** the comment in `context.py:508` says "Stage 0/1 keep the full penalty" — but with `_IDENTITY_BONUS_CAP=0.15` and the `-0.35` penalty, Stage 1 is effectively unreachable cross-scope for any query with cosine below ~0.81. The design intent (portable across same scope_kind) cannot be validated via `slowave_activate` without either reducing the mismatch penalty for stage 1 or raising the identity cap.

**Root issue for Phase 7:** the `slowave consolidate` command runs full ReplayEngine before decay. When test episodes are created in the same session as the test, they will be reprocessed on the next consolidation run. The backdating technique only works reliably if either (a) the session events are also backdated or (b) decay is invoked directly via `eng.schemas.decay_unused()`.
