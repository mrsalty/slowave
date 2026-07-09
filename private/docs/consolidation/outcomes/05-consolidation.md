# Consolidation — Outcome Notes (2026-07-09)

## What Was Done

### Phase 1-3: Audit + Documentation
- Audited `core/05-consolidation.md` (110 lines) vs `consolidation.py`/`schema.py`/`schema_store.py`: doc cited the wrong thresholds entirely (supersession-manifold constants `SAME_SCOPE_COS_THRESHOLD`/`DIRECTION_THRESHOLD` from `engine.remember()`, Module 10 — not `GeometricContradictionJudge`, which is what this module actually uses)
- Rewrote `core/05-consolidation.md` → 410 lines: all 6 phases, 10 invariants, 8 diagnostic hooks, 9 parameter sensitivity rows, 7 failure modes, 24 implementation files
- Created `plans/05-consolidation.md`: 7 diagnostic questions, 8-row threshold ablation matrix (no boolean flags in this module — every knob is a continuous threshold), grid search ranges, micro-benchmark gap-fill spec

### Phase 4: Diagnostic Instrumentation
Added `verdict_counts`, `near_dup_intercepts`, `gate_downgrades`, `confidence_histogram` to `ConsolidationStats` (`consolidation.py`); wired through `engine.session_end()` into both `locomo_eval.py` and `stalememory_eval.py` summary JSON (per-conversation/per-scenario, aggregated at the run level — StaleMemory further split by `stale`/`detected` outcome).

**B1 baseline (LoCoMo limit=3 + StaleMemory limit=15/attribute, 13,572 prototypes):**

| Metric | Value |
|--------|-------|
| `contradicts` verdict | 0 / 13,572 |
| `reinforces` verdict | 0 / 13,572 |
| Confidence (mean / median) | 0.981 / 0.988 — compressed near ceiling |
| Near-dup intercept rate | ~49% |

### Phase 5-6: Ablation Matrix + Parameter Tuning Decision
Exposed `near_dup_guard_cosine`/`related_schema_cosine` as `GeometricJudgeConfig` fields (were hardcoded), threaded through `SlowaveConfig.judge` → `engine.py` → a general `--judge-overrides` JSON CLI flag on both eval scripts. Ran the full **B1–B8** threshold ablation matrix (see Ablation Results below). **Grid search skipped** — no ablation cleared this project's own 1pp gate (`CORE_DOC_TEMPLATE.md` Phase 5: "if ALL flags show ~0pp → document, skip Phases 6–7").

### Phase 7: Micro-Benchmark Tests (MANDATORY)
7 new tests across 3 files, all passing, 0% overlap with existing coverage (existing "contradiction" tests all mocked `judge.judge()` directly, never exercising the real facet-axis comparison):
- `test_near_dup_guard_inactive_gap.py` (2 tests) — proves the near-dup guard's active-status gap lets genuine `reinforces`/`contradicts` verdicts through when the closest-by-cosine schema is already inactive
- `test_contradicts_verdict_unreachable.py` (2 tests) — proves (pre-fix) that `contradicts` was provably unreachable via the real judge, regardless of the new schema's facet-axis divergence
- `test_facet_axis_persistence.py` (3 tests) — proves the fix: round-tripping facet data through `SchemaStore`, and `contradicts` becoming reachable end-to-end with real, divergent facet data

## Root Causes Found (in the order discovered — includes two self-corrections)

### 1. Priority Finding: near-dup guard silently absorbing contradicting updates — REFUTED
Original concern: the near-dup guard (cosine ≥ 0.92, runs before the judge) could intercept a genuinely contradicting update and silently reinforce the stale claim instead. Tested directly via B2 ablation (guard disabled, cosine→1.01) on the same StaleMemory scope as B1: `near_dup_intercepts` 6,421→0, `reinforces` unlocked 0→859 — but `contradicts` stayed at exactly 0, and detection/stale rates didn't move outside noise. **The guard was never the bottleneck.**

### 2. Two self-corrections while cross-checking against real production data
User pushback ("verify on diverse data before concluding") led to checking `~/.slowave/backups/` (real dogfood usage). First correction: claimed `reinforces`/`contradicts` were "provably unreachable" — wrong; real data showed 78 `reinforces` + 2 `supersedes` relations. Second correction: those 2 `supersedes` rows turned out to belong to a *different* subsystem (`engine.remember()`'s SVD1 supersession manifold, Module 10) — both schemas involved were `explicit_remember`-sourced, which this module's judge never even sees (Phase 1 gate skips them). Net: `reinforces` is real (mechanism confirmed below); `contradicts` still had zero confirmed real-world observations at this point.

### 3. Root cause of `contradicts=0`: facet-axis persistence gap — FOUND AND FIXED
Not a calibration issue. `Consolidator._write_latent_schema` reconstructed the *old* schema's facet axes as an unconditional `np.zeros((0, dim))` placeholder on every call, because raw facet axes were never persisted anywhere retrievable (only bound lossily into a VSA hypervector). `GeometricContradictionJudge`'s facet-distance branch only activates if both sides are non-empty — so `facet_distance` was always exactly `0.0`, making `contradicts` provably unreachable regardless of the new schema's real divergence.

**Fix:** `schemas` table gained `facet_axes`/`facet_strengths`/`n_facet_axes` columns (with a legacy-DB migration path); `SchemaStore.create()` persists them; `_write_latent_schema` now builds `old_view` from the real, persisted data. Verified against a real 385-schema legacy backup DB — migration clean, zero regressions, 394 unit tests pass.

**Measured impact** (identical scope, only the fix changed): LoCoMo `contradicts` 0→79 (18% of prototypes), hit rate **80.3%→81.3% (+1.0pp)**. StaleMemory `contradicts` 0→41 (0.3%), but detection/stale/no-answer **exactly unchanged**.

### 4. Why StaleMemory showed zero behavioral impact — three-layer investigation
- **Ruled out:** "hitting background schemas, not the target attribute" (the original guess) — never directly confirmed and superseded by the findings below.
- **Real bug #1, fixed:** `_value_present` used plain substring matching — `"cli" in "right-click"` → `True`. For the `tool_preference` attribute's `gui`→`cli` pairs (63 scenarios, the whole dataset), the literal word "cli" never appears in any conversation — post-drift CLI usage is only implied via commands. Every `detected=True` for this pair was a false positive. **Fix:** word-boundary regex matching. **Measured impact:** `tool_preference` detection crashed 84.4%→37.8% — confirming the bug inflated numbers by roughly half for that attribute.
- **Hypothesis tested and refuted:** "episodes mask consolidation's effect" (episodes are immutable, schemas aren't). Added a parallel schema-only scoring lens — combined and schema-only give **identical classifications on all 360 scenarios**. Episodes are redundant with schema content here, not a distinct confound.
- **The terminal explanation — architectural, not a bug:** `GeometricJudgeConfig`'s thresholds are inputs to `Consolidator`'s internal schema-linking logic only. They are never read by `eng.recall()`'s ranking (query-cosine + salience — a disjoint config namespace, confirmed by inspecting `RetrievalConfig`). Re-ran the full B1–B8 matrix with the fixed scorer: **B4/B6/B7/B8 show 0/360 classification diffs** — confirms the disconnect cleanly, even for 41 real, mechanically-confirmed contradictions (B6). **B2 (near-dup guard) is the one exception** — 2-3/360 diffs, because unlike the judge-verdict thresholds (which always create a new schema regardless of verdict), the guard's action calls `reinforce_schema()` on the *existing* schema without ever touching `content_text` — a small, direct, mechanistically-distinct channel to retrievable content.

## Ablation Matrix Results (B1–B8, `plans/05-consolidation.md`)

| # | Threshold | Benchmark | Mechanical effect | Task metric effect |
|---|-----------|-----------|-------------------|---------------------|
| B1 | baseline | LoCoMo+StaleMemory | — | baseline |
| B2 | `near_dup_guard_cosine=1.01` | StaleMemory | `reinforces` 0→859-866, `contradicts` +20 | **refuted** at aggregate (B1 vs B2); small real effect post-scorer-fix (2-3/360 scenarios) |
| B3 | `related_schema_cosine=1.01` | LoCoMo | schemas_created 217→399 | **−0.6pp** (worse) |
| B4 | `same_topic_cosine=0.99` | StaleMemory | refines→0, unrelated 152→3052 | 0/360 diffs, both scorers |
| B5 | `reinforce_cosine=1.01` | LoCoMo | byte-identical diagnostics to baseline | ~0 (mechanically dead already) |
| B6 | `contradicts_facet_dist=0.99` | StaleMemory | contradicts 41→0 | 0/360 diffs, both scorers |
| B7 | `min_support_to_supersede=1` | StaleMemory | contradicts 41→42 (noise) | 0/360 diffs, both scorers |
| B8 | `min_time_delta_to_supersede_s=1` | StaleMemory | contradicts 41→41 (no change) | 0/360 diffs, both scorers |

## Files Changed

| File | Change |
|------|--------|
| `core/05-consolidation.md` | Full rewrite (110→410 lines); Phase 4 Step 3 + Known Failure Modes corrected for the facet-axis fix |
| `plans/05-consolidation.md` | New plan document; updated with B1-B8 results and grid-search decision |
| `slowave/core/consolidation.py` | `ConsolidationStats` diagnostics; `near_dup_guard_cosine`/`related_schema_cosine` read from config; `old_view` built from real facet data |
| `slowave/latent/schema.py` | `GeometricJudgeConfig` gained `near_dup_guard_cosine`, `related_schema_cosine` |
| `slowave/core/config.py` | `SlowaveConfig.judge: GeometricJudgeConfig` |
| `slowave/core/engine.py` | `GeometricContradictionJudge(self.cfg.judge)`; `session_end()` returns full diagnostics |
| `slowave/utils/vec.py` | `pack_f32_matrix`/`unpack_f32_matrix` |
| `slowave/storage/schema.sql` | `schemas.facet_axes`/`.facet_strengths`/`.n_facet_axes` columns |
| `slowave/storage/sqlite_db.py` | Legacy-DB migration entries for the 3 new columns |
| `slowave/symbolic/schema_store.py` | `Schema.facet_axes`/`.facet_strengths`; persisted in `create()`, unpacked in `_row_to_schema()` |
| `tests/unit/test_near_dup_guard_inactive_gap.py` | New: 2 tests |
| `tests/unit/test_contradicts_verdict_unreachable.py` | New: 2 tests |
| `tests/unit/test_facet_axis_persistence.py` | New: 3 tests |
| `tests/integration/locomo_eval.py` | Consolidation diagnostics aggregation; `--judge-overrides` flag |
| `tests/integration/stalememory_eval.py` | Consolidation diagnostics aggregation; `--judge-overrides` flag; `_word_present` word-boundary fix; schema-only scoring lens |
| `outcomes/05-consolidation.md` | This file |

## Benchmark Impact

| Benchmark | Metric | Before (facet-axis fix) | After | Δ |
|-----------|--------|--------------------------|-------|---|
| LoCoMo (limit=3, 447 prototypes) | hit rate | 80.3% | 81.3% | **+1.0pp** |
| StaleMemory (limit=15/attribute, buggy scorer) | detection/stale/no-answer | 44.17%/35.83%/20.0% | unchanged across every ablation | 0pp (architectural, not the fix's fault) |
| StaleMemory (fixed scorer) | detection/stale/no-answer | 36.11%/35.56%/28.33% | unchanged across B4/B6/B7/B8; small (2-3/360) shift on B2 only | ~0pp except near-dup guard |
| StaleMemory `tool_preference` (fixed scorer) | detection rate | 84.4% | 37.8% | **−46.6pp** (bug fix, more honest number) |

**No regressions** — 394 unit tests pass throughout every change; migration verified against a real 385-schema legacy DB.

## Open Items (explicitly deferred, not silently dropped)

- `test_verdict_distribution_bounds` (plan's Phase 7 gap-fill spec) not written as a standalone test — low remaining value, largely covered by `test_facet_axis_persistence.py`'s reachability test
- A schema-status-aware StaleMemory metric (checking `schema.status == "active"` directly against the DB instead of keyword-matching retrieved text) would be the correct way to measure consolidation's effect on this benchmark, if that's ever wanted — not implemented
- `same_topic_cosine`/`variance_floor` grid searches from the plan remain unswept — deprioritized after the architectural-disconnect finding made clear that sweeping consolidation-internal thresholds won't move this particular benchmark's task metric

## Next Module

**Module 5: Temporal.** Key question: does `TemporalProbe` actually fire? What fraction of queries get temporal anchors vs. fallback to `now()`?
