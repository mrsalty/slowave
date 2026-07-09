# 08 — Feedback System & Learning Signals

## Overview

The feedback system closes the memory loop: a symbolic label from the caller (`useful`, `stale`, `wrong`, …) is converted into a numeric `FeedbackSignal`, then applied to the schemas the caller says it relied on — nudging salience, confidence, and review flags. It is the only module in the pipeline whose entire job is to consume *external* signal rather than derive structure from embeddings. Two entry points do the work: `FeedbackService.record_retrieval()` snapshots what a retrieval returned (so a later feedback call has something to reference), and `FeedbackService.retrieval_feedback()` applies the label. This is not an internal implementation detail — `retrieval_feedback()` is the direct handler behind the `slowave_reinforce` MCP tool (`slowave/mcp/tools.py:257-293` → `ops.reinforce()` → `SlowaveEngine.retrieval_feedback()` → `FeedbackService.retrieval_feedback()`), i.e. the same mechanism documented here is exercised every time an agent calls `slowave_reinforce` on itself.

## Data Flow

```
slowave_activate / slowave_recall                         slowave_reinforce
(ops.activate / ops.recall)                                (ops.reinforce)
        │                                                          │
        ▼                                                          ▼
FeedbackService.record_retrieval()                  FeedbackService.retrieval_feedback()
  INSERT context_recall_events (1 row/call)            ┌─ _derive_context_fields(retrieval_id)
  INSERT context_recall_items  (1 row/returned item,    │    SELECT ... FROM context_recall_events
                                admitted=1)              │    WHERE context_id = retrieval_id
  INSERT context_recall_items  (1 row/filtered item,     │    (session_id/scope_id/goal/task_type/
                                admitted=0)              │     situation/requirements — caller-
        │                                                │     supplied values always win)
        │  (rows keyed by retrieval_id,                  │
        │   read back later)                             ▼
        └──────────────────────────────────────►  feedback_signal_for(label, outcome, cfg)
                                                           │  → FeedbackSignal (10 components)
                                                           ▼
                                            source_weight = context_feedback_weight (0.5) if
                                                            retrieval_type=="context" else
                                                            recall_feedback_weight (1.0)
                                                           │
                              ┌────────────────────────────┼────────────────────────────┐
                              ▼                            ▼                            ▼
                    used_memory_ids               irrelevant_memory_ids      stale_memory_ids / wrong_memory_ids
                    (apply_positive_learning)      (apply_negative_learning)   (apply_stale_wrong_review)
                              │                            │                            │
                    "useful" → schemas.reinforce(  schemas.adjust_feedback_state(  schemas.adjust_feedback_state(
                      amount=Δs·w,                    salience_delta=Δs·w)          salience_delta=Δs·w,
                      confidence_delta=Δc·w)
                    "partially_useful" →                                            confidence_delta=Δc·w,
                      schemas.adjust_feedback_state(                                needs_review=True)
                        salience_delta=Δs·w,                                       "wrong"+outcome=="failure" also:
                        confidence_delta=Δc·w)                                     schemas.update_status(status=
                                                                                      "needs_review")
                              │                            │                            │
                              └────────────────────────────┴────────────────────────────┘
                                                           ▼
                                     INSERT context_feedback_events (1 row, full signal + id lists)
                                                           ▼   (unconditional — NOT gated by apply_learning)
                                schemas.refresh_utility(schema_id) for every touched id
                                  → recomputes context_noise_score / schema_utility / generalization_stage
                                    (09-context.md reads context_noise_score at next retrieval's ranking step)
```

`missing` and `too_much_context` labels flow through `feedback_signal_for` like any other label, but their `salience_delta`/`confidence_delta` are hardcoded to `0.0` in the mapping, so no schema-touching branch above ever fires for them — they only produce the `context_feedback_events` row (`missing_context` free-text column for `missing`).

The diagram above ends at `needs_review` being *set*. Since 2026-07-10 that flag is no longer a dead end — see "Labile State & Reconsolidation" below for what clears it, including a path (Consolidation's `reconsolidate_labile_schemas()`) that lives entirely outside this module.

## Mathematical Formulation

### Phase 1: Symbolic Label → Numeric Signal

`feedback_signal_for(feedback, outcome, cfg)` (`slowave/core/feedback.py:190-310`) maps a normalized label to a 10-component vector:

\[
\boldsymbol{\phi} = (v, c_f, e_t, e_\tau, m, o, \Delta_s, \Delta_c, r_p, r_o)
\]

| Component | Symbol | Range | Meaning |
|-----------|--------|-------|---------|
| `valence` | \( v \) | \([-1, 1]\) | overall usefulness |
| `context_fit` | \( c_f \) | \([-1, 1]\) | match between memory and query cue |
| `truth_error` | \( e_t \) | \([0, 1]\) | factual wrongness |
| `temporal_error` | \( e_\tau \) | \([0, 1]\) | staleness |
| `missingness` | \( m \) | \([0, 1]\) | recall gap |
| `overload` | \( o \) | \([0, 1]\) | working-memory capacity failure |
| `salience_delta` | \( \Delta_s \) | \(\mathbb{R}\) | schema salience change (config-driven) |
| `confidence_delta` | \( \Delta_c \) | \(\mathbb{R}\) | schema confidence change (config-driven) |
| `review_pressure` | \( r_p \) | \([0, 1]\) | see note below — informational, **not wired to any gate** |
| `outcome_reward` | \( r_o \) | \([-1, 1]\) | task-level reward, independent of \(v..r_p\) |

Label → \((v, c_f, e_t, e_\tau, m, o, \Delta_s, \Delta_c, r_p)\), with \(r_o\) computed separately (Phase 1b) and appended to every row:

| Label | \(v\) | \(c_f\) | \(e_t\) | \(e_\tau\) | \(m\) | \(o\) | \(\Delta_s\) | \(\Delta_c\) | \(r_p\) |
|---|---|---|---|---|---|---|---|---|---|
| `useful` | 1.0 | 1.0 | 0 | 0 | 0 | 0 | `useful_salience_delta` (0.10) | `useful_confidence_delta` (0.02) | 0 |
| `partially_useful` | 0.4 | 0.5 | 0 | 0 | 0 | 0 | `partially_useful_salience_delta` (0.04) | 0 | 0 |
| `irrelevant` | −0.4 | −1.0 | 0 | 0 | 0 | 0 | `irrelevant_salience_delta` (−0.05) | 0 | 0 |
| `stale` | −0.6 | −0.3 | 0 | 1.0 | 0 | 0 | `stale_salience_delta` (−0.20) | `stale_confidence_delta` (−0.20) | `0.7` (fixed) |
| `wrong` | −1.0 | −0.5 | 1.0 | 0 | 0 | 0 | `wrong_salience_delta` (−0.30) | `wrong_confidence_delta` (−0.40) | `1.0` (fixed) |
| `missing` | −0.3 | 0 | 0 | 0 | 1.0 | 0 | 0 | 0 | 0 |
| `too_much_context` | −0.2 | −0.2 | 0 | 0 | 0 | 1.0 | 0 | 0 | 0 |

**Logical concept**: the vector separates *why* a memory failed (context_fit vs. truth_error vs. temporal_error vs. missingness vs. overload) from *what changes as a result* (\(\Delta_s, \Delta_c\)). This lets `missing`/`too_much_context` carry diagnostic signal (they populate `missingness`/`overload`) without ever mutating a schema — those two labels describe a retrieval/gating problem, not a memory-quality problem, so \(\Delta_s = \Delta_c = 0\) unconditionally (Invariant 1).

**review_pressure is populated but never read as a gate.** \(r_p\) is `_STALE_REVIEW_PRESSURE`/`_WRONG_REVIEW_PRESSURE` — fixed module constants (0.7/1.0), persisted into `feedback_signal_json` for analytics only. **Fixed 2026-07-10**: these were originally `FeedbackConfig` fields (`stale_review_threshold`/`wrong_review_threshold`) that could be overridden per-call, implying they gated something — no code path ever compared \(r_p\) against anything, so the fields were removed rather than wired (making them real would require redefining \(r_p\) from an independent signal, since it's defined to *equal* the threshold by construction — a design change, not a bug fix). The `needs_review` boolean is set unconditionally whenever `apply_stale_wrong_review` is on and a schema id appears in `stale_memory_ids`/`wrong_memory_ids` (`services/feedback.py:407-441`).

### Phase 1b: Outcome Reward

Computed independently of the feedback label, from a separate `outcome` argument (`normalize_outcome_label`, `feedback.py:177-187`):

\[
r_o = \begin{cases} 1.0 & \text{outcome} = \text{success} \\ 0.3 & \text{outcome} = \text{partial} \\ 0.0 & \text{outcome} = \text{unknown} \\ -1.0 & \text{outcome} = \text{failure} \end{cases}
\]

`"failed"`, `"fail"`, `"task_failed"` are normalized aliases for `"failure"`; anything else unrecognized (including `None`/`""`) defaults to `"unknown"`, never raises. \(r_o\) is stored in `context_feedback_events.outcome_reward` and in the signal JSON, but never applied to any schema field — there is no code path that feeds it back into salience/confidence. **Fixed 2026-07-10**: this used to be gated by a `FeedbackConfig.apply_outcome_to_schema_reward` field (default `False`) that implied a real feature existed behind a flag; it was read nowhere, so it was removed rather than built. Whether outcome-driven schema reward should exist at all (does task-level success belong in memory-quality reward?) is an open product question, not resolved here — see the plan/outcome docs. This is why `useful` feedback still reinforces a schema even when `outcome="failure"` (Invariant 2, tested by `test_useful_with_failure_still_reinforces`).

### Phase 2: Source-Weighted Schema Update

Every schema update is scaled by a per-retrieval-type weight before it reaches the schema store (`services/feedback.py:336-340`):

\[
w = \begin{cases} \text{context\_feedback\_weight} = 0.5 & \text{retrieval\_type} = \text{"context"} \\ \text{recall\_feedback\_weight} = 1.0 & \text{retrieval\_type} = \text{"recall"} \end{cases}
\]

For `used_memory_ids` (label = `useful`, gated by `apply_positive_learning`):

\[
s \leftarrow \min(s + \Delta_s^{\text{useful}} \cdot w,\; \text{SALIENCE\_CEILING}) \qquad (\texttt{SchemaStore.reinforce})
\]
\[
c \leftarrow \operatorname{clamp}\!\big(c + \Delta_c^{\text{useful}} \cdot w,\; \text{min\_confidence},\; \text{max\_confidence}\big) \qquad \text{iff } \Delta_c^{\text{useful}} \neq 0
\]

**Fixed 2026-07-10**: `reinforce()` previously had no confidence parameter at all — `useful_confidence_delta` was computed into the signal and then silently dropped, so `"useful"` feedback could never move confidence. `reinforce()` now takes an optional `confidence_delta`/`min_confidence`/`max_confidence`, applied with the same clamp semantics `adjust_feedback_state()` uses, and `FeedbackService`'s `useful` branch now passes `useful_signal.confidence_delta * w`. The salience-only call remains the default (`confidence_delta=0.0` is a no-op — the `UPDATE` only touches `confidence` when a nonzero delta is given, to avoid a wasted read on the common path).

For `used_memory_ids` (label = `partially_useful`) and `irrelevant_memory_ids` (gated by `apply_positive_learning` / `apply_negative_learning` respectively), and for `stale_memory_ids`/`wrong_memory_ids` (gated by `apply_stale_wrong_review`):

\[
s \leftarrow \min\!\big(\text{SALIENCE\_CEILING},\; \max(\text{min\_salience},\; s + \Delta_s^{\text{label}} \cdot w)\big) \qquad (\texttt{SchemaStore.adjust\_feedback\_state})
\]
\[
c \leftarrow \operatorname{clamp}\!\big(c + \Delta_c^{\text{label}} \cdot w,\; \text{min\_confidence},\; \text{max\_confidence}\big)
\]

**Fixed 2026-07-10 — bounds are now shared, not asymmetric.** Before this fix, the `useful` path (`reinforce`) had a *ceiling* (`SALIENCE_CEILING = 20.0`, a module constant in `schema_store.py`, shared with `reinforce_schema()`'s unrelated consolidation-path literal) but `adjust_feedback_state` (partial/irrelevant/stale/wrong) had **no ceiling at all** — a schema reinforced only via `partially_useful` could grow past 20.0 while an otherwise-identical `useful`-reinforced schema could not. `adjust_feedback_state()` now takes an optional `max_salience` parameter defaulting to the same `SALIENCE_CEILING`, so both paths saturate at the same value. Both paths still share the floor semantics: `reinforce()` never needs an explicit floor in practice (the `useful` signal's `salience_delta` is always positive), while `adjust_feedback_state()`'s floor (`min_salience`, default `0.01`) matters because its callers include negative deltas. `stale_memory_ids`/`wrong_memory_ids` additionally pass `needs_review=True` unconditionally (subject only to `apply_stale_wrong_review`, not to `review_pressure` — see Phase 1). For `wrong_memory_ids` specifically, if `outcome == "failure"`, an extra call escalates the schema's **status string** (not the boolean flag) to `"needs_review"`:

\[
\text{status} \leftarrow \texttt{"needs\_review"} \qquad \text{iff label}=\text{wrong} \wedge \text{outcome}=\text{failure}
\]

This is the *only* path in the module that changes retrieval eligibility outright — see Phase 4.

### Phase 3: Context Noise Score (read by 09-context.md)

After every `retrieval_feedback()` call, `SchemaStore.refresh_utility(schema_id)` is called once per distinct touched id (`services/feedback.py:532-536`), which recomputes (`schema_store.py:952-966`):

\[
\text{noise} = \frac{N_{\text{neg}}}{N_{\text{neg}} + 3 \cdot N_{\text{used}} + 1}
\]

where \(N_{\text{neg}}\) = count of `context_feedback_events` rows where this schema appears in `irrelevant`/`stale`/`wrong_memory_ids_json`, and \(N_{\text{used}}\) = count of rows where it appears in `used_memory_ids_json` — both counted across **all** scopes, cumulative, never decayed or windowed. One `used` mark is worth 3 `irrelevant`/`stale`/`wrong` marks by construction.

**Requires `scope_id` to be non-null.** The counting query (`schema_store.py:830-840`) filters `WHERE scope_id IS NOT NULL` — a `retrieval_feedback()` call made without a `scope_id` (directly or auto-derived from the snapshot) contributes to neither \(N_{\text{neg}}\) nor \(N_{\text{used}}\), silently. Verified directly (`scripts/feedback_ablation.py` Q4 repro): four identical `irrelevant` calls with `scope_id=None` leave `context_noise_score=0.0`/`needs_review=False`; the same four calls with `scope_id="eval:test"` produce `context_noise_score=0.8`/`needs_review=True`. `09-context.md`'s activation scorer subtracts `_NOISE_PENALTY_WEIGHT (0.30) * noise` from a schema's ranking score (`core/context.py:146,559-562`) — a soft, continuous penalty, not a hard cutoff.

**Demotion (`schema_store.py:964-966`)**: if \(N_{\text{neg}} \geq 3\) and \(N_{\text{used}} = 0\), `needs_review` (boolean column) is set to `1` in the same update. **This does not remove the schema from default-mode retrieval** — `_eligible()` (`core/context.py:352-371`) gates default mode purely on `schema.status`, and this code path never touches `status`. A schema can sit at `needs_review=1`, `status="active"`, noise ≈ 0.86-0.89 indefinitely, fully eligible, only soft-penalized by \(0.30 \times 0.86 \approx 0.26\) activation points. Confirmed against the live dogfood DB (`~/.slowave/slowave.db`, 2026-07-09): 6/47 schemas sit in exactly this state (3-8 negative marks, 0 used marks, `status="active"`, `needs_review=1`); only 1/47 schemas has `status="needs_review"` (the string, via the Phase 2 wrong+failure path) and is actually excluded from default-mode eligibility. See Known Failure Modes.

**`apply_learning=False` does not disable this mechanism.** `FeedbackService.retrieval_feedback()` calls `refresh_utility()` for every touched id (`services/feedback.py:562-566`) **unconditionally**, outside the `if self.cfg.apply_learning:` block that gates the direct salience/confidence/status mutations in Phase 2 above. The `INSERT INTO context_feedback_events` row is likewise always persisted regardless of `apply_learning`. So with the "master learning gate" off: direct reinforcement/penalization/status-escalation never happens, but `context_noise_score` still accumulates from the persisted events and the boolean `needs_review` demotion rule can still fire (given `scope_id`). Discovered 2026-07-10 while building `scripts/feedback_ablation.py` into a scored benchmark and locked in by `tests/unit/test_feedback_review_gating.py::TestApplyLearningFlagsGateExactlyTheirLabelSubset::test_apply_learning_false_does_not_disable_noise_score_demotion`. Not changed — whether `apply_learning` *should* gate this derived mechanism too is a design question (see outcome doc), not treated as an obvious bug fix.

### Phase 4: Labile State & Reconsolidation

**Terminology, precise and not metaphorical.** When `needs_review` is set (by the demotion rule above, by `decay_unused()`, or by `remember()`'s ambiguous-update case in `engine.py` — see Relationship to Other Modules), the schema is **labile**: the standard term in the memory-reconsolidation literature for a reactivated trace that is temporarily uncertain and open to revision. **Reconsolidation** is the process by which a labile trace resolves — restabilizing back to what it was, or being updated/replaced by better evidence. Before 2026-07-10, three separate subsystems set this flag using language that implied a follow-up step (`decay_unused()`'s docstring literally says schemas are "flagged `needs_review` for eventual pruning") and **none of them ever built that follow-up** — a schema could sit labile indefinitely, with no code path anywhere ever clearing the flag. Three recovery channels now exist, none of them requiring a new mechanism — each reuses something the codebase already had:

1. **Explicit positive feedback** (this module). A `useful`/`partially_useful` mark is direct evidence the schema is still good. `SchemaStore.reinforce()` gained a `clear_needs_review` parameter, set by `FeedbackService`'s `useful` branch; `adjust_feedback_state()` (the `partially_useful` branch) already took a `needs_review` parameter and now gets `needs_review=False` passed explicitly. `irrelevant`/`stale`/`wrong` do not clear it. **Regression found and fixed via the acceptance suite, not the unit tests** (`tests/acceptance/test_e2e.py` Phase 4): `reinforce()` calls `_update_utility_scores()` internally, before the current event's row is INSERTed into `context_feedback_events` — so a demote recount running in that same internal call was blind to the very `useful` mark clearing the flag, and re-set `needs_review=1` from stale history in schemas with real (3+) prior negative marks. The unit tests never caught this because they set `needs_review=True` directly via `adjust_feedback_state()` rather than building real negative history first. Fixed with `_update_utility_scores`'s new `force_clear_review` parameter, which `reinforce()` passes through and which takes priority over the demote recount unconditionally.
2. **Sustained passive recurrence** (this module, `SchemaStore._update_utility_scores`). If a labile schema keeps getting genuinely reactivated (`reinforce()` called with `recall_hit=True` — its default, fired on every explicit `useful`/`partially_useful` mark and, separately, on every schema `slowave_recall` returns in its top-k), that reactivation is itself evidence the memory is still good, mirroring how repeated recall drives real memory consolidation. A `recurrence_count_at_flag` facet is captured lazily the first time `_update_utility_scores` observes an already-labile schema with no baseline recorded, and `needs_review` clears once `_RECONSOLIDATION_RECOVERY_RECURRENCE` (3) recurrence hits accumulate *since* that baseline — deliberately not lifetime recurrence, so a schema with 10 pre-existing recurrences doesn't recover the instant it's flagged. On a same-call conflict (a schema simultaneously qualifies for the noise-demotion rule *and* has crossed the recovery threshold), demotion wins — explicit accumulated negative feedback outweighs passive reactivation.
3. **Consolidation's replay** (`05-consolidation.md`, a different module). `Consolidator.reconsolidate_labile_schemas()` — wired into every `consolidate_once()` pass — re-examines up to 20 labile, `status="active"` schemas per pass by finding each one's nearest active neighbor and replaying it through the *same* `GeometricContradictionJudge` and *same* caution gates the fresh-schema consolidation path already uses. Outcomes: **restabilized** (no conflict found, `needs_review` cleared), **superseded**/**contradicted** (the older/losing side demoted, the labile schema — now confirmed — restabilized), or **inconclusive** (no sufficiently related neighbor exists; left labile, decaying further via `decay_unused()` rather than being actively resolved — the brain analogue of passive extinction rather than reconsolidation). See `05-consolidation.md` for the full mechanics, including the chronology-based `old`/`new` argument assignment needed to avoid systematically favoring the labile schema purely by construction.

**Deliberately not done**: the `needs_review` **column** itself was not renamed to `is_labile` — that would require a schema migration plus updating every read/write site including the dashboard (a different tech stack outside this investigation's scope). "Labile"/"reconsolidation" are the vocabulary used in this document and in code comments; the database column is still literally `needs_review`. See `outcomes/08-feedback.md`'s "Follow-up (2026-07-10, part 2)" for the full design discussion, including why "labile" (state) and "reconsolidation" (process) were kept as two distinct, correctly-paired terms rather than collapsed into one.

## Configuration

### `FeedbackConfig` (`slowave/core/feedback.py:92-149`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `bool` | `True` | Master switch — `False` short-circuits `retrieval_feedback()` to a no-op dict before any signal mapping |
| `persist_context_snapshots` | `bool` | `True` | Gates whether `record_retrieval()` writes anything at all |
| `persist_response_json` | `bool` | `True` | Store the full response JSON alongside the snapshot |
| `persist_rendered_context` | `bool` | `False` | Store rendered text (can be large) |
| `persist_activation_trace` | `bool` | `False` | Store activation trace (very large) |
| `max_response_json_chars` | `int` | `20000` | Truncation for stored response JSON |
| `max_memory_content_chars` | `int` | `500` | Truncation for per-item stored content |
| `apply_learning` | `bool` | `True` | Master gate for *direct* salience/confidence/status mutations — `False` skips the entire `if self.cfg.apply_learning:` block (Phase 2). Does **not** gate the noise-score/`needs_review`-demotion mechanism (Phase 3) — that runs unconditionally. Still persists the feedback event row either way. |
| `apply_positive_learning` | `bool` | `True` | Gates `useful`/`partially_useful` schema updates |
| `apply_negative_learning` | `bool` | `True` | Gates `irrelevant` schema updates |
| `apply_stale_wrong_review` | `bool` | `True` | Gates `stale`/`wrong` schema updates and review flagging |
| `context_feedback_weight` \(w_{\text{ctx}}\) | `float` | `0.5` | Source weight when `retrieval_type == "context"` |
| `recall_feedback_weight` \(w_{\text{rec}}\) | `float` | `1.0` | Source weight when `retrieval_type == "recall"` |
| `useful_salience_delta` | `float` | `0.10` | \(\Delta_s\) for `useful`, pre-\(w\) |
| `partially_useful_salience_delta` | `float` | `0.04` | \(\Delta_s\) for `partially_useful`, pre-\(w\) |
| `irrelevant_salience_delta` | `float` | `−0.05` | \(\Delta_s\) for `irrelevant`, pre-\(w\) |
| `stale_salience_delta` | `float` | `−0.20` | \(\Delta_s\) for `stale`, pre-\(w\) |
| `wrong_salience_delta` | `float` | `−0.30` | \(\Delta_s\) for `wrong`, pre-\(w\) |
| `useful_confidence_delta` | `float` | `0.02` | \(\Delta_c\) for `useful`, pre-\(w\) — wired into `reinforce()` since 2026-07-10 (previously computed and silently dropped) |
| `stale_confidence_delta` | `float` | `−0.20` | \(\Delta_c\) for `stale`, pre-\(w\) |
| `wrong_confidence_delta` | `float` | `−0.40` | \(\Delta_c\) for `wrong`, pre-\(w\) |
| `min_salience` | `float` | `0.01` | Floor for `adjust_feedback_state`'s salience update |
| `min_confidence` | `float` | `0.0` | Floor for both `reinforce()`'s and `adjust_feedback_state()`'s confidence update |
| `max_confidence` | `float` | `1.0` | Ceiling for both `reinforce()`'s and `adjust_feedback_state()`'s confidence update |

24 fields total (verified against the dataclass). **Removed 2026-07-10** (5 fields, confirmed dead — see Known Failure Modes' history for why): `apply_outcome_to_schema_reward`, `missing_creates_memory`, `missing_replay_enabled` (read nowhere outside this dataclass), `stale_review_threshold`, `wrong_review_threshold` (only set a stored value nothing compared against — see `_STALE_REVIEW_PRESSURE`/`_WRONG_REVIEW_PRESSURE` module constants that replaced them). `SchemaStore.SALIENCE_CEILING` (`schema_store.py`, value `20.0`) is a shared module constant used by both `reinforce()` and `adjust_feedback_state()`, not a `FeedbackConfig` field.

## Key Invariants

1. **`missing` and `too_much_context` never mutate schema state.** Their label mapping hardcodes `salience_delta = confidence_delta = 0.0`; they only ever produce a `context_feedback_events` row. (Testable: assert schema fields unchanged after either label.)
2. **Outcome is orthogonal to memory-quality reinforcement.** There is no code path from `outcome_reward` back into schema state — a `useful` label reinforces its schemas even when `outcome="failure"`, and a `wrong` label penalizes even when `outcome="success"`.
3. **`useful_confidence_delta` is applied via `reinforce()`'s `confidence_delta` parameter, clamped to `[min_confidence, max_confidence]`.** (Testable: from a starting confidence below `max_confidence`, a `useful` call with a nonzero `useful_confidence_delta` moves confidence by exactly `delta * source_weight`, clamped.) Fixed 2026-07-10 — previously silently dropped (see Known Failure Modes' history).
4. **`review_pressure` is a fixed, informational constant per label (0.7 for `stale`, 1.0 for `wrong`) and gates nothing.** `needs_review` is set unconditionally by `apply_stale_wrong_review`, independent of `review_pressure`'s value — there was never a config knob that could change this even before the (now-removed) threshold fields were deleted 2026-07-10.
5. **`reinforce()` and `adjust_feedback_state()` share the same salience ceiling (`SchemaStore.SALIENCE_CEILING = 20.0`) since 2026-07-10.** Before that fix, only `reinforce()` (the `useful` path) had a ceiling; `adjust_feedback_state()` (partial/irrelevant/stale/wrong) had none, so a schema reinforced exclusively via `partially_useful` could grow past 20.0 while an otherwise-identical `useful`-reinforced schema could not.
6. **`needs_review=1` (boolean) never excludes a schema from default-mode retrieval eligibility** — only a `status` value other than `"active"` does, and only the `wrong` + `outcome=="failure"` path ever writes a non-`"active"` status. The noise-score demotion rule (`\(N_{\text{neg}} \geq 3\), N_{\text{used}}=0\)`) sets the boolean flag only, producing a soft ranking penalty via `context_noise_score`, not hard exclusion.
7. **Caller-supplied context fields always win over auto-derived ones.** `_derive_context_fields()` only fills in `None` values; a caller passing an explicit `scope_id`/`goal`/etc. is never overridden by the stored snapshot.
8. **Feedback events persist even with no matching prior snapshot.** If `retrieval_id` has no row in `context_recall_events`, `retrieval_feedback()` synthesizes a minimal parent row before inserting the feedback row — feedback is never silently dropped for lacking a snapshot.
9. **Procedure-id fields are accepted, persisted, and never acted upon.** `used_procedure_ids`/`irrelevant_procedure_ids`/etc. are written verbatim into `context_feedback_events` JSON columns, but `FeedbackService._parse_procedure_ids` is a no-op lambda (`services/feedback.py:33-35`, "removed Phase 1 P1") — no schema/procedure state is ever touched from these fields.
10. **`context_noise_score` tracking no longer requires `scope_id`.** **Fixed 2026-07-10** — the counting query used to filter `WHERE scope_id IS NOT NULL`, silently excluding scope-less feedback events with no error or warning; that filter was removed since the arithmetic never cared about the *value* of `scope_id`, only whether a row existed. (Testable: identical repeated `irrelevant` calls with and without `scope_id` now produce the same `context_noise_score`.) `scope_id` is still used elsewhere (cross-scope generalization, an unrelated computation) — see Relationship to Other Modules.
11. **`apply_learning=False` gates only the direct salience/confidence/status mutations, not the noise-score/`needs_review`-demotion mechanism.** `refresh_utility()` runs unconditionally for every feedback-touched schema id regardless of `apply_learning`, because it recomputes `context_noise_score` directly from the always-persisted `context_feedback_events` rows. (Testable: with `apply_learning=False`, repeated `irrelevant` marks still raise `context_noise_score` and can still set `needs_review=True`, while salience/confidence stay unchanged.) Discovered 2026-07-10.
12. **Only schema ids are parseable from the memory-id lists.** `_parse_schema_ids` (`services/feedback.py:349-357`) only accepts strings prefixed `sch_`; any other id shape (raw int, episode id, malformed string) is silently dropped from that feedback event's applied changes — no error is raised.
13. **A labile (`needs_review=True`) schema is not stuck.** Three independent channels can clear it: an explicit `useful`/`partially_useful` mark (immediate), `_RECONSOLIDATION_RECOVERY_RECURRENCE` (3) genuine reactivations since being flagged (passive, gradual), or Consolidation's `reconsolidate_labile_schemas()` replaying it against a neighbor (active, per-consolidation-pass). Fixed 2026-07-10 — before this, nothing ever cleared the flag. See "Labile State & Reconsolidation" above.
14. **Demotion wins over passive recovery on the same call.** If a schema's `_update_utility_scores` call simultaneously satisfies the noise-demotion condition (\(N_{\text{neg}} \geq 3, N_{\text{used}}=0\)) and the recurrence-recovery condition, it stays flagged — explicit accumulated negative feedback is treated as stronger evidence than passive reactivation.

## Implementation Files

| File | What It Implements |
|------|-------------------|
| `slowave/core/feedback.py` | `FeedbackSignal`, `FeedbackConfig`, label/outcome validation, `feedback_signal_for()` — pure functions, no I/O |
| `slowave/core/services/feedback.py` | `FeedbackService` — `record_retrieval()`, `retrieval_feedback()`, `_derive_context_fields()`, backward-compat wrappers `record_context_recall()`/`context_feedback()` |
| `slowave/core/engine.py` | `SlowaveEngine.__init__` constructs the single `FeedbackService` instance; `record_retrieval`/`retrieval_feedback` are thin pass-through delegates (lines ~770-777) |
| `slowave/ops.py` | `ops.activate()`/`ops.recall()` call `record_retrieval()` after retrieval completes; `ops.reinforce()` calls `retrieval_feedback()` |
| `slowave/mcp/tools.py` | `slowave_reinforce` MCP tool (lines 257-293) — the only public entry point for applying feedback; `slowave_activate`/`slowave_recall` implicitly populate the snapshot this tool reads |
| `slowave/symbolic/schema_store.py` | `reinforce()`, `adjust_feedback_state()`, `update_status()`, `refresh_utility()`/`_update_utility_scores()` — the actual schema-state mutations feedback drives |
| `slowave/core/context.py` | Reads `context_noise_score` at ranking time (`_NOISE_PENALTY_WEIGHT`, lines 146, 557-562); `_eligible()` status-based filtering that determines whether demotion actually excludes a schema |
| `slowave/storage/schema.sql` | `context_recall_events`, `context_recall_items`, `context_feedback_events` table definitions (lines 248-331) |
| `tests/unit/test_context_feedback.py` | 26 tests covering signal mapping, snapshot persistence, per-label reinforcement/penalty, source-weight asymmetry, outcome independence |
| `tests/unit/test_feedback_review_gating.py` | Gap-fill tests: `needs_review`-boolean-vs-`status`-string eligibility, the `scope_id` fix, shared salience ceiling, `useful_confidence_delta` wiring, the `apply_learning`/noise-demotion interaction, `TestFeedbackClearsLability`, F1-F4 ablation regression coverage |
| `tests/unit/test_labile_lifecycle.py` | Recurrence-clears-lability (`TestRecurrenceClearsLability`) and `Consolidator.reconsolidate_labile_schemas()` (`TestReconsolidateLabileSchemas`) — built against a real `SlowaveEngine`/`GeometricContradictionJudge`, no judge mocking |
| `slowave/core/consolidation.py` | `Consolidator.reconsolidate_labile_schemas()`, `_schema_to_latent_view()` — the active replay-based reconsolidation channel; see `05-consolidation.md` |
| `slowave/core/services/consolidation.py` | `ConsolidationService.consolidate_once()` calls `reconsolidate_labile_schemas()` every pass, surfaced under the `"reconsolidation"` result key |
| `private/docs/consolidation/scripts/feedback_ablation.py` | Scored micro-benchmark (AUC-style separation of synthetic good/bad schemas by salience and `context_noise_score`, under `apply_learning`/`scope_id` ablations) — substitutes for the external-benchmark coverage no project eval script provides for this module |

## Diagnostic Hooks

| Metric | What It Measures | How to Instrument |
|--------|-----------------|-------------------|
| `context_noise_score` distribution + `needs_review` boolean count | Is the negative-feedback accumulation mechanism actually firing on real usage? | Already persisted in `schemas.facets_json`; query directly (`json_extract(facets_json,'$.context_noise_score')`) — no new instrumentation needed, see Phase 4 |
| Fraction of `context_feedback_events` rows with `retrieval_type="context"` vs `"recall"` | Which `source_weight` dominates real traffic — is the 0.5/1.0 asymmetry actually exercised at different rates? | `SELECT retrieval_type, COUNT(*) FROM context_feedback_events GROUP BY retrieval_type` |
| `status` value distribution on `schemas` | How many schemas are ever hard-excluded (Phase 4's `update_status` path) vs. only soft-penalized (boolean `needs_review`) | `SELECT status, needs_review, COUNT(*) FROM schemas GROUP BY status, needs_review` |
| `used_procedure_ids`/etc. non-empty rate | Is any caller still populating the dead procedure-id fields, i.e. would resurrecting procedure handling actually matter to real traffic? | `SELECT COUNT(*) FROM context_feedback_events WHERE used_procedure_ids_json != '[]'` |
| Malformed-id drop rate | How often does `_parse_schema_ids` silently drop a caller-supplied id (Invariant 12)? | Would require instrumenting `_parse_schema_ids` to log/count non-`sch_`-prefixed inputs — not currently instrumented |
| `context_feedback_events` volume vs. `context_recall_events` volume | What fraction of retrievals ever receive feedback at all — is the loop closing in practice? | `SELECT (SELECT COUNT(*) FROM context_feedback_events) * 1.0 / (SELECT COUNT(*) FROM context_recall_events)` |
| Good/bad separation AUC (salience, `context_noise_score`) | Does the mechanism, end to end, actually separate schemas by quality under realistic (noisy) repeated feedback? | `scripts/feedback_ablation.py` — scored micro-benchmark, not a one-off diagnostic; baseline AUC 1.0 on both metrics at default settings (12 good/12 bad schemas, 20 rounds, 20% label noise, seed 42) |
| Labile-schema recovery channel breakdown | Of schemas that stop being labile, how many resolved via explicit feedback vs. passive recurrence vs. Consolidation's replay? | Not currently instrumented — would need a facet recording which channel last cleared `needs_review`, e.g. `labile_resolved_via` |
| `reconsolidate_labile_schemas()` outcome distribution | Is Consolidation's replay path actually resolving labile schemas, or mostly landing on "inconclusive" (no related neighbor)? | `Consolidator.reconsolidate_labile_schemas()`'s return dict (`examined`/`restabilized`/`superseded`/`contradicted`/`inconclusive`) — surfaced in `consolidate_once()`'s result under the `"reconsolidation"` key, not yet aggregated across passes |

## Parameter Sensitivity

| Parameter | Direction | Effect | Sweep Range |
|-----------|-----------|--------|-------------|
| `apply_learning` | on/off | Off means direct salience/confidence/status mutations never happen — but the noise-score/`needs_review`-demotion mechanism still runs regardless (Invariant 11) | on, off |
| `apply_positive_learning` | on/off | Off disables all `useful`/`partially_useful` reinforcement | on, off |
| `apply_negative_learning` | on/off | Off disables all `irrelevant` penalization | on, off |
| `apply_stale_wrong_review` | on/off | Off disables `stale`/`wrong` salience/confidence penalties and both review-flagging paths | on, off |
| `context_feedback_weight` / `recall_feedback_weight` | ↑ | Larger schema deltas per feedback event from that source; ratio between the two determines whether context-tool feedback or recall-tool feedback dominates cumulative drift | 0.0–1.0 each, independently |
| `useful_salience_delta` / `*_salience_delta` (5 labels) | ↑ (magnitude) | Faster salience movement per event; no external benchmark exists to optimize against — these are calibrated by design intent, not swept. `scripts/feedback_ablation.py` can measure separation AUC under a sweep if this is ever revisited. | 0.02–0.5 (rough range consistent with current defaults) |
| `min_salience` | ↑ | Raises the floor negative feedback can push a schema's salience to; both `reinforce()` and `adjust_feedback_state()` now share the same ceiling (`SALIENCE_CEILING`), so this only affects the floor side | 0.0–0.5 |

## Known Failure Modes

| Symptom | Likely Cause | Diagnostic Signal |
|---------|-------------|-------------------|
| A schema repeatedly marked `irrelevant`/`stale`/`wrong` keeps appearing in default-mode retrieval | Boolean `needs_review=1` demotion only applies a soft `context_noise_score` ranking penalty; it never changes `status`, and only `status != "active"` is hard-excluded in default mode | `SELECT status, needs_review FROM schemas WHERE id=?` — if `status="active"` and `needs_review=1`, the schema is still fully eligible, just down-ranked by `0.30 * noise` |
| A caller passes episode ids or raw ints in `used_memory_ids` and sees no reinforcement | `_parse_schema_ids` only accepts `sch_`-prefixed strings; anything else is silently dropped, no error | `result["applied"]["reinforced"]` empty despite non-empty `used_memory_ids` in the call |
| No external benchmark run shows any Δ from toggling feedback-related flags | None of the 6 project benchmarks (`locomo_eval.py`, `longmemeval_eval.py`, `stalememory_eval.py`, wiki, dmr, temporal) ever call `retrieval_feedback()` — this module requires multi-turn, feedback-labeled interaction that offline single-shot benchmarks don't produce. Use `scripts/feedback_ablation.py`'s scored AUC benchmark instead. | Grep the eval scripts for `feedback`/`reinforce` — zero hits (confirmed 2026-07-09) |
| `apply_learning=False` was expected to fully quiesce a schema, but `needs_review` still flips to `True` | The noise-score demotion mechanism (Phase 3) is not gated by `apply_learning` — only direct salience/confidence/status mutations are (Invariant 11) | Salience/confidence stay put but `context_noise_score`/`needs_review` still move; confirmed by `scripts/feedback_ablation.py`'s `apply_learning=False` scenario (`noise_score_auc` stays 1.0 while `salience_auc` collapses to 0.5) |
| A schema flagged labile by `decay_unused()` (pure disuse, no related evidence) never seems to resolve | `reconsolidate_labile_schemas()`'s neighbor search found nothing above `related_schema_cosine` — the "inconclusive" outcome, left labile by design (passive extinction, not a bug) | `Consolidator.reconsolidate_labile_schemas()`'s `inconclusive` count; the schema's `needs_review` stays `True` across consolidation passes with no `recurrence_count_at_flag` progress either |

**Fixed 2026-07-10** (previously listed here as failure modes, now resolved — kept for history): `stale_review_threshold`/`wrong_review_threshold` having no observable effect (fields removed, not wired); `useful_confidence_delta` not changing confidence on `useful` feedback (now wired into `reinforce()`); `apply_outcome_to_schema_reward`/`missing_creates_memory`/`missing_replay_enabled` changing nothing (all three fields removed rather than wired — building the underlying features remains an open product decision, not resolved by this fix); a schema marked `irrelevant`/`stale`/`wrong` with no `scope_id` never accumulating `context_noise_score` (the `scope_id IS NOT NULL` filter was removed — see Invariant 10 — so this is no longer reproducible).

<sub>Verified against `scripts/feedback_ablation.py` (both the original F1-F7/Q4 ablation and its 2026-07-10 rewrite into a scored AUC benchmark) and, for the noise-score/status distinction, cross-checked against real usage in `~/.slowave/slowave.db` (2026-07-09).</sub>

## Relationship to Other Modules

| Module | Relationship |
|--------|-------------|
| `05-consolidation.md` | Feedback operates on schemas *after* consolidation creates them — it never creates, merges, or supersedes a schema itself, only reinforces/penalizes/flags existing ones. **Since 2026-07-10, the relationship is bidirectional**: Consolidation's `reconsolidate_labile_schemas()` reads the `needs_review` flag this module sets and can itself change `status` (superseded/contradicted) or clear the flag — the one exception to "Feedback never changes retrieval eligibility except via the wrong+failure path." |
| `09-context.md` | Downstream consumer of `context_noise_score` (computed here, read there via `_NOISE_PENALTY_WEIGHT`) and of `status`/`needs_review` for eligibility gating; `context.py`'s `_eligible()` is where the "does demotion actually exclude?" question is answered |
| `02-salience.md` | Shares the same `schemas.salience` field but through entirely separate write paths — salience decay/reinforcement-on-recall (Module 2) vs. feedback-driven `reinforce`/`adjust_feedback_state` (this module); both paths accumulate onto the same column, neither is aware of the other |
| `06-retrieval.md` | `record_retrieval()` is called by `RetrievalService`/`ops.recall()` immediately after a retrieval completes, to snapshot what would later be referenced by a feedback call on the same `retrieval_id` |
| MCP surface (`slowave/mcp/tools.py`) | `slowave_activate`/`slowave_recall` → `record_retrieval()`; `slowave_reinforce` → `retrieval_feedback()`. This module is the entire implementation behind the "reinforce" step of the 5-verb cognitive cycle described in this project's own tooling |
