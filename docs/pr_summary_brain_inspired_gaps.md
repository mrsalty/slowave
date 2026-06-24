# PR: Geometry-Only Supersession + Brain-Inspired Gaps

**Branch:** `fix/brain-inspired-gaps` → `main`
**Commits:** 8 commits, +918 / −557 across 16 files

---

## What & Why

Two connected refactors that replace Slowave's English-only regex supersession (P1) with a language-agnostic geometry decision tree, then fix five brain-inspired architectural gaps identified in an end-to-end audit of the generalization/promotion pipeline.

---

## 1. Geometry-Only Supersession

**Problem:** Four sequential supersession layers (P1–P4) violated the north star — memory is geometry, language is never a memory operator.

- **P1** — 6 English-only regex patterns (`"now uses"`, `"switched from X to Y"`, etc.) — zero coverage for IT/FR/DE/ES content
- **P2** — Cosine `needs_review` at 0.50 had no semantic signal — false positives from same-domain unrelated facts
- **P3** — Auto-supersession at cos ≥ 0.85 ignored the `SupersessionManifold` SVD1 axis entirely (always superseded regardless of direction)
- **P4** — No cross-scope generalization bootstrap path existed (stage-0 schemas can never accumulate cross-scope recall events)

**Fix:** Single geometry decision tree, all scopes, language-agnostic:

```
cosine ≥ 0.78 (cross-scope) or 0.85 (same-scope)?
├── YES → direction_score from SupersessionManifold SVD1:
│   ├── ≥ 0.10 → value substitution → SUPERSEDE
│   ├── [0.05, 0.10) → ambiguous → NEEDS_REVIEW
│   └── < 0.05 → restatement → REINFORCE (same-scope) or
│                              REINFORCE + evidence (cross-scope)
└── NO → create new schema (no change)
```

- Deleted `slowave/core/supersession.py` (301 lines of regex dead code)
- Deleted `tests/eval/test_synthetic_long_session.py` TestSupersession class (tested P1 patterns)
- Added `tests/unit/test_geometry_supersession.py` — 12 deterministic unit tests using controlled embeddings + mock manifold
- Calibrated threshold constants in `supersession_manifold.py` with distribution table from 186-pair eval set
---

## 2. Gap 3 — Extended Supersession Range

**Problem:** The geometry tree only operated at cos ≥ 0.85, missing ~79% of supersession pairs in the 0.70–0.85 band (including WikiScenarios S-1/S-2 at cos ~0.80).

**Fix:** `EXTENDED_SAME_SCOPE_COS_THRESHOLD = 0.70` — direction-score-only supersession in [0.70, 0.85). No reinforce/review at this range because cosine alone is too weak — only clear value substitutions (dir_score ≥ 0.10) are superseded.

---

## 3. Gap 2 — Cross-Scope Generalization Bootstrap

**Problem:** Stage-0 schemas could never accumulate cross-scope recall events — you need stage 1 to be recalled cross-scope, but you need cross-scope recalls to reach stage 1. Deadlock.

**Fix (two paths):**

- **`remember()`-time (P4):** Cross-scope same-concept remembers add `schema_evidence` entries via `reinforce_schema(evidence=[...])`
- **Consolidation-time:** `increment_cross_scope_reinforcement()` called when a different-scope prototype reinforces an existing schema via `GeometricContradictionJudge`

`_update_utility_scores()` merges both sources via `UNION` to avoid double-counting when the same scope+session appears in both paths. Offline reinforcement carries half-weight (`cross_scope_reinforcement_count // 2`) toward generalization stage promotion.

---

## 4. Gap 4 — Context Query Pollution

**Problem:** `context_query` events were ingested as episodic text, polluting the corpus with verbatim user queries.

**Fix:** Filter `source="context_query"` in `ingest.py` before event storage.

---

## 5. Gap 5 — Near-Duplicate Suppression (MMR)

**Problem:** Near-duplicate schemas (cos ≥ 0.92) both surfaced in context/activate, wasting token budget.

**Fix:** Maximal Marginal Relevance dedup in `WorkingMemoryGate` at cos ≥ 0.92 — select the first, skip the rest.

---

## 6. Gap 6 Phase 1 — Schema Abstraction Measurement

**Problem:** Slowave promotes schemas but doesn't abstract them — no principled signal existed to measure whether schema text generalizes beyond specific instances.

**Fix:** `episode_embedding_variance` computed in `LatentSchemaBuilder` facets. Passive measurement only — no behavioral change yet. Creates the empirical foundation for Phase 2 (principle extraction via central-episode selection).

---

## 7. Other Changes

- **Dashboard:** Generalization tab clarity improvements
- **CLAUDE.md:** Karpathy coding guidelines
- **Benchmark docs:** Updated to match current oracle-split numbers
- **Wiki scenarios results:** Updated post-gaps

---

## Benchmark Impact

| Benchmark | Before | After | Verdict |
|---|---|---|---|
| LongMemEval | 87.8% | 87.8% | 🟢 flat — expected (knowledge-update was already handled by P1) |
| LoCoMo | 76.0% | 76.0% | 🟢 flat — no supersession dependency |
| DMR | ~93% | ~93% | 🟢 flat |
| StaleMemory | 45.1% | 45.1% | 🟡 flat — implicit drift requires retrieval-layer changes (separate work) |
| WikiScenarios S-1/S-2 | hit=True, v1_status="active" | same | 🟡 data hygiene unchanged — direction_score (0.082/−0.085) < 0.10 threshold |

**No regression, no gain on existing benchmarks — but the fixes target genuine architectural flaws that existing single-scope benchmarks cannot measure.** Cross-scope generalization, bootstrap deadlock breaking, and schema abstraction require new multi-scope benchmarks to validate.

---

## Files Changed (16 files, +918 / −557)

| File | Change |
|---|---|
| `slowave/core/engine.py` | Replace P1–P4 with single geometry decision tree; import new threshold constants |
| `slowave/core/supersession_manifold.py` | Add `DIR_REVIEW_BAND`, `SAME_SCOPE_COS_THRESHOLD`, `EXTENDED_SAME_SCOPE_COS_THRESHOLD`, `CROSS_SCOPE_COS_THRESHOLD` with calibration docs |
| `slowave/core/supersession.py` | **Deleted** (301 lines of regex dead code) |
| `slowave/symbolic/schema_store.py` | `increment_cross_scope_reinforcement()`, UNION-based cross-scope count merge, offline reinforcement weight |
| `slowave/core/consolidation.py` | Cross-scope reinforcement call in `GeometricContradictionJudge` path |
| `slowave/core/context.py` | MMR dedup in `WorkingMemoryGate` at cos ≥ 0.92 |
| `slowave/core/services/ingest.py` | Filter `context_query` events |
| `slowave/latent/schema.py` | Schema abstraction measurement scaffolding |
| `slowave/dashboard/app.py` | Generalization tab clarity |
| `tests/unit/test_geometry_supersession.py` | **New** — 12 deterministic supersession decision tree tests |
| `tests/eval/test_synthetic_long_session.py` | Remove `TestSupersession` class (covered by new geometry tests) |
| CLAUDE.md, README.md, `docs/benchmarks.md`, `docs/reproducibility.md` | Guidelines, doc updates |
| `results/wiki_scenarios_full.json` | Updated benchmark results |

---

## Testing

```bash
pytest tests/unit/test_geometry_supersession.py -v          # 12 new tests, 0.16s
pytest tests/unit -q                                        # 333+ passing
pytest tests/wiki_scenarios/run_wiki_scenarios.py           # 18 scenarios, 4 ablations
```