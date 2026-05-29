# Slowave — Benchmark Reproducibility

This document describes how to reproduce the benchmark numbers in [docs/benchmarks.md](benchmarks.md).

## Environment

| Requirement | Tested value |
|---|---|
| Python | 3.10+ |
| Slowave | latest (`pip install slowave`) |
| Hardware | Mac M-series CPU; x86-64 Linux should work |
| RAM | ≥ 8 GB recommended |
| LLM required | No |

Run `slowave doctor` after installing to verify all dependencies load correctly.

## Datasets

### LongMemEval
- **Source:** https://github.com/xiaowu0162/LongMemEval
- **File:** `longmemeval_oracle.json` (500 questions, 6 categories)
- **Place at:** `data/longmemeval/longmemeval_oracle.json`

### LoCoMo
- **Source:** https://snap-stanford.github.io/locomo/
- **File:** `locomo10.json` (1986 questions, 5 categories, 10 conversations)
- **Download:**
  ```bash
  curl -o data/locomo/locomo10.json \
    https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json
  ```

## Running benchmarks

Evaluation harnesses are in `tests/integration/`. Both scripts now default to the brain-only path (`--schema-mode latent`) and episode-only mode (`--no-consolidate`). Run without `--no-consolidate` to get the full pipeline numbers.

### Smoke test (no dataset required)

```bash
pip install -e ".[dev]"
pytest tests/unit -q
# Expected: 100+ tests pass in < 60 seconds (NER tests skipped without en_core_web_sm)
```

### LongMemEval — episode-only (fast baseline, ~2-3 min)

```bash
python tests/integration/longmemeval_eval.py \
  --dataset data/longmemeval/longmemeval_oracle.json \
  --out data/longmemeval/runs/my_lme_episode_only.json
```

Expected: **~60.2%** overall, 149 s elapsed, 0 LLM calls.

### LongMemEval — with consolidation (full pipeline, ~10 min)

```bash
python tests/integration/longmemeval_eval.py \
  --dataset data/longmemeval/longmemeval_oracle.json \
  --out data/longmemeval/runs/my_lme_consolidated.json
  # --no-consolidate is omitted; consolidation runs per-question
```

Expected: **~70.0%** overall, 0 LLM calls.

### LoCoMo — episode-only (~1 min)

```bash
python tests/integration/locomo_eval.py \
  --out data/locomo/runs/my_locomo.json
```

Expected: **~74.6%** overall, 57 s elapsed, 0 LLM calls.

### Cosine-only ablation (disables all brain mechanisms)

```bash
python tests/integration/longmemeval_eval.py \
  --dataset data/longmemeval/longmemeval_oracle.json \
  --no-graph-expansion \
  --no-salience-rerank \
  --out data/longmemeval/runs/my_cosine_ablation.json
```

Expected: approximately equal to episode-only baseline (~60%).

## Configuration used for reported numbers

Default `SlowaveConfig` with all retrieval parameters at defaults:

| Parameter | Value |
|---|---|
| `use_spreading` | `True` |
| `spread_steps` | 2 |
| `use_multi_scale` | `True` |
| `use_temporal` | `True` |
| `temporal_weight` | 0.25 |
| `use_transition` | `True` |
| `schema_mode` | `latent` |

## Reproducibility caveats

1. **FAISS tie-breaks** may differ on different hardware, affecting <1% of questions.
2. **Embedding model version**: if `sentence-transformers` downloads a different model revision the scores may shift slightly. Pin to a specific commit if exact reproduction is required.
3. **Dataset version**: numbers are for LongMemEval and LoCoMo as of April–May 2026.
4. **consolidation=True runs are per-question**: each question gets its own fresh DB; the consolidation step runs inline. This matches how an agent would actually use Slowave in production.

## Reporting deviations

If your run differs materially from the reported numbers, open an issue with:
- `slowave doctor` output
- `slowave --version`
- Python version and OS
- The JSON summary block from your run
