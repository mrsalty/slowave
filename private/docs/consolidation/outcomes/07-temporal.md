# Temporal — Outcome Notes (2026-07-09)

## What Was Done

### Phase 1-3: Audit + Documentation
- Audited `core/07-temporal.md` (125 lines) vs `temporal.py`/`retrieval.py`/`services/retrieval.py`: the Stage 7 sinusoidal-encoding math was already correct (scales, periods, dimension all matched code), but the Stage 10 anchor-estimation section was stale — the 12-probe compass table listed phrases and displacements that don't exist in `_TEMPORAL_PROBES` (invented "a few minutes ago"/"an hour ago" probes that aren't in the code; missing the real "two months ago"/"six months ago"/"two years ago" probes), and the documented `softmax_temperature` default (0.15) didn't match the constructor's actual default (0.05). The doc also lacked every template section past "Key Invariants" — no Implementation Files, Diagnostic Hooks, Parameter Sensitivity, Known Failure Modes, or Relationship to Other Modules.
- Rewrote `core/07-temporal.md` → full template compliance: corrected probe table, corrected default, added a data-flow diagram spanning both mechanisms, 7 invariants, 7 implementation file rows, 4 diagnostic hooks (one previously nonexistent), 5 parameter sensitivity rows, 5 failure modes, 4 cross-module references. Flagged a second, independent staleness bug found in the implementation itself: `TemporalProbe`'s own docstring claims a default temperature of 0.1 that the constructor has never used (real default 0.05) — a documentation drift bug inside the source file, not just the generated doc.
- Created `plans/07-temporal.md`: 7 diagnostic questions, a 1-flag ablation matrix (only `use_temporal` is wired end-to-end; everything else in `TemporalProbe` has no config path at all), grid search ranges, micro-benchmark gap-fill spec (zero prior coverage of `TemporalProbe`).

### Phase 4: Diagnostic Instrumentation
Added `anchor_fired`/`anchor_displacement_s` to `RecallResult` (`services/retrieval.py`) — populated unconditionally on every `recall()` call, since `TemporalProbe.estimate_anchor()` already runs unconditionally regardless of `use_temporal` (core doc Invariant 7). Wired through both `locomo_eval.py` and `longmemeval_eval.py`: per-question fields on `QAResult`/`QuestionResult`, aggregated into each script's summary JSON under `diagnostics.temporal` (overall + per-category `anchor_fired_rate`/`mean_displacement_s`). Also added a `--no-temporal` flag to `locomo_eval.py` (LongMemEval already had one) and a `--temporal-weight` flag for the Phase 6 grid search.

**Baseline run (LongMemEval oracle, `--no-consolidate`, limit=10/category, 60 questions):** `anchor_fired_rate` = **65% overall** — Stage 10 is not dead weight by any reasonable threshold.

### Phase 5: Ablation Matrix (A1-A4)

| Benchmark | `use_temporal` ablation result |
|---|---|
| LongMemEval (60 q) | **Exactly 0.0pp on every one of 6 categories**, including `temporal-reasoning` |
| LoCoMo (497 q) | **-0.6pp overall**; category 2 "temporal" -2.22pp, category 1 "single-session" -1.35pp; categories 3/4/5 exactly 0.0pp |

### Phase 6: Parameter Tuning
`temporal_weight` grid search on LoCoMo categories 1+2 (the only sensitive slices): {0.0, 0.10, 0.25, 0.40, 0.60}. Flat, non-monotonic landscape (all within ~2pp, consistent with single-question flips at n=74/n=90). Current default (0.25) is the single best value for category 1 and within 1.1pp of the best observed value for category 2. **No change** — documented as the flat case per the project's own gate.

### Phase 7: Micro-Benchmark Tests (MANDATORY)
`tests/unit/test_temporal_probe.py` — 12 new tests, net-new coverage (this class had zero prior tests): dead-zone gate (fires and doesn't-fire cases, including the `atemporal_margin=0` tie boundary), the softmax-bound invariant (displacement never exceeds the most extreme matched probe, checked across 5 temperature values), sharper-temperature-concentrates-weight, determinism, probe-embedded-once-no-reembedding (call-count assertion), internal query normalization, and 3 `TemporalContext` pure-function sanity checks (determinism, self-similarity, dimension). All pass in <1s. Full unit suite (394+ tests) still passes after the `RecallResult` field additions — zero regressions.

## Key Findings (in the order discovered)

### 1. The Stage 7 encoding math was already right; Stage 10's compass table was fabricated
Unlike Consolidation (wrong thresholds entirely) or Graph (wrong dominant parameter), this module's core-doc staleness was narrower: someone had generated a plausible-looking but non-existent probe table (finer-grained, with minute/hour entries) instead of transcribing the real 12-phrase `_TEMPORAL_PROBES` tuple. A reader trusting the old doc would look for "an hour ago" behavior that the system has never implemented.

### 2. `anchor_fired_rate` tracks phrasing, not the benchmark's category taxonomy — a correction mid-investigation
The plan's Q4 proposed using LongMemEval's category label (`temporal-reasoning` vs. everything else) as ground truth for whether the dead-zone gate is well-calibrated. The baseline run refuted this framing directly: `single-session-assistant` fires at 90% — identical to `temporal-reasoning` — while `single-session-preference` is the real outlier at 10%. Reading the actual questions explains it: `single-session-assistant` questions are phrased with backward-reference language ("checking back on our previous conversation", "I wanted to revisit"), while `single-session-preference` questions are present/future-tense ("Can you recommend...", "upcoming trip"). **The category taxonomy labels *what kind of fact* is being asked about; the compass tracks *how the question is phrased*. These are different axes.** Q4 as originally scoped (precision/recall against category label) was abandoned as measuring the wrong thing, not attempted and failed.

### 3. The mechanism is architecturally alive but benchmark-dependent, mirroring the Consolidation module's core finding
LongMemEval shows **zero** measurable effect from `use_temporal` on every category despite 65% anchor-fire rate and a real, working additive re-rank (confirmed alive by the LoCoMo result and by `test_temporal_boost_changes_episode_ranking` in `test_retrieval_pipeline_plumbing.py`). LoCoMo shows a real, benchmark-specific effect (-2.22pp on its dedicated temporal category) that clears the project's 1pp significance gate. Two honestly-measured benchmarks disagreeing this cleanly is itself the finding — a real mechanism can be measurable on one benchmark and invisible on another for reasons that have nothing to do with the mechanism being broken, most likely because LongMemEval's keyword-overlap hit metric at `top_k=5` is less sensitive to which specific episode among near-ties gets included than LoCoMo's answer-length-sensitive scoring is.

### 4. Grid search confirms the current default without moving it
`temporal_weight=0.25` was never swept before. The sweep found a flat, noisy landscape at real-benchmark sample sizes (n=74/n=90 per category) — not the kind of landscape a grid search would resolve further without a much larger benchmark. 0.25 is already at or near the empirical optimum on both sensitive categories; kept as-is.

## Open Items (explicitly not addressed)

- **`softmax_temperature`/`atemporal_margin` recalibration (Q4/Q7):** not swept. The plan's original ground truth (category label) was shown to be the wrong target (Finding 2); a real recalibration needs phrasing-level annotation (does the question contain backward-reference language?) that this investigation did not produce. `TemporalProbe` also has zero config wiring (no `TemporalProbeConfig`, no `SlowaveConfig` field, no CLI flag) — any future sweep needs Phase 4's Step-4 wiring decision resolved first (a standalone script bypassing the engine is the cheaper option, per the plan).
- **Probe-set coverage gap (Q6):** the compass has no minute/hour-scale probe — the finest past probe is "yesterday" (−1 day). Same-day backward-reference queries ("this morning", "an hour ago") necessarily either fall into the dead zone or get mapped to "yesterday". Not measured directly (would need hand-picked same-day query examples, which neither benchmark reliably contains); flagged as a structural follow-up, not a threshold-tuning task.
- **`TemporalProbe` docstring drift — fixed.** The in-source docstring's claimed default (0.1) didn't match the constructor's real default (0.05); corrected to 0.05 (`temporal.py:211`), no behavior change.
- **Why LongMemEval is insensitive to `use_temporal` while LoCoMo isn't:** plausible mechanism proposed (Finding 3) but not confirmed by direct instrumentation (e.g., comparing episode-vs-schema hypothesis-text contribution ratios between the two benchmarks). Would require a dedicated diagnostic beyond this investigation's scope.

## PROGRESS.md Update

Module 5 (Temporal) status: **not started → COMPLETE**. Benchmark deltas: LongMemEval 0.0pp (all categories) from `use_temporal`; LoCoMo -0.6pp overall / -2.22pp on category 2 from disabling `use_temporal` (i.e. `use_temporal=True` is a net positive, concentrated on the temporal and single-session categories). No parameter changes — `temporal_weight=0.25` confirmed near-optimal by grid search, kept as-is.
