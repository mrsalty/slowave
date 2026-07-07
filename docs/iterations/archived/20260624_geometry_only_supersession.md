# Geometry-Only Supersession: Remove P1/P2, Unify Decision Tree

**Date:** 2026-06-24  
**Branch:** `fix/supersession-direction-generalize`  
**Status:** Implemented — 331 tests passing

---

## 1. Problem

The `remember()` path had four sequential supersession layers (P1–P4) that accumulated organically over multiple iterations. Two of them violated the project's north star:

**P1 — Regex pattern matching (removed)**
- English-only: `"now uses"`, `"switched from X to Y"`, `"no longer uses"`, etc.
- For Italian, French, German content: zero coverage, despite `paraphrase-multilingual-MiniLM-L12-v2` supporting 50+ languages.
- Supersession mean cosine ≈ 0.68 (below P1's cosine threshold) — P1 was covering only a small, linguistically-biased subset anyway.
- Directly contradicts the north star: memory is geometry, language is never a memory operator.

**P2 — Cosine → needs_review fallback (removed)**
- Flagged `needs_review` for cosine ≥ 0.50 with no semantic signal — pure topical proximity.
- Zero test coverage; never validated.
- Easily triggered false reviews for unrelated same-domain facts (unrelated zone median cosine = 0.682).

**P3 + P4 — Separate loops (unified)**
- Two independent loops, two `_get_manifold()` calls, two `search_embedding()` passes.
- Shared logic (get candidate, fetch embedding, compute dir_score) duplicated across both.

---

## 2. Empirical Basis for Thresholds

Calibration from the 186-pair geometry eval set (`tests/unit/test_supersession_geometry.py`):

```
zone            n    min    p10    p25    med    p75    p90    max
supersession   71  0.218  0.501  0.529  0.694  0.800  0.904  0.981
additive       17  0.100  0.176  0.249  0.295  0.432  0.582  0.902
duplicate       6  0.822  0.850  0.895  0.952  0.973  0.981  0.984
unrelated      10 -0.014  0.059  0.292  0.682  0.883  0.944  0.948
```

**Key insight**: the cosine thresholds are *triage gates*, not supersession detectors.

- At cos ≥ 0.85: catches 21% of supersession pairs. The other 79% are handled by the consolidation path (`GeometricContradictionJudge`), which runs on every replay pass.
- The `unrelated` zone reaching 0.944 is the binding constraint against lowering thresholds: same-domain unrelated facts can accidentally be very close in cosine space.
- `direction_score` from the SVD1 manifold does the real discrimination once candidates are admitted.

**Threshold values (all in `supersession_manifold.py`):**

| Constant | Value | Rationale |
|---|---|---|
| `DIRECTION_THRESHOLD` | 0.10 | sep(sup,add)=+0.35 at this value; mean(add)=−0.028 |
| `DIR_REVIEW_BAND` | 0.05 | Lower bound of ambiguous zone → needs_review |
| `SAME_SCOPE_COS_THRESHOLD` | 0.85 | Duplicate-zone floor (min=0.822 rounded down) |
| `CROSS_SCOPE_COS_THRESHOLD` | 0.78 | Empirical: cos(Karpathy framing variants)=0.81, −3pp buffer |

---

## 3. New Decision Tree

Single pass, all scopes, language-agnostic:

```
cosine(new, candidate) >= CROSS_SCOPE_COS_THRESHOLD (0.78)?
  same scope AND cosine >= SAME_SCOPE_COS_THRESHOLD (0.85)?
    dir_score >= DIRECTION_THRESHOLD (0.10)
      → SUPERSEDE (value substitution)
    dir_score in [DIR_REVIEW_BAND (0.05), 0.10)
      → NEEDS_REVIEW (ambiguous, flag only)
    dir_score < DIR_REVIEW_BAND (0.05)
      → REINFORCE existing (restatement/paraphrase)
  different scope AND cosine >= 0.78?
    dir_score < DIRECTION_THRESHOLD
      → CROSS-SCOPE REINFORCE + record schema_evidence
        (breaks generalization bootstrap deadlock)
    dir_score >= DIRECTION_THRESHOLD
      → skip (cross-scope value divergence is valid)
```

---

## 4. Files Changed

| File | Change |
|---|---|
| `slowave/core/supersession_manifold.py` | Added `DIR_REVIEW_BAND`, `SAME_SCOPE_COS_THRESHOLD`, `CROSS_SCOPE_COS_THRESHOLD` with calibration comments and distribution table |
| `slowave/core/engine.py` | Removed `supersession.py` imports; replaced P1+P2+P3+P4 with single unified geometry pass |
| `slowave/core/supersession.py` | **Deleted** (dead code after P1 removal) |
| `tests/eval/test_synthetic_long_session.py` | Removed `TestSupersession` class (tested P1 patterns; now replaced by geometry tests) |
| `tests/unit/test_geometry_supersession.py` | **New**: 12 unit tests covering same-scope supersede/reinforce/review, cross-scope reinforce/skip/no-action, and threshold constant ordering |

---

## 5. Test Strategy

The new tests use **controlled embeddings** (`_ControlledEncoder`) and a **mocked manifold** (`_MockManifold`) so they:
- Run without a real encoder (no `requires_model` mark, no model download)
- Exercise the decision logic deterministically
- Are fast (0.16s for all 12 tests)

The `_make_pair(cos_target)` helper constructs two unit vectors with exact cosine = cos_target, giving full control over the admission gate. The mock manifold returns a fixed `direction_score`, allowing independent testing of each branch.

Real-encoder integration testing of value substitution detection (e.g., "SQLite→DuckDB" via `paraphrase-multilingual-MiniLM-L12-v2` + the actual SVD1 axis) is covered by the supersession geometry test (`test_supersession_geometry.py`, marked skip — intended for investigation runs, not CI).

---

## 6. Known Limitation

`CROSS_SCOPE_COS_THRESHOLD` (0.78) is motivated by one empirical observation. A proper calibration would need a cross-scope pair dataset: (same concept, different framing) vs. (different concepts, same domain). The threshold is conservative enough that `direction_score` catches any false admissions, but the value itself should be revisited once cross-scope ground truth data is available.
