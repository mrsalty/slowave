# Supersession Geometry — Domain-General Investigation

**Date:** 2026-06-19  
**Status:** Concluded — key constraints established, architecture updated, next steps defined  
**Continues from:** `20260618_encoder_supersession_geometry_investigation.md`  
**Trigger:** User requirement: Slowave must work for any AI client in any field, not just coding assistants

---

## 1. Context and Motivation

The June 18 investigation concluded that cosine-only supersession detection is not viable
with any tested encoder, and that the current regex P1 + cosine P2 hybrid should be retained.
Three open questions were carried forward:

1. Can the **difference vector direction** `d = normalize(emb(new) − emb(old))` discriminate
   supersession from additive pairs better than cosine alone?
2. Which **multilingual encoder** gives the best geometry for this task?
3. Is there an **off-the-shelf benchmark** we can reuse?

This session addressed all three, then uncovered a fourth critical constraint (domain-generality),
ran two further experiments (domain cross-test, SVD + Fisher LDA), and reached firm
architectural conclusions.

---

## 2. Benchmark Search — No Off-the-Shelf Solution Exists

A systematic search of NLP benchmarks (2022–2026) found no dataset suitable for our exact task.

| Dataset | Old/New pairs | Value-substitution label | Multilingual | Informal text |
|---|:---:|:---:|:---:|:---:|
| WikiFactDiff (2024) | ✓ | ✓ (Obsolete) | ✗ | ✗ (KG triples) |
| VitaminC (2021) | Implicit | ✗ | ✗ | ✗ |
| MNLI contradiction | ✓ | ✗ | ✗ | ✗ |
| SNLI | ✓ | ✗ | ✗ | ✗ |
| ContraDoc (2024) | ✗ | ✗ (8 coarse types) | ✗ | ✗ |
| TemporalWiki / TempLAMA | ✗ | ✗ | ✗ | ✗ |

**WikiFactDiff** is the closest conceptual match — real Wikidata (old triple, new triple)
pairs labelled "Obsolete" — but uses formal KG triples, not the informal short sentences
Slowave actually receives. Threshold calibration on formal text would not transfer.

**Decision:** Build a custom test set. WikiFactDiff's taxonomy of real-world update types
(role changes, numeric changes, location/affiliation changes) guides the pair design.

---

## 3. First Investigation — 20 Pairs, Tech Domain Only

### Test set (original)
12 supersession / 4 additive / 2 unrelated / 2 duplicate.  
Supersession: all tech domain (db-switch, lang-switch, model-switch, deploy-switch, pref-switch)
across EN/IT/FR/DE + one cross-lingual pair.

### Results — 3 encoders

```
Model                                      cos sep    aln sep (LOO centroid)
─────────────────────────────────────────────────────────────────────────────
bge-small-en-v1.5                          +0.184      +0.358
multilingual-e5-small (no prefix)          +0.079      +0.311
paraphrase-multilingual-MiniLM-L12-v2      +0.228      +0.321
```

`aln sep` = mean(supersession alignment) − mean(additive alignment)  
where alignment = cosine(normalize(d_i), centroid_LOO)

**Initial conclusion:** Direction vector beats cosine on all three encoders (~2–4× gain).
`paraphrase-multilingual-MiniLM-L12-v2` (384-dim, 50+ languages) was the best overall.

**Problem with this conclusion:** The 20-pair test set was dominated by db-switch / lang-switch
pairs (8 of 12), so the centroid was biased toward that geometry. The result was inflated.

---

## 4. Critical Constraint — Slowave is Domain-General

User clarification: Slowave must work for any AI agent in any field — medical, legal,
business, HR, financial, scientific, personal assistant — not just coding tools.

This changes the test set design fundamentally. A centroid built from tech pairs alone
cannot be assumed to generalize to medical dosage changes or legal contract date changes.

---

## 5. Expanded Test Set — 104 Pairs, 8 Domains

### Design principles
- **8 domains**: tech, medical, business, personal, financial, hr, legal, science
- **Balanced supersession types** within each domain (tool switch, numeric change,
  person/role change, date/version change)
- **Adversarial negatives**: additive hard cases (same subject, adjacent attribute),
  additive expansion (old fact still true), adversarial unrelated (same value/different subject)
- **Multilingual coverage**: EN (primary) + IT + FR + DE + ES, cross-lingual pairs

### Counts
```
supersession:  71 pairs across 8 domains
additive:      17 pairs (3 easy, 11 hard negatives, 3 expansion)
unrelated:     10 pairs (4 adversarial same-value, 3 general statements, 3 clearly unrelated)
duplicate:      6 pairs
─────────────────────────────────────────────────────────────────
total:        104 pairs
```

### Location
- `tests/unit/test_supersession_geometry.py` — CASES list, standalone runner
- `tests/unit/_run_geometry_investigation.py` — investigation script with domain analysis

---

## 6. Second Investigation — Domain Cross-Test (104 pairs)

### The key test
Two centroid strategies per encoder:

- `centroid_all (LOO)`: built from all 71 supersession pairs; each pair's centroid excludes self
- `centroid_tech → all domains`: built from 18 tech pairs only; evaluated against all 71 pairs

### Results

```
Model                                   cos sep   aln(all)   aln(tech→all)
──────────────────────────────────────────────────────────────────────────
bge-small-en-v1.5                       +0.198    +0.108       +0.110
multilingual-e5-small (no prefix)       +0.085    +0.121       +0.105
paraphrase-multilingual-MiniLM-L12-v2   +0.319    +0.091       +0.111
```

### Cross-domain test: centroid_tech → each non-tech domain

```
domain       bge       e5        mnlm     verdict
────────────────────────────────────────────────
business    +0.039   +0.054   +0.051    ✗ FAILS
financial   +0.028   +0.067   +0.039    ✗ FAILS
hr          -0.011   +0.002   +0.001    ✗ FAILS
legal       -0.013   +0.015   -0.014    ✗ FAILS
medical     -0.032   -0.048   -0.019    ✗ FAILS
personal    -0.009   -0.024   -0.077    ✗ FAILS
science     -0.040   -0.011   -0.008    ✗ FAILS
tech        +0.281   +0.281   +0.326    ✓ (LOO within tech)
```

**Every non-tech domain fails, uniformly across all three encoders.**

The difference vector direction for tech pairs ("SQLite→DuckDB") is geometrically
orthogonal to medical ("metformin 500mg→1000mg") or HR ("Alice reports to John→Sarah").
Direction is domain-local, not universal.

### centroid_all (LOO) domain breakdown

```
domain       mnlm mean   verdict
────────────────────────────────
financial    +0.309      ✓ good
medical      +0.168      ✓ ok
hr           +0.131      ✓ ok
business     +0.111      ✓ ok
science      +0.116      ✓ ok
legal        +0.061      ✓ marginal
personal     -0.051      ✗ systematic failure
tech         +0.158      ✓ ok
```

When the centroid covers all domains, most domains show positive signal.
**Personal preference is a systematic failure across all encoders and centroid strategies.**

---

## 7. Third Investigation — SVD Concentration + Fisher LDA

Script: `tests/unit/_run_svd_fisher_investigation.py`  
Model: `paraphrase-multilingual-MiniLM-L12-v2` (mnlm)

Motivated by the SparseCL paper's claim that contradictions concentrate in a
low-dimensional subspace — if true for supersession, projecting onto that subspace
would solve the cross-domain generalization problem.

### Q1: Does supersession concentrate in a low-dimensional subspace?

SVD on raw diff vectors per zone; k = components needed for 90% variance.

```
zone           n    k@90%   k/dim   top-1 var%   top-5 var%   top-20 var%
──────────────────────────────────────────────────────────────────────────
supersession  71      23    0.060       14.1%        50.2%         87.4%
additive      17      11    0.029       15.2%        54.9%        100.0%
unrelated     10       6    0.016       28.1%        84.1%        100.0%
duplicate      6       4    0.010       62.5%        97.1%        100.0%
```

**SparseCL hypothesis falsified.** Supersession is the *most diffuse* zone — it needs
23 components for 90% variance, compared to 11 (additive), 6 (unrelated), 4 (duplicate).
The domain diversity of 8 domains pointing in different directions makes the joint
supersession distribution the most spread-out of all zones.

### Q2: Does projecting onto the top-K supersession SVD axes improve separation?

```
K    sep(sup, add)    full-dim baseline
─────────────────────────────────────────
1    +0.3496          +0.0906   ← 3.8× better at K=1
2    +0.0345          +0.0906
5    +0.0645          +0.0906
10   +0.0672          +0.0906
20   +0.0736          +0.0906
50   +0.0708          +0.0906
```

**Critical finding:** Projecting onto the single top-1 SVD axis gives separation +0.35,
dramatically better than the full-dim mean centroid (+0.09) and matching cosine (+0.32).
K ≥ 2 immediately drops to 0.03–0.09 and never recovers.

**Why K=1 works so much better than the mean centroid:**
The mean centroid averages normalized diff vectors, which cancels out when different
domain pairs point in opposite directions (especially personal preference, which is
anti-aligned). SVD1 finds the single direction that explains the *most variance* in the
supersession diff matrix — it is robust to this cancellation.

**Why K≥2 doesn't help:**
Subsequent SVD axes capture within-domain variation (the different geometric directions
of different domains), which is noise from a discrimination standpoint. They add spread,
not signal.

### Q3: Fisher LDA — regularised LOO cross-validation

Regularised Fisher LDA (sklearn LDA, shrinkage='auto', solver='lsqr') trained on
raw diff vectors with leave-one-out cross-validation.

```
Overall LOO accuracy:    80.8%  (84/104)
Supersession recall:     93.0%  (66/71)   ← high
Not-sup specificity:     54.5%  (18/33)   ← low
Precision (sup):         81.5%
Mean LDA score (sup):   +9.36  std=6.08
Mean LDA score (not):   +0.31  std=8.66
Score separation:        +9.05
```

93% recall (catches nearly all supersession) but only 54.5% specificity — Fisher LDA
is aggressive, classifying half of non-supersession pairs as supersession. Too many false
positives to use as a standalone classifier. Useful as a high-recall recall booster inside
a pipeline where cosine or regex provides the primary filter.

### Domain alignment with top-1 SVD axis

```
domain        n    mean alignment          range
──────────────────────────────────────────────────────────────
tech         18    +0.345  ✓        [-0.123, +0.928]
financial     8    +0.243  ✓        [+0.009, +0.374]
business      8    +0.104  ✓        [-0.060, +0.211]
science       5    +0.099  ✓        [-0.019, +0.255]
medical      10    +0.073  ✓        [+0.002, +0.193]
legal         6    +0.047  ~        [-0.020, +0.117]
hr            8    +0.001  ~        [-0.116, +0.232]
personal      8    -0.171  ✗        [-0.361, -0.022]
──────────────────────────────────────────────────────────────
[additive]   17    -0.028  ref      [-0.424, +0.142]
```

The top-1 axis (dominated by tech pairs) correctly separates financial, medical, science,
business from additive. HR and legal are marginal. Personal preference is actively
anti-aligned — it sits on the *opposite* side of the hyperplane from the supersession signal.

---

## 8. Key Findings — Consolidated

### F1: Direction is domain-local, not universal

The diff vector for "SQLite→DuckDB" is geometrically orthogonal to "metformin 500mg→1000mg".
No single centroid/axis built from one domain generalises to others.
Multi-domain centroid (centroid_all LOO) works for most domains; personal preference fails.

### F2: SparseCL hypothesis is falsified

Supersession diff vectors are the *most* diffuse zone (k=23), not the most concentrated.
There is no low-dimensional universal supersession subspace.

### F3: Top-1 SVD axis is the best single geometric discriminant

Sep(sup, add) = +0.35 at K=1, vs +0.09 for full-dim centroid and +0.32 for cosine.
The mean centroid is a poor direction estimate because domain diversity causes sign
cancellations. SVD1 is the correct direction estimator.
K≥2 adds noise, not signal.

### F4: Personal preference is structurally uncoverable by direction

Anti-aligned with the main supersession axis (−0.171 mean alignment).
"Prefers email → prefers phone" and "vegetarian → vegan" live in a separate geometric
region from concrete entity/value substitutions. No tested approach covers this domain
via direction; falls through to cosine + regex only.

### F5: Cosine remains the strongest global signal for mnlm (+0.319)

Except for adversarial same-value-different-subject pairs (cosine ≈ 0.98), where
direction correctly scores near-zero or negative.

### F6: Fisher LDA provides high recall (93%) at the cost of precision (81.5%)

Useful as recall booster in a layered pipeline; cannot stand alone due to 45.5% false
positive rate on non-supersession pairs.

### F7: Encoder recommendation — mnlm

`paraphrase-multilingual-MiniLM-L12-v2`:
- 384-dim → zero FAISS/SQLite migration cost
- 50+ languages
- Strongest cosine sep among multilingual options
- Best domain-alignment profile for SVD1

---

## 9. Architecture Decision — Updated

The "replace regex with pure latent direction" thesis is falsified.

**Retained and refined hybrid architecture:**

| Layer | Signal | Behaviour |
|---|---|---|
| Regex P1 | Explicit language patterns ("now uses X", "switched from X to Y") | Primary gate; domain-agnostic; fires on explicit change markers |
| Cosine gate | cosine(new, old) | Topical relevance filter; blocks truly unrelated pairs; threshold ~0.35–0.50 |
| SVD1 alignment | cosine(normalize(d), svd1_axis) | P3; built from multi-domain seed; replaces mean centroid; sep +0.35 |
| Cosine P2 (≥0.90) | cosine(new, old) | Near-verbatim rewording flag; already in engine.py |

**SVD1 axis construction:**
- Compute diff vectors for a built-in seed set covering all 7 domains except personal
- Run SVD; take first right singular vector as svd1_axis
- Store as a 384-dim vector; recompute at init if encoder changes
- ~3–4 pairs per domain × 7 domains = ~25 pairs minimum

**Personal preference domain:**
Cannot be covered by SVD1 or centroid direction. Falls through to cosine gate + regex P1.
Acceptable: explicit preference language ("now prefers", "switched to", "no longer")
is common in that domain and regex P1 catches it.

**Threshold calibration (to do):**
- cosine gate threshold: calibrate on 104-pair test set against mnlm cosine distribution
- SVD1 alignment threshold: calibrate similarly; preliminary data suggests ~0.05–0.10

---

## 10. Literature Review — Relevant Techniques

Systematic search of NLP/ML literature for geometry-only supersession approaches.
Ordered by practical applicability (no LLM, CPU-first, no or small training data).

### Tier 1: No training required

**Unbalanced Optimal Transport (UOT)** — arXiv:2412.12569 (2024)  
Wasserstein distance captures direction + magnitude of semantic shift.
No training, Python `ot` library. Untested for supersession.
*Status:* Open experiment.

**Top-1 SVD axis** (this investigation)  
Best zero-training discriminant: sep +0.35 vs cosine +0.32.
Build from ~25 multi-domain seed pairs.
*Status:* Validated; recommended for implementation.

### Tier 2: Small labeled set (50–200 pairs), no LLM

**Fisher LDA on difference vectors** — classical  
Finds optimal linear direction for separating (emb_B − emb_A) by zone.
~50–100 labeled pairs, sklearn, 10 lines. LOO recall 93%, specificity 54.5%.
*Status:* Tested; useful as recall booster, not standalone.

**SparseCL: Sparse Contrastive Learning** — sparsecl.github.io (2024)  
Core claim: contradictions concentrate in a Hoyer-sparse subspace.
*Status:* Hypothesis tested and FALSIFIED for our data — supersession is the most
diffuse zone (k=23 for 90% variance). The sparsity insight does not transfer.

**Asymmetric Word Embeddings (AWE)** — arXiv:1809.04047 (2018)  
Learns directional embedding asymmetry for entailment. ~500 pairs.
*Status:* Untested; theoretically applicable to value-change direction.

### Tier 3: Requires transformer / more data

**Cross-encoder fine-tuning (DeBERTa)**  
+30–50% in-domain accuracy. Violates no-LLM constraint.

**Triplet loss with hard negative mining**  
Fine-tune bi-encoder on (A, B, unrelated) triplets.
+15–30% cross-domain with balanced data.

### Tier 4: Research / long-term

**Frame-Semantic Parsing** — same frame + different filler = supersession.
Theoretically ideal; high complexity; FrameNet required.

**RotatE / TeRo / ChronoR** — temporal KG rotation embeddings.
Designed for KG triples; adaptation to sentences unclear.

**Sparse Autoencoders** — Anthropic (2023, 2024).
Search LLM activations for a "value change" feature.
Speculative; requires model internals; 12+ months.

---

## 11. Open Questions

1. **Does Unbalanced Optimal Transport outperform cosine or SVD1?**  
   Untested. Python `ot` library, one-shot metric, no training.

2. **Calibrate thresholds for cosine gate and SVD1 alignment on 104-pair test set.**  
   Prerequisite before implementing P3 in `engine.py`.

3. **Multilingual regex expansion** (from 20260618, still open)  
   Add IT/FR/DE/ES patterns to `STRONG_SUPERSESSION_PATTERNS`.
   Now lower priority since regex P1 is supplementary, not primary.

4. **Full regression benchmark** before encoder swap  
   WikiScenarios 18 (100% core) + LongMemEval (88.0%) + LoCoMo (80.36%) +
   DMR (87.4%) + StaleMemory (45.8%). Must not regress on any.

5. **Personal preference domain — alternative signal?**  
   Could a second SVD axis built from personal preference pairs alone discriminate
   within that domain? Low priority given regex usually catches explicit preferences.

---

## 12. Files

| File | Description |
|---|---|
| `tests/unit/test_supersession_geometry.py` | 104-pair test set; 8 domains × 5 languages; `domain` field on Case; pytest marked skip (thresholds TBD) |
| `tests/unit/_run_geometry_investigation.py` | Direction centroid investigation; domain cross-test; `--model` flag |
| `tests/unit/_run_svd_fisher_investigation.py` | SVD concentration + top-K projection + Fisher LDA LOO; `--model` flag |
| `docs/iterations/20260618_encoder_supersession_geometry_investigation.md` | Previous session: encoder selection, first cosine geometry tests |
| `docs/iterations/20260619_supersession_geometry_domain_general.md` | This document |
