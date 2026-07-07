# Encoder Selection & Geometry-Based Supersession Investigation

**Date:** 2026-06-18  
**Status:** Concluded  
**Trigger:** Python 3.14 install failure → multilingual encoder discussion → empirical cosine supersession investigation

---

## 1. Python 3.14 Install Failure

User on Homebrew Python 3.14 got:
```
Broken Python installation, platform.mac_ver() returned an empty value
```
Cause: Homebrew `python@3.14` packaging bug — `platform.mac_ver()` returns empty, `uv` (used by `pipx`) rejects the interpreter.

**Fix applied to `pyproject.toml`:**
- `requires-python` bumped `>=3.10` → `>=3.11` (onnxruntime 1.27+ dropped 3.10)
- `onnxruntime` constraint `>=1.16,<2.0` → `>=1.19`
- Classifier: removed `3.10`, added `3.14`
- README badge updated to `3.11+`

**Workaround for users on Python 3.14 Homebrew:**
```bash
pipx install slowave --python python3.12
```

---

## 2. Supersession Regex — The Problem

`slowave/core/supersession.py` contains 6 hardcoded English-only regex patterns:
```
"now uses / is now / has moved to"
"switched from X to Y"
"replaced X with Y"
"no longer uses / dropped"
"Use X instead of Y"
"Prefer X over Y"
```
These are English-only and contradict Slowave's latent-space-first design principle.

**Hypothesis tested:** cosine similarity already encodes supersession — no language needed.

---

## 3. bge-small-en-v1.5 Results (existing encoder)

Test: `tests/unit/test_supersession_geometry.py`, 19 pairs, 4 zones.
```
zone          range                mean    verdict
──────────────────────────────────────────────────
duplicate     0.9488 – 0.9542      0.952   overlap with supersession top
supersession  0.6476 – 0.9515      0.830   cross-lingual EN→IT = 0.65 (FAIL)
additive      0.4443 – 0.7544      0.649   bottom safe, top overlaps supers.
unrelated     0.3745 – 0.3874      0.381   clean separation ✓
```
Conclusion: zones exist but thresholds proposed (0.82) were wrong; cross-lingual broken.

---

## 4. Encoder Swap: bge-small-en → multilingual-e5-small

Replaced with `intfloat/multilingual-e5-small`:
- Same 384-dim → zero FAISS/SQLite migration
- ~100 language coverage
- ONNX via `Xenova/multilingual-e5-small`

Implementation notes:
- `token_type_ids` zero-filled when tokenizer omits them but ONNX graph requires them
- Xenova repo derived dynamically: `"Xenova/" + model_name.split("/")[-1]`
- `"query: "` prefix applied uniformly in `encode_many()` per e5 training convention

---

## 5. multilingual-e5-small Results

```
zone          e5+query: range      mean    e5 raw range         mean
──────────────────────────────────────────────────────────────────────
duplicate     0.975 – 0.981        0.978   0.959 – 0.970        0.964
supersession  0.878 – 0.967        0.930   0.906 – 0.967        0.941
additive      0.795 – 0.895        0.858   0.810 – 0.899        0.863
unrelated     0.770 – 0.800        0.784   0.759 – 0.827        0.789
```

Problem: all zones compressed into [0.76, 0.98]. Additive and unrelated OVERLAP.
The `"query: "` prefix provides no meaningful separation improvement.

Root cause: e5 was trained for asymmetric retrieval. Prefixing both sides maps
both into the same dense region — inflating all scores uniformly.

---

## 6. Three-Way Comparison

Models: `e5+query:`, `e5 raw`, `paraphrase-multilingual-MiniLM-L12-v2 (mnlm-L12)`

### Per-pair

```
zone           pair                   e5+query:   e5 raw    mnlm-L12
──────────────────────────────────────────────────────────────────────
supersession   en/SQLite->DuckDB        0.9294     0.9407    0.5078
supersession   en/Python->Go            0.9248     0.9334    0.4429
supersession   en/GPT4->Claude          0.8795     0.9055    0.5035
supersession   en/AWS->GCP              0.9157     0.9202    0.3526
supersession   en/dark->light           0.9674     0.9675    0.8012
supersession   it/SQLite->DuckDB        0.9566     0.9644    0.5298
supersession   it/Python->Go            0.9504     0.9543    0.2521
supersession   fr/SQLite->DuckDB        0.9575     0.9594    0.4316
supersession   de/SQLite->DuckDB        0.9446     0.9511    0.3857
supersession   cross/en-it              0.8783     0.9103    0.5005
additive       en/db+lang               0.8772     0.8714    0.2705
additive       en/lang+test             0.8629     0.8714    0.2621
additive       en/model+deploy          0.7951     0.8097    0.0672
additive       it/db+lang               0.8951     0.8989    0.2586
unrelated      en/db+weather            0.7701     0.7593    0.0673
unrelated      en/model+recipe          0.8003     0.8274    0.0825
unrelated      en/totally-diff          0.7807     0.7810   -0.0651
duplicate      en/rephrase-db           0.9807     0.9704    0.8783
duplicate      en/rephrase-lang         0.9749     0.9586    0.9451
```

### Zone summary

```
zone          e5+query:                  e5 raw                     mnlm-L12
──────────────────────────────────────────────────────────────────────────────────
supersession  [0.878,0.967] mean=0.930   [0.906,0.967] mean=0.941   [0.252,0.801] mean=0.471
additive      [0.795,0.895] mean=0.858   [0.810,0.899] mean=0.863   [0.067,0.270] mean=0.215
unrelated     [0.770,0.800] mean=0.784   [0.759,0.827] mean=0.789   [-0.065,0.083] mean=0.028
duplicate     [0.975,0.981] mean=0.978   [0.959,0.970] mean=0.964   [0.878,0.945] mean=0.912
```

---

## 7. Conclusions

### mnlm-L12 — rejected
Trained for semantic equivalence, not structural similarity with value substitution.
`en/SQLite->DuckDB` scores 0.51 (same as unrelated). Supersession range 0.25–0.80 — no
reliable signal. No cross-lingual coherence.

### multilingual-e5-small — right for retrieval, wrong for geometry-supersession
Band compression makes additive/unrelated indistinguishable via cosine alone.
Retains as Slowave default because multilingual retrieval is the primary job.

### Geometry-supersession thesis: falsified
No tested encoder produces cleanly separable zones suitable for cosine-only
auto-supersession. Threshold-based cosine is insufficient as a **primary gate**.
Remains valid as a conservative secondary signal (≥0.95 for near-verbatim rewording).

### Architecture decision: hybrid retained

| Layer | Role |
|---|---|
| Regex patterns (P1) | Primary gate — explicit change signals, English-only for now |
| Cosine fallback (P2) | Secondary — flags `needs_review` at ≥0.90, never auto-supersedes |
| multilingual-e5-small | Retrieval across all languages — the primary job |

---

## 8. Open Questions

1. **Multilingual regex:** extend `STRONG_SUPERSESSION_PATTERNS` with IT/FR/DE/ES equivalents
2. **Prefix strategy:** `"query: "` adds no benefit for symmetric comparison; consider removing it from storage calls (benchmark impact TBD)
3. **Existing DB migration:** live databases built with `bge-small-en-v1.5` contain incompatible embeddings — users upgrading need to reset or re-embed
4. **Benchmark regression:** full WikiScenarios + LongMemEval + LoCoMo run needed before releasing encoder change

---

## 9. Files Changed

| File | Change |
|---|---|
| `pyproject.toml` | requires-python >=3.11, drop 3.10/add 3.14, onnxruntime>=1.19 |
| `README.md` | badge 3.11+ |
| `slowave/symbolic/encoder.py` | default model → intfloat/multilingual-e5-small |
| `slowave/symbolic/onnx_encoder.py` | dynamic Xenova repo, query: prefix, token_type_ids zero-fill |
| `slowave/latent/temporal.py` | comment |
| `slowave/latent/vsa.py` | comment |
| `tests/unit/test_onnx_encoder.py` | model name string |
| `tests/unit/test_supersession_geometry.py` | **new** — empirical cosine zone validation |
| `tests/test_token_efficiency.py` | model name string |
| `tests/integration/longmemeval_eval.py` | print string |
| `tests/integration/stalememory_eval.py` | print string |
| `docs/limitations.md` | model name |
| `docs/token_efficiency.md` | model name in table |
