# 07 — Temporal Improvement Plan

**Status:** planning
**Created:** 2026-07-09
**Depends on:** `core/07-temporal.md` (rewritten 2026-07-09, Phase 2 complete)

## What's Already Done

Unlike Consolidation, this module's existing coverage is split unevenly across its two mechanisms:

| Test file | Covers |
|-----------|--------|
| `tests/unit/test_retrieval_pipeline_plumbing.py` (SP-2) | Stage 7 sinusoidal encoding + additive score integration — proves a controlled `temporal_anchor_ts` flips episode ranking vs pure cosine |
| `tests/unit/test_spreading_path_completion.py` | Uses `use_temporal=False` to isolate spreading from temporal, but does not itself test temporal behavior |

**Gap:** `TemporalProbe` (Stage 10 — anchor estimation, the dead-zone gate, softmax weighting, displacement math) has **zero** existing test coverage. No test constructs a `TemporalProbe` directly or calls `estimate_anchor()`. This is the mirror of the "Phase 7 partially pre-satisfied" finding from Consolidation, except here it cuts the other way: the *encoding* half is covered, the *anchor-estimation* half is not.

## Priority Finding (motivates Q1/Q4 below)

`TemporalProbe`'s tunable parameters (`softmax_temperature`, `atemporal_margin`, the probe set) are **not exposed anywhere** — no `TemporalProbeConfig` dataclass, no `SlowaveConfig` field, no CLI flag on any eval script (`core/07-temporal.md` Configuration section). `SlowaveEngine` always constructs `TemporalProbe(self.encoder.encode)` with every other argument at its hardcoded class default. Separately, **no diagnostic anywhere records whether `estimate_anchor()` ever returns something other than `now_ts`** — this is PROGRESS.md's standing "key question" for this module (does `TemporalProbe` actually fire, and on what fraction of queries?), and right now the honest answer is "unknown — never measured." Both gaps must close before any threshold can be meaningfully swept.

## UPDATE (2026-07-09, after Phase 4 baseline run)

Q1 and Q6 are answered by one LongMemEval run (oracle dataset, `--no-consolidate`, limit=10/category, 60 questions, new `anchor_fired`/`anchor_displacement_s` diagnostics): **overall `anchor_fired_rate` = 65%** — nowhere close to 0%, so Stage 10 is not dead weight by the Q1 decision threshold. But the per-category breakdown refutes this plan's original framing of Q4 (using the category label as ground truth for "is this query temporal"):

| Category | anchor_fired_rate |
|---|---|
| `single-session-assistant` | **90%** |
| `temporal-reasoning` | 90% |
| `multi-session` | 80% |
| `knowledge-update` | 60% |
| `single-session-user` | 60% |
| `single-session-preference` | **10%** |

`temporal-reasoning` is not the outlier — `single-session-assistant` fires at the same 90% rate, and `single-session-preference` (not `temporal-reasoning`) is the real outlier at the low end. Inspecting the actual question text explains it directly: `single-session-assistant` questions are phrased with backward-reference language ("checking back on our previous conversation", "I wanted to revisit", "remind me what you told me earlier"), while `single-session-preference` questions are present/future-tense ("Can you recommend...", "upcoming trip", "this weekend"). **The LongMemEval category taxonomy labels *what kind of fact* is being asked about, not *whether the question is phrased with backward-referencing language* — these are different axes, and Stage 10's dead-zone gate correctly tracks the latter, not the former.** Q4's originally proposed ground truth (category label) is invalid; a corrected version would need phrasing-level annotation (does the question contain backward-reference language?), not the existing category field. Given this, Q4 as originally scoped is not pursued further — the finding above answers the more important question (does the gate discriminate on *something* real) more usefully than forcing a mismatched ground truth would have.

This also means the large mean displacements observed (roughly −4 to −29 million seconds, i.e. 1–11 months) are not obviously wrong: LongMemEval oracle sessions are dated across a wide span, and the compass has no probe finer than "yesterday" (Q6) — a backward-referencing query with no more specific temporal cue than "earlier" or "our previous conversation" will land wherever the softmax lands among the 12 landmarks, which for this dataset's actual session date spread pulls toward the multi-month probes. Not a bug; a direct consequence of the probe set's coverage (Q6) combined with genuinely wide inter-session gaps in this dataset.

## Diagnostic Questions

| # | Question | Why It Matters |
|---|----------|-----------------|
| Q1 | What fraction of queries get a non-`now_ts` anchor from `estimate_anchor()`, overall and split by benchmark category? | Direct answer to the standing "key question." If near-0% even on categories expected to be temporal-heavy (LongMemEval `temporal-reasoning`, LoCoMo category 2), Stage 10 is dead weight in practice regardless of its unit-level correctness. |
| Q2 | Does disabling `use_temporal` (the only wired boolean) move LongMemEval's `temporal-reasoning` category score, and does it move the *overall* score by a different amount? | `--no-temporal` already exists in `longmemeval_eval.py`; this is the cheapest possible ablation and answers "is the additive Stage 7 term alive" without writing new code. |
| Q3 | Does the same ablation move LoCoMo's category-2 ("temporal") accuracy? | `locomo_eval.py` has no `--no-temporal` flag today — must be added first. LoCoMo's temporal category is a second, independent signal from a different benchmark's question distribution. |
| Q4 | Is `atemporal_margin=0.12` / `softmax_temperature=0.05` well-calibrated for the encoder actually in use, using LongMemEval's category label as ground truth (`temporal-reasoning` = should fire; other categories = should mostly stay at `now_ts`)? | The code comment calibrating these values cites a specific encoder (`bge-small-en-v1.5`) and a specific informal calibration set — never verified against a labeled benchmark. LongMemEval's category field is a ready-made ground truth for exactly this. |
| Q5 | When the anchor *does* fire, does it change which episodes land in the final top-k — independent of `temporal_weight`? | `temporal_anchor_ts` changes what `q_temporal` *is*; `temporal_weight` changes how much it's weighted. These are separable effects and the ablation matrix below only tests the latter unless this is checked explicitly. |
| Q6 | Given the probe set has no minute/hour-scale entries (finest past probe is "yesterday", −1 day), do same-day temporal queries ("this morning", "an hour ago") get silently absorbed into the dead-zone and treated as atemporal? | Structural gap in probe coverage, independent of threshold tuning — no amount of `atemporal_margin` sweeping fixes a missing probe. |
| Q7 | Is it worth adding `TemporalProbeConfig` + `SlowaveConfig` wiring + CLI flags before sweeping Q4/Q6, or is a standalone diagnostic script (bypassing `SlowaveEngine` entirely) cheaper for this investigation? | Mirrors the Consolidation module's decision to expose `near_dup_guard_cosine` before running B2 — but here the sweep target (`TemporalProbe`) has no engine-level side effects to worry about, so a standalone script may be sufficient and cheaper than full wiring. |

## Ablation Matrix

Only one flag in this module is currently wired end-to-end: `use_temporal`. Everything else that could be "ablated" (`softmax_temperature`, `atemporal_margin`, the probe set) has no config path at all (Priority Finding) — those are grid-search targets (see below), not ablation-matrix entries, once Q7 is resolved.

| # | use_temporal | temporal_weight | Eval | Slice | Disables |
|---|---|---|---|---|---|
| A1 | True | 0.25 (default) | LongMemEval | overall + `temporal-reasoning` category | **baseline** |
| A2 | False | 0.0 | LongMemEval | overall + `temporal-reasoning` category | Stage 7 additive term entirely (Q2) |
| A3 | True | 0.25 (default) | LoCoMo | overall + category 2 ("temporal") | **baseline** — requires adding `--no-temporal` to `locomo_eval.py` first |
| A4 | False | 0.0 | LoCoMo | overall + category 2 ("temporal") | Stage 7 additive term entirely (Q3) |

A1/A2 need no new code (`--no-temporal` already exists in `longmemeval_eval.py`). A3/A4 needed a `--no-temporal` flag added to `locomo_eval.py` (done 2026-07-09), mirroring the existing pattern.

**A1/A2 results (LongMemEval oracle, `--no-consolidate`, limit=10/category, 60 questions):** `use_temporal` moves the score by **exactly 0.0pp on every one of the 6 categories**, including `temporal-reasoning` (90.0% both). This despite `anchor_fired_rate=65%` overall — the mechanism is live (Stage 10 fires, Stage 7 re-ranks) but invisible to this benchmark's keyword-overlap metric at this config (`top_k=5`, `episodic_top_k` default). Matches the "architectural disconnect" pattern from `outcomes/05-consolidation.md`: a real, firing mechanism with zero measurable effect on a specific benchmark's metric is not automatically a bug.

**A3/A4 results (LoCoMo, consolidate, limit=3, 497 questions):** `use_temporal` moves the score by **-0.6pp overall**, concentrated in exactly the two categories the core doc's Invariant 3 would predict matter most for recency-sensitive disambiguation:

| Category | baseline (temporal on) | no_temporal | Δ |
|---|---|---|---|
| 1 single-session | 79.73% | 78.38% | −1.35pp |
| 2 temporal | 62.22% | 60.00% | **−2.22pp** |
| 3 commonsense | 57.14% | 57.14% | 0.0pp |
| 4 multi-session | 89.5% | 89.5% | 0.0pp |
| 5 adversarial | 88.39% | 88.39% | 0.0pp |

Category 2 clears the project's 1pp gate; categories 3/4/5 are exactly flat, matching LongMemEval's global flatness. **Conclusion: the mechanism is alive and LoCoMo (not LongMemEval) is the benchmark that can see it** — proceed to grid search on `temporal_weight`, scoped to categories 1+2 where the signal lives.

## Grid Search

**Ran 2026-07-09** (LoCoMo, consolidate, limit=3, `--categories 1 2` — the only categories A3/A4 showed sensitivity in):

| `temporal_weight` | cat 1 (single-session) | cat 2 (temporal) |
|---|---|---|
| 0.00 (= `--no-temporal`) | 78.38% | 60.00% |
| 0.10 | 77.03% | 61.11% |
| **0.25 (current default)** | **79.73%** | 62.22% |
| 0.40 | 78.38% | 61.11% |
| 0.60 | 78.38% | **63.33%** |

**Decision: no change.** The landscape is flat and non-monotonic across 0.10-0.60 (all values within ~2pp of each other, consistent with single-question flips at n=74/n=90 sample sizes — not a real gradient). The current default (0.25) is the single best value for category 1 and within 1.1pp of the best observed value for category 2 (0.60's 63.33% vs 0.25's 62.22% — a ~1-question difference on n=90). No value dominates on both categories simultaneously. Per the project's Phase 6 gate ("at least one parameter tuned from data, **or documented as flat — current value is optimal**"), this is the documented-flat case — `temporal_weight=0.25` stays.

`softmax_temperature`/`atemporal_margin` sweeps (Q4/Q7) were **not run** — LongMemEval's per-category `anchor_fired_rate` breakdown (see UPDATE above) already showed the originally proposed ground truth (category label) doesn't cleanly separate temporal from atemporal phrasing, so a precision/recall sweep against that label would optimize against the wrong target. A real sweep would need phrasing-level annotation this investigation did not produce — left as an explicit open item (see outcome doc).

Probe set composition (Q6, minute/hour coverage gap): not swept — structural, not a scalar grid; left as a follow-up experiment.

## Diagnostic Instrumentation Spec (Phase 4)

No `TemporalStats`-equivalent exists (unlike `ConsolidationStats`). Minimal addition, at the eval-script level rather than inside the engine (since `TemporalProbe` is stateless per call and the engine has no persistent stats object for retrieval):

```python
# In RetrievalService.recall() (services/retrieval.py:143-157), or a thin
# wrapper the eval scripts call directly:
anchor_fired: bool          # anchor_ts != now_ts
anchor_displacement_s: int  # anchor_ts - now_ts (0 when not fired)
```

Wire into `longmemeval_eval.py`'s per-question result (it already has a `question_type`/category field, so aggregation by category is free) and `locomo_eval.py`'s per-question result (category field already exists per `locomo_eval.py:60`). Aggregate into each script's summary JSON as `anchor_fired_rate` overall and per-category — directly answers Q1.

## Micro-Benchmark Gap (Phase 7)

`TemporalProbe` has no tests at all. Add `tests/unit/test_temporal_probe.py`, deterministic (fixed fake encoder, no real model load), covering:

- Dead-zone gate: a query embedding identical to the "now" probe returns `now_ts` unchanged; a query embedding identical to a past probe (with margin exceeding `atemporal_margin`) returns a shifted anchor.
- Softmax bound invariant (core doc Invariant 5): construct a query that maximally matches one past probe; assert `|anchor_ts - now_ts| <= |max single probe displacement|`.
- Determinism: same query embedding + same `now_ts` → identical `anchor_ts` across repeated calls.
- Probe embedding call count: a mock `encode_fn` is called exactly 12 times at `__init__` (once per probe) and zero additional times during `estimate_anchor()` (Invariant 6).
- `atemporal_margin=0` edge case: every query is treated as temporal (no dead zone) — boundary behavior check.

`TemporalContext` (Stage 7) is already covered end-to-end by SP-2 in `test_retrieval_pipeline_plumbing.py` — do not duplicate; that test already proves determinism-in-effect (same fixture reproduces the same ranking) and the additive-bonus mechanism. If a pure-unit test of `encode`/`encode_many`/`cosine` in isolation (no retrieval pipeline) is wanted for symmetry with the new probe tests, add it to the same new file rather than a separate one.

Keep new tests deterministic, <5s total, no external data — same bar as `test_graph_edge_quality.py`.

## Decision Thresholds

| Observed | Action |
|----------|--------|
| Q1: `anchor_fired_rate` < 5% even on `temporal-reasoning`/category-2 slices | Stage 10 is dead weight on real benchmark data — document, do not invest in threshold tuning (Q4/Q6 become moot), jump toward Phase 8 |
| Q1: `anchor_fired_rate` > 30% on temporal-heavy slices, < 10% elsewhere | Stage 10 is working as designed — proceed to Q4/Q6 calibration questions |
| Q2/Q3: `use_temporal` ablation moves temporal-heavy slice by > 1pp but overall by ~0pp | Additive term is a targeted, non-disruptive signal — no change needed, confirms current default is reasonable |
| Q2/Q3: `use_temporal` ablation shows ~0pp everywhere, including temporal-heavy slices | Stage 7's additive term is dead weight — matches the "ALL flags ~0pp → skip Phases 6-7" project gate; document and move to Phase 8 |
| Q4: labeled-category firing accuracy (precision/recall of anchor-fired vs `temporal-reasoning` label) is poor (e.g. < 60% either way) | `atemporal_margin`/`softmax_temperature` need recalibration for the current encoder — proceed to grid search |
| Q6: same-day queries systematically fall into the dead zone | Structural probe-coverage gap — note as a follow-up (add minute/hour probes), not a threshold-tuning task |

## Implementation Order

```
Step 1: Add --no-temporal to locomo_eval.py (mirrors longmemeval_eval.py pattern)          [15 min]
Step 2: Add anchor_fired/anchor_displacement_s diagnostics to both eval scripts             [30 min]
         ** Q1 answered from existing + new eval runs **
Step 3: Run A1/A2 (LongMemEval) and A3/A4 (LoCoMo) — overall + temporal-heavy slice         [15 min]
         ** Q2, Q3 answered — GO/NO-GO gate for Phase 6 **
Step 4: Resolve Q7 (wiring decision) — likely: standalone script constructing TemporalProbe
         directly with overridden kwargs, no engine/config changes needed                   [15 min]
Step 5: Using Step 4's script, compute anchor-fired precision/recall vs LongMemEval category
         labels at default (T=0.05, margin=0.12) and grid points                            [30 min]
         ** Q4 answered **
Step 6: Manually inspect same-day-phrased queries (LongMemEval/LoCoMo) for dead-zone
         absorption (Q6) — qualitative, small sample                                        [15 min]
Step 7: Grid search on temporal_weight (always) and softmax_temperature/atemporal_margin
         (only if Step 3 shows > 1pp)                                                       [30-60 min]
Step 8: Write test_temporal_probe.py                                                        [45 min]
Step 9: Update core/07-temporal.md defaults + Parameter Sensitivity if anything changed     [15 min]
```

## Phase Execution

| # | Task | Status |
|---|------|--------|
| 1 | Implementation audit | ✅ |
| 2 | Core doc rewrite | ✅ |
| 3 | Plan document | ✅ |
| 4 | Diagnostic instrumentation + baseline (Q1/Q6 answered) | ✅ |
| 5 | Ablation matrix (A1-A4) | ✅ |
| 6 | Parameter tuning (`temporal_weight` grid search — flat, no change) | ✅ |
| 7 | Micro-benchmark gap-fill (`tests/unit/test_temporal_probe.py`, 12 new tests) | ✅ |
| 8 | Outcome document + PROGRESS | ✅ |
