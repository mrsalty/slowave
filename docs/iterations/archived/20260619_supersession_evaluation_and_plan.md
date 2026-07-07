# Supersession: Evaluation, Results & Next-Step Plan

**Date:** 2026-06-19  
**Status:** In progress — explicit supersession improved; implicit drift unsolved  
**Context:** Full investigation cycle started from `20260618_encoder_supersession_geometry_investigation.md`  
**See also:** `20260619_supersession_geometry_domain_general.md` (geometry investigation log)

---

## 1. What Was Shipped This Session

### 1.1 Encoder switch
- **From:** `BAAI/bge-small-en-v1.5` (English-only, 384-dim)
- **To:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (50+ languages, 384-dim)
- Zero FAISS/SQLite migration cost (same dim)
- `ONNXTextEncoder` is now generic: Xenova repo derived from model name, token_type_ids zero-filled from ONNX required inputs

### 1.2 P2 geometric fallback (engine.py)
- Threshold: 0.90 → 0.50 (calibrated for mnlm cosine distribution: supersession mean ≈ 0.68, additive mean ≈ 0.36)
- Candidate limit: 5 → 10
- Skips schemas already handled by P1

### 1.3 SupersessionManifold (slowave/core/supersession_manifold.py)
- SVD1 direction axis from 21-pair multilingual seed set (7 domains)
- Lazy-computed on first use; invalidates on encoder change
- **Not wired into production P2** — investigation showed SVD1 is domain-local with a small fixed seed (numeric-scale pairs dominate axis; tool/person switches anti-align)
- Kept for future scope-adaptive use

### 1.4 Geometry investigation tooling
- `tests/unit/test_supersession_geometry.py`: 104-pair test set, 8 domains, 5 languages
- `tests/unit/_run_geometry_investigation.py`: direction centroid + domain cross-test
- `tests/unit/_run_svd_fisher_investigation.py`: SVD concentration + Fisher LDA LOO

---

## 2. Regression Benchmark Results

Baseline: June 17 2026 with `BAAI/bge-small-en-v1.5`

| Benchmark | Baseline | After mnlm | Delta | Verdict |
|---|---|---|---|---|
| WikiScenarios core | 15/15 (100%) | 15/15 (100%) | 0 | ✓ flat |
| LongMemEval | 88.0% | 87.8% | −0.2pp | ✓ within noise |
| StaleMemory | 45.8% | 45.1% | −0.7pp | ✓ within noise |
| DMR | 87.4% | 94.0%\* | +6.6pp | ✓ improved\* |
| LoCoMo | 80.36% | 77.2% | −3.2pp | ⚠ regression |

\*partial run (47/50)

**LoCoMo −3.2pp** is the only meaningful delta. LoCoMo is English conversational data — exactly where bge-small-en excels. The regression is the expected cost of switching from English-specialist to multilingual-generalist. Accepted for Slowave's multilingual mandate.

**LME by category (mnlm):**

| Category | Score |
|---|---|
| knowledge-update | 94.9% |
| single-session-user | 95.7% |
| single-session-assistant | 92.9% |
| temporal-reasoning | 88.0% |
| multi-session | 79.7% |
| single-session-preference | 76.7% |

`single-session-preference` (76.7%) is the weakest category and directly relevant to supersession quality.

---

## 3. Why StaleMemory Did Not Improve

StaleMemory was expected to improve because supersession detection was strengthened. It did not. The reason is architectural, not implementation.

### 3.1 What StaleMemory tests

1200 scenarios where a user preference changes **implicitly through behavior** across 10 sessions. The change is never stated explicitly after session 0. Example:

- Session 0: "user prefers JSON output format" (explicit, stored as schema)
- Sessions 1–10: user consistently requests CSV-formatted outputs (implicit behavioral drift)
- Query: "what format does the user prefer?"
- Expected: CSV. System returns: JSON → STALE

### 3.2 Why P1 and P2 both miss

- **P1 (regex)**: never fires — there is no "switched from X to Y" language in implicit drift sessions
- **P2 (cosine ≥ 0.50)**: never fires — "can you format this as CSV?" has cosine < 0.50 with "user prefers JSON output format" (they are semantically adjacent, not paraphrase-similar)
- The old schema stays active with full retrieval score. Even though `needs_review` would trigger score × 0.20, the flag is never set

### 3.3 The detection → action gap

Even when P2 fires (explicit change signals), it only sets `needs_review` (score × 0.20). P1 auto-supersedes (status = "superseded", salience = 0.05). For StaleMemory, the issue is not the suppression strength — it is that neither detection path fires at all for implicit drift.

### 3.4 StaleMemory by category

```
programming_language   HIT   (python→rust) — tech terms overlap in behavioral signals
naming_convention      HIT   (camelCase→snake_case) — same
output_format          STALE (json→csv) — format preference, no textual overlap
communication_style    STALE (detailed→moderate) — style preference, abstract
error_handling         STALE (defensive→permissive) — style preference, abstract
explanation_approach   STALE (code_first→text_first) — style preference, abstract
```

The working categories succeed because behavioral signals (code with Rust, snake_case identifiers) semantically overlap with the preference schema text. The failing categories are abstract style preferences with no lexical overlap between behavior and preference.

---

## 4. Root Cause Analysis

**Two distinct supersession problems:**

| Problem type | Signal available | Current handling | StaleMemory? |
|---|---|---|---|
| Explicit change | "switched from X to Y" in new fact | P1 regex → auto-supersede | ✓ covered |
| High-similarity rewrite | cosine(new, old) ≥ 0.50 | P2 cosine → needs_review | ✓ partially covered |
| Implicit behavioral drift | no single event; distributed across sessions | nothing fires | ✗ unsolved |
| Cross-lingual explicit | "ora usa X invece di Y" | nothing (regex English-only) | ✗ unsolved |

**The fundamental constraint:** P1 and P2 both operate at `remember()` time on a single fact. Implicit drift cannot be detected from a single fact in isolation — it requires observing the *pattern* across multiple sessions. This is a consolidation or retrieval concern, not a storage concern.

---

## 5. Next-Step Plan

### Phase 1 — Validation (before any new implementation)

**P1.1 Run temporal_eval supersession scenario**  
`tests/temporal_eval/` has a dedicated supersession scenario. We have never run it. This establishes a controlled baseline for the existing mechanism before any changes.

**P1.2 StaleMemory by-attribute breakdown**  
The current StaleMemory report groups by drift pattern (abrupt/gradual/noisy). Extract per-attribute detection rates from the raw output to confirm which attribute types fail and which succeed. Guides where to focus.

**P1.3 P2 ablation on StaleMemory**  
Run StaleMemory with P2 disabled (threshold back to 0.90) to confirm whether P2 has any effect on StaleMemory at all. If P2 on = P2 off, it is pure noise on this benchmark.

**P1.4 WikiScenarios S-family expansion**  
Currently S-family has only 2 scenarios, both with explicit change signals. Add implicit-drift S scenarios (no "switched from/to" language) to measure the implicit gap in a controlled, fast benchmark.

---

### Phase 2 — Retrieval layer (highest impact, lowest risk)

**P2.1 Recency-biased retrieval**  
When two active schemas in the same scope have similar topic (cosine > 0.70), bias ranking toward the newer one. Small additive `recency_bonus` based on `created_at` or `last_reinforced_at` in the retrieval scoring formula. Estimated impact: +3–8pp on StaleMemory (gradual/noisy drift especially). Zero false positive risk — only a relative reranking.

Implementation: ~10 lines in `slowave/core/services/retrieval.py`.

**P2.2 `needs_review` stronger suppression**  
Currently `needs_review` → score × 0.20. Consider making this harder: score × 0.05, or temporarily exclude from profile layer in default mode. Measure StaleMemory delta.

---

### Phase 3 — Session-end contradiction scan (medium effort)

After `session_end`, compare the session's newly produced schemas against existing active schemas in the same scope. For any pair where cosine > 0.70 but the core value differs, flag the older one as `needs_review`. This catches behavioral drift one session at a time rather than requiring a single explicit statement.

Implementation: new method in `SlowaveEngine.session_end()` or a `ConsolidationService` pass.

Risk: false positives if threshold is too low. Calibrate on StaleMemory.

---

### Phase 4 — Consolidation-time contradiction marking (medium effort)

During replay (ReplayEngine), after clustering prototypes, check if two active schemas in the same scope have:
- cosine similarity > 0.75 (same topic)
- significantly different content (as measured by diff vector magnitude)
- one created before the other (temporal ordering)

Mark the older one as `needs_review` or `superseded`. This operates on the accumulated history across all sessions — the right level of abstraction for implicit drift detection.

---

### Phase 5 — Cross-encoder NLI (longer term, highest impact)

A small fine-tuned cross-encoder (`cross-encoder/nli-MiniLM2-L6`) trained to detect "A contradicts B" would reliably catch implicit contradictions. Properties:
- 117MB ONNX, no torch, ~2ms per pair
- Handles the "user now does X" → contradicts "user prefers not-X" semantic relationship
- Language-agnostic (trained on XNLI / multilingual NLI corpora)
- Would cover all the StaleMemory failing categories (output_format, communication_style, etc.)

This is the approach that could push StaleMemory beyond 55–60%. It violates the pure-geometry thesis but is pragmatic for a critical capability.

---

### Phase 6 — Multilingual regex expansion

Add IT/FR/DE/ES equivalents to `STRONG_SUPERSESSION_PATTERNS`. Lower priority given:
- mnlm retrieval handles multilingual content well
- P2 cosine fallback is now language-agnostic
- StaleMemory doesn't test non-English content

---

## 6. Prioritised Work Queue

| Priority | Item | Expected StaleMemory impact | Effort |
|---|---|---|---|
| 1 | P1.1–P1.4 validation pass | — (measurement only) | Low |
| 2 | P2.1 Recency-biased retrieval | +3–8pp | Low |
| 3 | P2.2 Stronger needs_review suppression | +1–3pp | Very low |
| 4 | Phase 3 session-end contradiction scan | +5–10pp | Medium |
| 5 | Phase 4 consolidation contradiction marking | +3–8pp | Medium |
| 6 | Phase 5 cross-encoder NLI | +10–15pp | High |
| 7 | Phase 6 multilingual regex | — (recall only) | Low |

Realistic target after Phases 2–4: StaleMemory ~55–60%. Phase 5 (NLI) could reach ~65–70%.

---

## 7. Current Supersession Architecture (post-session)

```
remember(content) call
│
├── P1: regex patterns (STRONG_SUPERSESSION_PATTERNS)
│     English-only. Fires on: "now uses", "switched from X to Y",
│     "replaced X with Y", "no longer uses", "Use X instead of Y", "Prefer X over Y"
│     → high confidence (≥0.85): auto-supersede (status=superseded, salience=0.05)
│     → lower confidence: needs_review (score×0.20 in retrieval)
│
└── P2: cosine fallback (fires only when P1 finds nothing)
      FAISS top-10 candidates in scope
      cosine ≥ 0.50 → needs_review (score×0.20 in retrieval)
      [does NOT auto-supersede]

Retrieval
│
└── needs_review schemas: score×0.20
    superseded schemas: excluded (default mode) or included with heavy penalty
    [no recency bias — opportunity for Phase 2.1]

Consolidation (replay)
│
└── [no contradiction detection — opportunity for Phase 4]

session_end
│
└── [no contradiction scan — opportunity for Phase 3]
```

---

## 8. What Was Learned

1. **Explicit and implicit supersession are different problems.** P1/P2 address explicit changes well. Implicit drift requires a fundamentally different approach (history-aware, consolidation-time or session-end).

2. **Cosine is the strongest geometric signal.** Direction vectors are domain-local and not composable into a universal detector. The investigation confirmed this rigorously — cosine sep +0.32 beats mean centroid +0.09 globally.

3. **Recency should be a first-class signal in retrieval.** Two semantically similar schemas about the same user in the same scope — the newer one is almost always more correct. This is currently absent from the ranking formula.

4. **StaleMemory 45% floor** comes from the explicit supersession path plus cases where tech behavioral signals have lexical overlap with preference schemas (python, rust, camelCase, snake_case). The ceiling with the current architecture is unlikely to exceed 50% without retrieval-layer changes.

5. **The `needs_review` soft suppression is correct but insufficient.** The mechanism is sound; what's missing is the detection path for implicit drift to set the flag.
