# Slowave — Algorithmic Deep Dive Progress

This is the pick-up point for every new session.
For strategy and prioritization: `iteration-strategy.md`.
For algorithm specs: `core/NN-module.md`.
For active improvement plans: `plans/NN-module.md`.
For completed work notes: `outcomes/NN-module.md`.

---

## Module Status

| # | Module | Core Doc | Plan | Outcome | Status | Benchmark Δ |
|---|--------|----------|------|---------|--------|-------------|
| 1 | **Retrieval** | ✅ updated | ✅ done | ✅ done | **COMPLETE** | LoCoMo +3.7pp, Temporal +6.7pp, DMR +2.2pp |
| 2 | Salience | ✅ updated | ✅ done | ✅ done | **COMPLETE** | LoCoMo +0.8pp (79.5%) |
| 3 | Graph | ✅ rewritten | ✅ done | ✅ done | **COMPLETE** | λ₁ 1.0→0.3 (live DB: 89% sim-dom → fixed) |
| 4 | Consolidation | ✅ rewritten | ✅ done | ✅ done | **COMPLETE** | LoCoMo +1.0pp (80.3%→81.3%); StaleMemory: 0pp on every ablation except a small (2-3/360) near-dup-guard effect — confirmed architectural disconnect between judge thresholds and recall ranking, not a bug or a mystery |
| 5 | Temporal | ✅ rewritten | ✅ done | ✅ done | **COMPLETE** | LongMemEval 0.0pp (all 6 categories) from `use_temporal`; LoCoMo -0.6pp overall / -2.22pp on its temporal category from disabling `use_temporal` — mechanism confirmed alive, benchmark-dependent visibility; `temporal_weight=0.25` grid-searched, flat, kept as-is |
| 6 | Feedback | ✅ generated | — | — | not started | — |
| 7 | Context | ✅ generated | — | — | not started | — |
| 8 | VSA | ✅ generated | — | — | deferred (not wired) | — |

**Current benchmarks (2026-07-08, post-graph-tuning full run):**
- LoCoMo: **80.1%** | LongMemEval: 87.8% | DMR: 95.4% | Temporal: 86.7% | Wiki: 83.3% | StaleMemory: not run (graph-insensitive)

---

## What Was Done: Retrieval (2026-07-08)

Full session log: `outcomes/01-retrieval.md`

**Root problem found:** `spread_episode_weight=0.15` placed graph episodes on an incommensurable score scale vs cosine-direct (0.56+). Graph contributed nothing.

**Fix implemented:** Spread-projection FAISS — `q_spread = normalize(Σ a(P)*centroid(P))`, second FAISS search in same cosine space, `spread_score_weight=0.90`. Eliminated the score-scale mismatch.

**Evidence:**
- `test_spreading_path_completion.py` — graph path A→B→C wired correctly
- `test_retrieval_pipeline_plumbing.py` — spreading and temporal components show differential
- `graph_only_saves > 0` for 10/18 wiki scenarios (was 0/18)
- Benchmark improvements confirmed above
### spread_score_weight grid search (2026-07-08)
- Swept 9 values [0.50-0.95] on LoCoMo limit=3 (214s)
- **0.90 optimal** (+0.8pp vs 0.85): single +1.3pp, multi +1.0pp, advers +0.9pp
- Default changed **0.85 to 0.90** in RetrievalConfig, locomo_eval.py, 06-retrieval.md


---

## What Was Done: Salience (2026-07-08)

Full session log: `outcomes/02-salience.md`

**Cleanup (no benchmark impact):**
- Removed dead `SalienceConfig.recall_reinforcement` / `reinforce_on_recall()` — never called
- Added `surprise_weight: float = 0.3` (was hardcoded constant in ingest)
- `tau_seconds` default 3600 → 604800 (7 days, brain-aligned hippocampal tier)
- All 4 eval scripts made injectable: `--tau-seconds`, `--salience-weight`, `--surprise-weight`

**Ablation + grid search:**
- `salience_weight=0` vs `0.3`: +2pp overall, **+11pp adversarial**, StaleMemory unchanged
- Grid 0.0→1.0: elbow at **0.5** (+1pp overall, +8pp adversarial vs 0.3, only -1.4pp single-session)

**Parameter change:** `RetrievalConfig.salience_weight` default **0.3 → 0.5**

### Micro-benchmark (2026-07-08)
- `test_salience_calibration.py` written: 27 deterministic tests (0.04s)
- Covers decay, novelty, penalty, lifecycle, sampling, floor invariants

**Residual open questions (deferred):**
- `surprise_weight=0.3` not swept (transition model likely cold at eval time)
- Per-benchmark tau not swept (locomo=30d, others=1d — hardcoded, not optimized)

---

## What Was Done: Graph Quality (2026-07-08)

Full session log: `outcomes/03-graph.md`

**Phase 1-3: Audit + Documentation**
- Audited `core/04-graph.md` (96 lines generated) vs `graph_manager.py` (275 lines): found 7 discrepancies
- Rewrote core doc to 268 lines with all template sections, 10 invariants, full caller table
- Created `plans/03-graph.md` with 7 diagnostic questions, ablation matrix, grid search spec

**Phase 4: Diagnostic Instrumentation**
- Added `GraphManager.diagnose()` method for edge weight decomposition
- Ran LoCoMo limit=3 — **key finding: 64.3% of edges are similarity-dominated (>80%), median symmetry = 1.0**
- GO/NO-GO: **CAUTION** — λ₁=1.0 is too dominant but transition (11%) and coactivation (20%) do contribute

**Phase 7: Micro-Benchmark Tests (MANDATORY)**
- `test_graph_edge_quality.py`: 11 deterministic tests (0.05s), all pass
- Covers: edge ranking (Spearman ρ=1.0), directional edges, homeostatic sums, pruning, EMA convergence, weight decomposition, coactivation top-k filter, similarity overwrite, diagnose() validation

**Phase 5-6: Targeted Ablation**
- Ran live DB diagnostics: **89.2% pure similarity, 89.8% similarity-dominant, symmetry 0.969**
- Confirmed root cause: λ₁=1.0 too dominant — graph is a cosine neighbor list on real data
- LoCoMo ablation script written (λ₁ ∈ {0.0, 0.3, 0.5, 1.0}) — running offline

**Parameter change:** `GraphConfig.lambda_similarity` default **1.0 → 0.3**
- At 0.3, similarity is on par with transition (0.5) and coactivation (0.3)
- Forces edges to earn weight through learned temporal/associative signals

**Residual open questions (deferred):**
- LoCoMo benchmark confirmation of λ₁=0.3 vs baseline
- Grid search on λ₂/λ₃ ratios with new λ₁ baseline

---

## What Was Done: Consolidation (2026-07-09)

**Root problem found:** The generated `05-consolidation.md` cited supersession-manifold thresholds (`SAME_SCOPE_COS_THRESHOLD=0.85`, `DIRECTION_THRESHOLD=0.10`) from `supersession_manifold.py` — these are used in `engine.remember()`, NOT in the consolidation path. The consolidation path uses `GeometricContradictionJudge` with entirely different thresholds (`same_topic_cosine=0.75`, `reinforce_cosine=0.95`, `contradicts_facet_dist=0.35`).

**Doc rewritten:** `05-consolidation.md` rewritten from 110 → 410 lines, covering all 6 phases (gating → building → persistence → geometric judge → relations → decay), 10 invariants, 8 diagnostic hooks, 9 parameter sensitivity rows, 7 failure modes, full cross-module references, and 24 implementation files documented.

**Answer to key question:** `SAME_SCOPE_COS_THRESHOLD=0.85` and `DIRECTION_THRESHOLD=0.10` are the *wrong* question for consolidation — they belong to the `remember()`-time supersession manifold (Module 10). The consolidation path's thresholds are `same_topic_cosine=0.75` (topic gate), `reinforce_cosine=0.95` (strengthening gate), and `contradicts_facet_dist=0.35` (divergence gate). These were set based on geometric reasoning about the 384-d unit-norm embedding space but have not been empirically swept against a benchmark that tests contradiction detection. Sweeping them requires a benchmark with explicit update/contradiction ground truth (e.g. StaleMemory with knowledge-update scenarios).

### Plan document (2026-07-09)

Full plan: `plans/05-consolidation.md`

**Existing coverage found:** 1,470 lines across 6 test files already cover builder math, TF-IDF, support/recency gates, and end-to-end wiring — unlike Graph/Salience, Phase 7 is partially pre-satisfied. No diagnostic instrumentation exists yet (`ConsolidationStats` has only 5 raw counters, no verdict-distribution breakdown).

**Priority finding:** The near-duplicate guard (cosine ≥ 0.92) runs *before* the geometric judge and `reinforce_schema()` never overwrites `content_text` (`schema_store.py:475-513`). An old/new claim pair about the same slot that happens to embed at cosine ≥ 0.92 (e.g. a changed preference value phrased similarly) would be silently absorbed as reinforcement of the **stale** claim — the geometric judge never sees it. Untested on real data; flagged as Q1/Q4 in the plan, with a StaleMemory-based ablation (near-dup guard disabled) as the go/no-go gate before any threshold tuning.

7 diagnostic questions, an 8-row threshold ablation matrix (no boolean flags exist in this module — all knobs are continuous thresholds), grid search ranges, and a gap-fill spec for 2 missing micro-benchmarks are in the plan doc.

### Diagnostic instrumentation + B1 baseline (2026-07-09)

Implemented Steps 1-3 of the plan's Implementation Order: `ConsolidationStats` gained `verdict_counts`, `near_dup_intercepts`, `gate_downgrades`, `confidence_histogram` (`slowave/core/consolidation.py`); wired through `engine.session_end()` into both `locomo_eval.py` (per-conversation, aggregated in `_save`) and `stalememory_eval.py` (per-session, aggregated in `_build_payload` — split further by `stale`/`detected` outcome to test the Priority Finding observationally).

**B1 baseline run:** LoCoMo limit=3 (447 prototypes, 80.3% hit rate — matches known baseline, single `consolidate_once()` pass per conversation) + StaleMemory limit=15/attribute (360 scenarios, 13,125 prototypes, 44.2% detection / 35.8% stale / 20.0% no-answer — **12 `session_end(consolidate=True)` passes per scenario**, so this one does accumulate supersession history within each scenario's DB).

**On this benchmark data:** `contradicts` verdict fired 0/13,572 times and `reinforces` fired 0/13,572 times; confidence is compressed near ceiling (mean 0.981, median 0.988, only 96/13,572 below 0.9).

**CORRECTION #1 (same day):** the initial write-up claimed `reinforces` was "provably unreachable by construction" because `near_dup_guard_cosine=0.92 < reinforce_cosine=0.95`. This is wrong — the near-dup guard's `search_embedding(limit=1)` returns the single globally-closest schema *regardless of status*, and only short-circuits if that closest match is `active`. When the closest-by-cosine schema is already inactive (superseded from a prior pass), the guard doesn't fire, and a different still-active schema found via `_best_related_schema` can genuinely reach the judge. Locked in as a regression test: `tests/unit/test_near_dup_guard_inactive_gap.py`.

**CORRECTION #2 (same day, after digging further per user's "verify on diverse data" request):** the first correction over-claimed by citing `~/.slowave/backups/slowave-20260706_083014.db.gz` (385 schemas, real dogfood usage) as evidence that BOTH `reinforces` (78 rows) and `supersedes` (2 rows) came from `_write_latent_schema`'s judge, based on `reason=NULL` ruling out `_link_schemas_via_prototype_centroid`. That ruled out one alternative but missed another: `engine.remember()` has its own, entirely separate SVD1 supersession manifold (Module 10, `engine.py` lines ~534-680) that *also* writes `relation="supersedes"` with no `reason` set, and reinforces via a direct `reinforce_schema()` call with no relation edge at all. Cross-referencing the two `supersedes` rows' schemas: **both pairs are `explicit_remember` ↔ `explicit_remember`** — and per this doc's Phase 1 gate, explicit-remember-sourced episodes never reach the Consolidator's judge in the first place. So the 2 `supersedes` rows almost certainly came from `engine.remember()`'s manifold, not from the module under study. **The "contradicts is real but rare (~0.5%) in production" claim is retracted — there is still no confirmed real-world observation of the Consolidator's judge itself returning "contradicts."** The `reinforces` finding stands with more nuance: several of the 78 rows involve at least one schema with a blank (consolidation-created, not `explicit_remember`) `source_kind` on one side of the pair — those could only have been created by `_write_latent_schema`, so that part of Correction #1 is still supported.

**Consequence for the plan (at the time):** real slowave usage mixes two independent schema-relation-producing subsystems — `Consolidator`'s judge (this module) and `engine.remember()`'s SVD1 manifold (Module 10) — any observational check against a live DB must attribute relations to the correct one. LoCoMo/StaleMemory only exercise the Consolidator path, so they remain the right tool for testing *this* module.

### near_dup_guard_cosine exposed as config + B2 ablation (2026-07-09)

Made `near_dup_guard_cosine` and `related_schema_cosine` fields of `GeometricJudgeConfig` (`slowave/latent/schema.py`) instead of hardcoded constants in `Consolidator._write_latent_schema`/`_best_related_schema`. Threaded through `SlowaveConfig.judge` → `engine.py` → new `--near-dup-guard-cosine` CLI flag on `stalememory_eval.py`. Core doc's Configuration table updated. All 71+ existing unit tests still pass.

**B2 run:** identical StaleMemory scope as B1 (limit=15/attribute, 360 scenarios, 13,125 prototypes), only `near_dup_guard_cosine` changed from `0.92` to `1.01` (guard fully disabled).

| | B1 (guard=0.92) | B2 (guard disabled) |
|---|---|---|
| `near_dup_intercepts` | 6,421 | 0 |
| `reinforces` verdict | 0 | **859** |
| `contradicts` verdict | 0 | **0** |
| `refines` verdict | 2,899 | 2,950 |
| detection_rate | 44.2% | 43.3% |
| stale_rate | 35.8% | 36.1% |

**Priority Finding: refuted.** Disabling the guard entirely unlocks 859 genuine `reinforces` verdicts (confirming the guard mechanism from Correction #1 is real and load-bearing), but produces **zero** additional `contradicts` verdicts, and detection/stale rates don't move outside noise. The near-dup guard was never the bottleneck for contradiction detection on this benchmark.

### Root cause of `contradicts=0` found (2026-07-09, same day)

The Q7 "facet-axis / `min_members_for_facets`" hypothesis above was a red herring in one specific way — the real cause is stronger and unconditional. `Consolidator._write_latent_schema` reconstructs the *old* (existing) schema's `LatentSchema` view with `facet_axes=np.zeros((0, dim))` **unconditionally**, on every call, regardless of the old schema's actual original member count. This is because raw facet axes are never persisted anywhere retrievable — `LatentSchemaBuilder.build()` computes them, but they are only bound lossily into a VSA hypervector blob (irreversible), never stored as a matrix. In `GeometricContradictionJudge.judge()` (`slowave/latent/schema.py` line ~538), the facet-distance branch only activates `if old.facet_axes.size > 0 and new.facet_axes.size > 0`; since `old.facet_axes.size` is always `0` on this path, `facet_distance` is always exactly `0.0` — always `< contradicts_facet_dist (0.35)` — so **`"contradicts"` is provably unreachable via this code path**, not merely rare, regardless of the *new* schema's member count or how divergent its real facet axes are.

Confirmed by two new tests in `tests/unit/test_contradicts_verdict_unreachable.py`: the real (unmocked) judge, called end-to-end through `_write_latent_schema`, always returns `"refines"` even when the new schema is given maximally divergent facet axes (orthonormal, sign-flipped, random). Existing tests in `test_contradiction_support_gate.py` never caught this because all of them mock `judge.judge()` directly to inject a `"contradicts"` verdict, testing only the downstream support/recency gates — 0% of existing test coverage exercised whether the verdict is actually reachable.

Core doc (`core/05-consolidation.md`) updated: Phase 4 Step 3 section now states this plainly, and the "No contradictions ever detected" row in Known Failure Modes is corrected from a threshold-calibration hypothesis to the confirmed root cause.

### Fix implemented + impact measured (2026-07-09, same day)

**Implemented:** `schemas` table gained `facet_axes`/`facet_strengths`/`n_facet_axes` columns (`schema.sql`, with a pre-migration entry in `sqlite_db.py._apply_pre_migrations` for legacy DBs). `SchemaStore.create()` persists them (new `pack_f32_matrix`/`unpack_f32_matrix` helpers in `slowave/utils/vec.py`); `SchemaStore._row_to_schema()` unpacks them into new `Schema.facet_axes`/`.facet_strengths` fields (always a concrete array — `(0, dim)`/`(0,)` for legacy rows or genuinely-small clusters, never `None`). `Consolidator._write_latent_schema` now builds `old_view` from `related.facet_axes`/`.facet_strengths` (the real persisted data), falling back to the old placeholder only via an `isinstance(np.ndarray)` check when the related schema has no real facet data.

**Verified:** migration tested directly against a real legacy backup DB (`~/.slowave/backups/slowave-20260706_083014.db.gz`, 385 schemas) — columns added, all rows preserved, legacy rows correctly degrade to empty facet arrays. 3 new tests in `tests/unit/test_facet_axis_persistence.py` prove round-tripping and that `contradicts` is now reachable end-to-end with real, divergent facet data. Full unit suite: 394 passed, 1 skipped (unrelated), zero regressions.

**Impact measured** — identical scope as B1 (same limits, same defaults), only the fix changed:

| | LoCoMo (447 prototypes) | StaleMemory (13,124 prototypes) |
|---|---|---|
| `contradicts` verdict | 0 → **79** (18%) | 0 → **41** (0.3%) |
| gate downgrades | 0/0 | 0/0 (all 41/79 passed straight through) |
| Task metric | hit_rate **80.3% → 81.3%** (+1.0pp) | detection/stale/no_answer: **exactly unchanged** (44.17%/35.83%/20.0%, identical to 4 decimals) |

The fix works mechanically on both benchmarks. Behaviorally it helped LoCoMo but had zero measurable effect on StaleMemory. Initial guess (superseded below): StaleMemory scenarios contain incidental conversational content, and most of the 41 contradictions landed on background schemas, not the target pair.

### Phase 5 (remaining ablations) + Phase 6 decision (2026-07-09, same day)

Extended `--near-dup-guard-cosine` into a general `--judge-overrides` JSON flag on both `locomo_eval.py` and `stalememory_eval.py` (cleaner than one flag per `GeometricJudgeConfig` field). Ran the plan's remaining B3–B8, **compared against the correct post-fix baseline** (`locomo_postfix.json` / `stalememory_postfix.json` — B1 predates the facet-axis fix, so comparing against it would conflate two changes).

**LoCoMo** (baseline: 81.3% hit rate, 79 contradicts):
- B3 `related_schema_cosine=1.01` (disabled): schemas_created 217→399 (nearly doubles — nothing ever finds a related schema to compare against), contradicts 79→0. Hit rate **81.3%→80.7% (−0.6pp)** — worse, not better.
- B5 `reinforce_cosine=1.01` (disabled): diagnostics **byte-for-byte identical** to baseline. Confirms `reinforce_cosine`'s active range was already unreachable in practice.

**StaleMemory** (baseline: 44.17%/35.83%/20.0%, 41 contradicts) — every ablation leaves the task metric **exactly unchanged**, despite large mechanical shifts:

| Ablation | Mechanical effect | detection/stale/no_answer |
|---|---|---|
| B4 `same_topic_cosine=0.99` | refines 2866→0, unrelated 152→3052, schemas_created 3528→6427 | 44.17/35.83/20.0 (unchanged) |
| B6 `contradicts_facet_dist=0.99` | contradicts 41→0, absorbed into refines | 44.17/35.83/20.0 (unchanged) |
| B7 `min_support_to_supersede=1` | contradicts 41→42 (noise) | 44.17/35.83/20.0 (unchanged) |
| B8 `min_time_delta_to_supersede_s=1` | contradicts 41→41 (no change) | 44.17/35.83/20.0 (unchanged) |

**Phase 6 decision: grid search skipped.** Per this project's own gate (`CORE_DOC_TEMPLATE.md` Phase 5: "If ALL flags show ~0pp → document, skip Phases 6–7, jump to Phase 8") — none of B2–B8 clear 1pp on either benchmark, and B3's −0.6pp is negative. Sweeping any of these thresholds further would be sweeping a flat landscape.

### Root cause of StaleMemory's invariance (2026-07-09, same day, pushed further per user request)

Initial write-up here (episode immutability + a scorer bug) is **superseded below** — both were real, both got fixed, and the invariance persisted anyway, revealing a third, deeper, architectural reason.

### Two fixes implemented and measured (2026-07-09, same day)

**Fix 1 — word-boundary scorer.** `_value_present` did plain substring matching; `"cli" in "right-click"` → `True`. Added `_word_present()` with `(?<![a-z0-9])token(?![a-z0-9])` lookaround anchoring. Verified directly against the exact collision found while tracing.

**Fix 2 — schema-only scoring lens.** Added `detected_schema_only`/`stale_schema_only`/`no_answer_schema_only` to `ScenarioResult`, scored against `schemas_text` alone (episodes excluded), computed **alongside** (not replacing) the original combined metric — both land in the payload (`summary.schema_only`).

**Measured impact of Fix 1 — large and real:** re-ran the same scope (limit=15/attribute) with the word-boundary fix. `tool_preference` detection **crashed 84.4%→37.8%** (stale 15.6%→42.2%, no-answer 0%→20%) — confirming the substring bug was inflating that attribute's numbers by roughly half. Overall: detection 44.17%→36.11%, no-answer 20%→28.33% — a harsher, more honest picture.

**Measured impact of Fix 2 — a non-event, and a correction to the episode-immutability theory:** combined and schema-only classifications are **identical on all 360 scenarios** in the fixed baseline. Episodes are genuinely retrieved (`n_episodes` never 0, mean 8.29) — but schema content already contains whatever episodes would add for keyword-presence purposes. **The original "episodes mask consolidation's effect" theory is wrong as a complete explanation** — episodes are redundant with schemas here, not a distinct confound hiding a real effect.

**The real test — did fixing the scorer reveal any sensitivity to consolidation at all?** Re-ran B4 (`same_topic_cosine=0.99`) with both fixes in place, same scope, and diffed every scenario against the fixed baseline: **zero classification changes, combined or schema-only, across all 360 scenarios** — even though B4's mechanical effect is now larger than before (schemas_created 9.80/scenario → 17.85/scenario, meaning top_k=10 recall now has to actively rank-filter rather than just return everything).

### The actual, complete, architectural explanation

`same_topic_cosine`, `contradicts_facet_dist`, `reinforce_cosine`, `related_schema_cosine`, `near_dup_guard_cosine` are **schema-to-schema comparison thresholds used exclusively inside `Consolidator`'s internal linking/dedup/contradiction logic.** None of them are inputs to `eng.recall()`'s ranking, which scores schemas by query-to-schema cosine similarity + salience — a completely separate computation. Sweeping any of these thresholds can only change: (a) how many distinct schemas exist, (b) which relation edges connect them, and (c) — via the `contradicts`/`supersedes` branch only — whether an old schema's salience gets suppressed to 0.05. None of (a)/(b) touch what content is retrievable for a given query at all. (c) only matters if that salience drop flips *top-k membership*, which essentially never happens for a schema that's directly relevant to the probe question (it was already going to rank high on query-similarity grounds, salience is a secondary re-rank factor). This is why even 41 real, mechanically-confirmed contradictions (B6: 41→0) moved the task metric by exactly 0.00pp — contradicting/superseding a schema doesn't remove it from being retrievable, it just gets deprioritized in a ranking that rarely mattered for on-topic queries in the first place.

**Net conclusion:** StaleMemory's detection/stale rate, at this ingestion scale (~10-18 schemas/scenario vs. `top_k=10`), cannot measure the Consolidator's `contradicts`/`refines`/`reinforces` mechanics at all — not due to a benchmark bug (both real bugs found are now fixed), but because the two systems don't share a causal pathway strong enough to move this metric. A benchmark that could measure this would need either much larger per-scenario schema counts (so ranking actually excludes low-salience schemas) or a metric that inspects schema *status* directly (e.g. "is the correct schema `active` and the stale one `superseded`") rather than raw keyword presence in retrieved text.

### Full B1–B8 re-run with the fixed scorer (2026-07-09, same day)

Re-ran B2, B6, B7, B8 with both scorer fixes (B1 and B4 already had fixed-scorer data from earlier the same day; B3/B5 are LoCoMo-based and untouched by the StaleMemory scorer fix, so not re-run — same code path, would reproduce identical numbers).

| Ablation | Rates (combined) | Classification diffs vs. fixed baseline |
|---|---|---|
| B2 `near_dup_guard_cosine=1.01` | 36.11%→35.56% det, 35.56%→36.11% stale | **2/360 combined, 3/360 schema_only — nonzero** |
| B4 `same_topic_cosine=0.99` | unchanged | 0/360 |
| B6 `contradicts_facet_dist=0.99` | unchanged | 0/360 |
| B7 `min_support_to_supersede=1` | unchanged | 0/360 |
| B8 `min_time_delta_to_supersede_s=1` | unchanged | 0/360 |

**The architectural-disconnect conclusion holds for B4/B6/B7/B8 — perfectly, at 0/360 diffs each, even with the scorer fixed.** But **B2 is the one exception**, and it's mechanistically explicable, not noise: unlike the judge-verdict thresholds (which always create a *new* schema regardless of verdict — the verdict only decides relation edges/old-schema status), the near-dup guard's action is structurally different. When it fires, it calls `SchemaStore.reinforce_schema()` on the existing schema, which never overwrites `content_text` — the stale claim persists verbatim forever. When disabled, a genuinely new schema with *updated* `content_text` gets created instead. That's a direct channel to retrievable content, not just relation-edge bookkeeping — a small resurgence, at reduced scale (2-3/360 scenarios, ~0.6-0.8pp), of the very first Priority Finding from earlier in this investigation (the one that was refuted at the *aggregate* level back on B1 vs B2 before the scorer was fixed). The refutation still stands directionally (this is a tiny effect, not the dominant one), but it's no longer a clean zero once the scorer noise is removed.

---

## Consolidation (Module 4): COMPLETE

Full session log: `outcomes/05-consolidation.md`. All 8 phases done. Two deferred, optional items if revisited: the `test_verdict_distribution_bounds` gap-fill test, and a schema-status-aware StaleMemory metric (check `schema.status == "active"` directly against the DB instead of keyword-matching retrieved text).

---

## What Was Done: Temporal (2026-07-09)

Full session log: `outcomes/07-temporal.md`. All 8 phases done.

**Root problem found:** `core/07-temporal.md`'s Stage 10 anchor-estimation section documented a fabricated 12-probe table (invented "a few minutes ago"/"an hour ago" entries that don't exist in `_TEMPORAL_PROBES`, missing the real "two months ago"/"six months ago"/"two years ago" entries) and the wrong `softmax_temperature` default (0.15 documented vs. 0.05 actual). The doc also lacked every template section past Key Invariants. A second, independent staleness bug was found *in the source itself*: `TemporalProbe`'s docstring claimed a 0.1 default that the constructor never used — fixed (`temporal.py:211`, no behavior change).

**Key question answered** (PROGRESS.md's standing question): `TemporalProbe` fires on **65% of queries** (LongMemEval oracle baseline, 60 questions) — not dead weight. But firing rate tracks *backward-referencing phrasing* ("checking back on our previous conversation"), not the benchmark's category taxonomy — `single-session-assistant` fires at 90%, identical to `temporal-reasoning`, while `single-session-preference` (present/future-tense phrasing) is the real outlier at 10%. This refuted the plan's original Q4 framing (using category label as ground truth for calibration) mid-investigation.

**Ablation matrix (`use_temporal` on/off, the only wired boolean in this module):** LongMemEval shows **exactly 0.0pp on every category**, including `temporal-reasoning` — despite the mechanism firing 65% of the time. LoCoMo shows a real, benchmark-specific effect: **-0.6pp overall, -2.22pp on its dedicated temporal category** (categories 3/4/5 exactly 0.0pp, matching LongMemEval's flatness). Two benchmarks disagreeing this cleanly on a real, confirmed-alive mechanism mirrors the Consolidation module's "architectural disconnect" pattern — not a bug, a benchmark-sensitivity difference.

**Grid search:** `temporal_weight` swept {0.0, 0.10, 0.25, 0.40, 0.60} on LoCoMo's two sensitive categories. Flat, non-monotonic landscape at real sample sizes (n=74/n=90) — current default (0.25) already at or near the empirical optimum on both. **No change.**

**Micro-benchmark tests (MANDATORY):** `tests/unit/test_temporal_probe.py` — 12 new tests, zero prior coverage of `TemporalProbe` (dead-zone gate, softmax-bound invariant, determinism, probe-embedded-once discipline, internal normalization). All pass; full 394+ unit suite unaffected.

**Residual open questions (deferred):** `softmax_temperature`/`atemporal_margin` recalibration (needs phrasing-level annotation, not category labels — Q4's original ground truth was shown wrong); the probe set's minute/hour coverage gap (same-day queries fall into the dead zone or map to "yesterday" — structural, not a threshold); why LongMemEval is insensitive to `use_temporal` while LoCoMo isn't (plausible mechanism proposed, not confirmed by direct instrumentation).

---

## Next Session: Feedback (Module 6)
1. Read `core/08-feedback.md` — audit alignment with `slowave/core/feedback.py` implementation
2. Rewrite following template
