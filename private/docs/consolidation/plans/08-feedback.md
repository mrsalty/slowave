# 08 — Feedback Improvement Plan

**Status:** COMPLETE — all 8 phases done 2026-07-09; Design Evaluation follow-up fixes applied 2026-07-10 (see `outcomes/08-feedback.md`'s "Follow-up (2026-07-10)" section for what was fixed/removed/documented per weakness, plus a new finding: `apply_learning=False` doesn't gate the noise-score demotion mechanism)
**Created:** 2026-07-09
**Depends on:** `core/08-feedback.md` (rewritten 2026-07-09 and updated 2026-07-10)

## What's Already Done

`tests/unit/test_context_feedback.py` (624 lines, 26 tests) covers: symbolic-label → signal mapping for all 7 labels, snapshot persistence (`record_context_recall`), feedback-event persistence, `useful`/`partially_useful` reinforcement, `irrelevant` penalization without review, `stale`/`wrong` penalization *with* review, `missing` (no memory created) and `too_much_context` (no penalty), outcome-independence of memory-quality reinforcement, and the `context_feedback_weight` (0.5) vs `recall_feedback_weight` (1.0) asymmetry. This is denser coverage than any prior module had at this stage (Consolidation had zero diagnostic instrumentation pre-existing; Temporal had zero coverage of `TemporalProbe`).

**Gap:** none of the 26 tests touch `context_noise_score`, the demotion rule, the salience-bound asymmetry between `reinforce()` and `adjust_feedback_state()`, or any of the config fields added/found dead during the Phase 1 audit (`useful_confidence_delta`, `*_review_threshold`, `apply_outcome_to_schema_reward`, `missing_creates_memory`, `missing_replay_enabled`).

## Priority Finding (motivates Q1–Q4 below)

Unlike every prior module, **none of the project's 6 benchmarks (`locomo_eval.py`, `longmemeval_eval.py`, `stalememory_eval.py`, wiki, dmr, temporal_eval) call `retrieval_feedback()`/`record_retrieval()` at all** (grep confirmed, 2026-07-09, zero hits for `feedback`/`reinforce` across `tests/integration/*.py`). This isn't a coverage gap to fill — it's structural: these are single-shot offline recall benchmarks, and feedback requires a multi-turn interaction with an explicit quality label, which none of them simulate. `iteration-strategy.md` already predicted this ("Requires many sessions to accumulate signal. Can't measure efficacy in a single benchmark run"). The Phase 4/5 "ablation matrix against benchmarks" pattern used by every prior module **does not apply here** — there is no task-metric Δ to measure. The substitute evidence sources are (a) the live dogfood DB (`~/.slowave/slowave.db`), which has accumulated 30 real `context_feedback_events` rows and 55 `context_recall_events` rows from this project's own agent sessions calling `slowave_reinforce`/`slowave_activate`, and (b) a synthetic internal-invariant script, since there's no external accuracy number to move.

## UPDATE (2026-07-09, live-DB inspection — Phase 4 substitute)

Queried `~/.slowave/slowave.db` read-only (47 schemas, 30 feedback events, 55 recall events — real usage from this project's own Claude Code sessions, not synthetic):

| Query | Result |
|---|---|
| `context_feedback_events` by label | `useful`=15, `irrelevant`=9, `partially_useful`=3, `stale`=2, `wrong`=1 |
| `context_feedback_events` by `retrieval_type` | `context`=28, `recall`=2 — the 0.5-weight path dominates real traffic by 14:1 |
| Schemas with `needs_review=1` (boolean) | 13/47 |
| Schemas with `status='needs_review'` (string) | 1/47 |

Cross-referencing schema ids against their feedback history confirms the noise-score demotion rule (\(N_{\text{neg}} \geq 3, N_{\text{used}}=0\)) **does fire on real usage**: schemas 21–26 each have 6–8 `irrelevant` marks, 0 `used` marks, `context_noise_score` in [0.857, 0.889], `needs_review=1` — and **`status='active'`** in every case. Only schema 10 (marked `wrong` with `outcome="failure"`) has `status='needs_review'`. This is a direct, real-data confirmation of core doc Invariant 6: the demotion mechanism is alive and firing, but it produces a soft ranking penalty (`activation -= 0.30 * noise ≈ −0.26`), not exclusion — schemas 21–26 remain fully eligible for default-mode retrieval today, in this project's own memory store, despite 6–8 consecutive negative marks and zero positive ones.

## Diagnostic Questions

| # | Question | Why It Matters | Status |
|---|----------|-----------------|--------|
| Q1 | Are `apply_outcome_to_schema_reward`, `missing_creates_memory`, `missing_replay_enabled` genuinely dead (zero behavioral effect at any value)? | If dead, sweeping them is pointless and the core doc/plan should say so plainly rather than imply they're tunable | **Answered** — grep confirms zero read sites outside the dataclass definition (Phase 1) |
| Q2 | Does `useful_confidence_delta` ever change a schema's confidence? | The config field exists, is documented in the old doc as active, and is silently unreachable — a user tuning it would see nothing change and might conclude the whole feedback system is broken | **Answered** — `reinforce()` (the only call path for `useful`) has no confidence parameter (Phase 1) |
| Q3 | Do `stale_review_threshold`/`wrong_review_threshold` gate `needs_review`, or only set a stored value? | The old doc's "Schema Updates from Feedback" section explicitly claimed a threshold comparison (`review_pressure ≥ threshold`) that doesn't exist in code | **Answered** — no comparison exists anywhere; `needs_review=True` is unconditional given `apply_stale_wrong_review` (Phase 1) |
| Q4 | Does the noise-score demotion rule (3+ negative marks, 0 used marks → `needs_review=1`) actually fire on real usage, and does it exclude the schema from default retrieval? | This is this module's closest analogue to prior modules' "is the mechanism alive" question — `iteration-strategy.md`'s own suggested micro-benchmark (`test_feedback_suppression`) asks exactly this | **Answered from live DB** — fires (6/47 schemas), does NOT exclude (all 6 remain `status="active"`); only the separate `wrong`+`failure` → `update_status` path excludes (1/47) |
| Q5 | Can this module be measured through any of the 6 existing benchmarks? | Determines whether Phase 4/5 should extend an eval script (as every prior module did) or substitute a different evidence source | **Answered** — no; zero call sites (Priority Finding) |
| Q6 | Is the salience-bound asymmetry (ceiling-only on the `useful`/`reinforce` path, floor-only on the `adjust_feedback_state` path) intentional, or does it let `partially_useful`-only reinforcement grow a schema's salience unboundedly? | An unbounded growth path would silently distort salience-ordered listings the same way exceeding the 20.0 cap already does by design (per the `reinforce()` comment) | Answered via ablation script below |
| Q7 | Is fixing the misleading `_update_utility_scores` demotion comment ("leave default context entirely") in scope, given Temporal's precedent of fixing a docstring lie with no behavior change? | The comment actively misdescribes real, verified behavior (Q4) — same class of issue as the Temporal docstring fix | **Yes — comment-only fix applied** (Phase 2, see outcome doc) |
| Q8 | Does `context_noise_score` tracking require `scope_id` to be set on the feedback call? | Discovered while building the Q4 repro script (not anticipated up front) — the counting query in `_update_utility_scores` hard-filters `scope_id IS NOT NULL`; a caller that omits scope gets silent, permanent non-tracking | **Answered** — yes, confirmed by the ablation script's first failed run followed by a corrected re-run (see Results below) |

## Ablation Matrix

No benchmark task-metric exists to move (Priority Finding), so this ablation targets the module's own internal invariants via a deterministic scripted scenario (`scripts/feedback_ablation.py`) against a real (temp, in-memory-equivalent) `SlowaveEngine` — the same substitution pattern Temporal used for its Q7 ("standalone script … no engine-level side effects to worry about"), except here the engine *is* the thing under test, so the script drives it directly rather than bypassing it.

| # | Flag | Scenario | Expected Δ if the flag matters |
|---|------|----------|-------------------------------|
| F1 | `apply_learning=False` | Full label sweep (`useful`×1, `irrelevant`×3) | Zero salience/confidence/needs_review change for every label vs. `apply_learning=True` baseline |
| F2 | `apply_positive_learning=False` | `useful`×1, `partially_useful`×1 | Zero salience change on those two labels only; `irrelevant`/`stale`/`wrong` unaffected |
| F3 | `apply_negative_learning=False` | `irrelevant`×3 | Zero salience change on `irrelevant` only |
| F4 | `apply_stale_wrong_review=False` | `stale`×1, `wrong`×1 | Zero salience/confidence/needs_review change on those two labels only |
| F5 (Q6) | n/a — no boolean flag | 200× `partially_useful` on one schema vs. 200× `useful` on another | `useful` schema salience saturates at 20.0; `partially_useful` schema salience exceeds 20.0 (no ceiling on that path) |
| F6 (Q3) | `stale_review_threshold` ∈ {0.0, 0.7, 999.0} | `stale`×1 each | `needs_review` is `True` in all three cases — threshold value has no effect |
| F7 (Q2) | `useful_confidence_delta` ∈ {0.0, 0.02, 0.9} | `useful`×1 each | Schema confidence identical across all three — value has no effect |

**Results (2026-07-09, `scripts/feedback_ablation.py`, dim=8, `disable_encoder=True`, actually run — not estimated):**

| # | Result |
|---|--------|
| F1 | Confirmed — with `apply_learning=False`, salience/confidence/`needs_review` bit-identical (1.0/1.0/False) before and after 4 feedback calls (1 useful + 3 irrelevant) |
| F2 | Confirmed — `useful` salience stays at 1.0 under `apply_positive_learning=False`; `irrelevant` still drops 1.0→0.975 in the same config |
| F3 | Confirmed — `irrelevant` salience stays at 1.0 (×3 calls) under `apply_negative_learning=False`; `useful` still rises 1.0→1.05 in the same config |
| F4 | Confirmed — `stale`/`wrong` salience unchanged, `needs_review` stays `False`, `wrong`+`failure` status stays `"active"` (not escalated) under `apply_stale_wrong_review=False` |
| F5 | Confirmed, **with a correction to this doc's first-draft arithmetic**: using `retrieval_type="recall"` (weight 1.0) for both, 500 `useful` reps saturate at exactly `20.0`; 500 `partially_useful` reps land at `20.9999999999997 ≈ 1.0 + 500×0.04 = 21.0`, **exceeding** the ceiling that bounds the `useful` path. (First draft used the default `retrieval_type="context"`, i.e. weight 0.5, which halves the per-rep delta and does not cross 20.0 within 500 reps — corrected before this was reported as a real finding.) Confirms Q6: the two paths are independently bounded; `adjust_feedback_state` genuinely has no ceiling. |
| F6 | Confirmed — `needs_review=True` for all three threshold values (0.0, 0.7, 999.0); zero behavioral difference |
| F7 | Confirmed — confidence unchanged (bit-identical, 1.0→1.0) across `useful_confidence_delta` ∈ {0.0, 0.02, 0.9} |
| Q4 repro | **First attempt failed and surfaced a new finding**: 4 `irrelevant` calls with no `scope_id` produced `context_noise_score=0.0`, `needs_review=False` — the demotion rule never fired. Root cause: `_update_utility_scores`'s counting query filters `WHERE scope_id IS NOT NULL` (`schema_store.py:830-840`); feedback with no `scope_id` is invisible to noise tracking, full stop. Re-run with `scope_id="eval:test"` on every call: `context_noise_score=0.8`, `needs_review=True`, `status` stays `"active"`, and the schema is still returned by `eng.context(limit=100)` — confirming the live-DB finding (demotion is soft, not exclusionary) end-to-end in a controlled scenario. A second schema marked `wrong`+`outcome="failure"` gets `status="needs_review"` and **is** excluded from `eng.context()`. |

**Every flag that has a wiring (F1–F4) shows a real, load-bearing Δ on the internal scenario — none are dead weight.** The three genuinely dead config fields (`apply_outcome_to_schema_reward`, `missing_creates_memory`, `missing_replay_enabled`) were already excluded from this matrix per Q1's static-analysis answer — running them would be a confirmed no-op, not a discovery. The `scope_id` requirement for noise tracking (newly found while running Q4's repro, not anticipated by the original diagnostic-question list) is folded into core doc Invariant 10 and Known Failure Modes.

## Grid Search

**Decision: skipped, with reasoning distinct from prior modules' "flat landscape" cases.** Every previous module's Phase 6 either found a real parameter to tune (Retrieval, Salience, Graph) or documented a flat *benchmark* landscape (Temporal's `temporal_weight`, Consolidation's judge thresholds) — in both cases, a task-metric existed to sweep against. Here, **no task metric exists at all** (Priority Finding) — there is nothing to compute a landscape against. The salience/confidence deltas (`useful_salience_delta`, `stale_salience_delta`, etc.) are calibrated by design intent (small, monotonic, roughly ordered by severity: `partially_useful` (0.04) < `useful` (0.10) < `irrelevant` (−0.05) < `stale` (−0.20) < `wrong` (−0.30/−0.40)) — this ordering is internally consistent and testable (Phase 7), but "optimal" has no meaning without a downstream task to optimize. `stale_review_threshold`/`wrong_review_threshold` are confirmed cosmetic (Q3/F6) — sweeping them is a defined no-op, not a flat-but-real landscape. No grid search was run.

## Diagnostic Instrumentation Spec (Phase 4)

Delivered as `scripts/feedback_ablation.py` (a standalone script against a real `SlowaveEngine`, not an eval-script flag, per the Priority Finding) plus the live-DB read-only query set documented in the UPDATE section above. No new persistent instrumentation was added to `slowave/` — `context_noise_score`, `needs_review`, and `status` are already fully queryable from `facets_json`/`schemas` for any future investigation; the gap was investigative reach, not missing data.

## Micro-Benchmark Gap (Phase 7)

New file: `tests/unit/test_feedback_review_gating.py`, deterministic, covering the findings that have zero existing coverage:

- Boolean `needs_review=1` (via noise-score demotion) does not exclude a schema from default-mode `recall()`; explicit `status="needs_review"` (via `wrong`+`outcome="failure"`) does.
- `context_noise_score` formula reproduces `neg / (neg + 3*used + 1)` for a scripted sequence of marks.
- `useful_confidence_delta` has no effect on schema confidence (F7).
- `stale_review_threshold`/`wrong_review_threshold` have no effect on `needs_review` (F6).
- Salience ceiling (20.0) on the `reinforce`/`useful` path; no ceiling on `adjust_feedback_state`/`partially_useful` path (F5, at a smaller rep count for test speed).
- The three dead flags (`apply_outcome_to_schema_reward`, `missing_creates_memory`, `missing_replay_enabled`) produce identical schema/DB state whether `True` or `False`.
- `apply_learning`/`apply_positive_learning`/`apply_negative_learning`/`apply_stale_wrong_review` each gate exactly their documented label subset (F1–F4), formalizing the ablation script's findings as regression tests.

Existing `tests/unit/test_context_feedback.py` is left untouched — no overlap with the above.

## Decision Thresholds

| Observed | Action |
|----------|--------|
| A boolean flag (F1–F4) shows zero Δ on the internal scenario | Treat as dead weight, document, do not test further — did not occur; all four are load-bearing |
| A config field is confirmed read nowhere in the codebase (Q1) | Document as dead in core doc's Configuration table; do not attempt to tune | Applied to 3 fields |
| A threshold field only sets a stored value with no comparison anywhere (Q3) | Document as cosmetic; exclude from grid search | Applied to 2 fields |
| The demotion mechanism never fires on real usage (Q4) | Would indicate the mechanism is dead on real traffic — did not occur; fires on 6/47 live schemas |
| The demotion mechanism fires but a code comment overstates its effect (Q4/Q7) | Fix the comment (no behavior change), same bar as Temporal's docstring fix | Applied |

## Implementation Order

```
Step 1: Live-DB read-only query set (context_feedback_events, schemas status/needs_review)  [15 min]
         ** Q4 answered directly from real usage — no synthetic scenario needed for this one **
Step 2: Write scripts/feedback_ablation.py — F1-F7 scenarios against a temp SlowaveEngine    [45 min]
         ** Q2, Q3, Q6 answered; F1-F4 ablation confirmed load-bearing **
Step 3: Fix misleading demotion comment in schema_store.py (Q7)                              [10 min]
Step 4: Write tests/unit/test_feedback_review_gating.py, formalizing F1-F7 + Q4              [40 min]
Step 5: Update core/08-feedback.md Configuration/Known-Failure-Modes if anything changed     [15 min]
Step 6: Write outcomes/08-feedback.md + update PROGRESS.md                                   [15 min]
```

## Phase Execution

| # | Task | Status |
|---|------|--------|
| 1 | Implementation audit | ✅ |
| 2 | Core doc rewrite | ✅ |
| 3 | Plan document | ✅ |
| 4 | Diagnostic instrumentation (live-DB query + ablation script, no benchmark exists) | ✅ |
| 5 | Ablation matrix (F1-F7) | ✅ |
| 6 | Parameter tuning (grid search — skipped, no task metric exists) | ✅ |
| 7 | Micro-benchmark gap-fill (`tests/unit/test_feedback_review_gating.py`) | ✅ |
| 8 | Outcome document + PROGRESS | ✅ |
