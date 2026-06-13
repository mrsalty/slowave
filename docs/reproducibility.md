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

Datasets are **not included** in the repository (too large or third-party licensed). Download them first:

```bash
# Download all datasets at once
bash scripts/download_datasets.sh

# Or individual datasets
bash scripts/download_datasets.sh locomo       # 2.7 MB
bash scripts/download_datasets.sh lme          # 15 MB oracle + 265 MB haystack
bash scripts/download_datasets.sh dmr          # 8.2 MB
bash scripts/download_datasets.sh stalememory  # 13 MB synthetic
```

### LongMemEval
- **Source:** https://github.com/xiaowu0162/LongMemEval (check license before redistributing)
- **Files after download:**
  - `data/longmemeval/longmemeval_oracle.json` — 500 questions, evidence-only sessions, fast regression guard
  - `data/longmemeval/longmemeval_s_cleaned.json` — 500 questions, ~48 sessions/question with distractors, full haystack

### LoCoMo
- **Source:** https://snap-stanford.github.io/locomo/ (ACL 2024, public)
- **File after download:** `data/locomo/locomo10.json` — 1986 questions, 5 categories, 10 conversations

### DMR (MSC-Self-Instruct)
- **Source:** https://huggingface.co/datasets/MemGPT/MSC-Self-Instruct (Apache-2.0)
- **File after download:** `data/dmr_original/msc_self_instruct.jsonl` — 500 records

### StaleMemory
- **Source:** Synthetically generated benchmark (EMNLP 2026, under review)
- **File after download:** `data/stalememory/scenarios.jsonl` — 1,200 scenarios, 8 attributes × 3 drift patterns
- Deterministically generated; no LLM required to reproduce it.

## Running benchmarks

Evaluation harnesses are in `tests/integration/`. The currently reported headline suite uses `--no-consolidate` for the zero-LLM episodic/latent retrieval path; omit it only when intentionally testing consolidation variants.

### Run the full suite (all four benchmarks)

```bash
# Full run (~40 min, all datasets must be present)
python tests/integration/run_full_benchmark.py

# Quick smoke across all benchmarks (~5 min)
python tests/integration/run_full_benchmark.py --limit 5

# Skip a specific benchmark
python tests/integration/run_full_benchmark.py --skip stalememory

# Results saved to data/runs/<timestamp>/summary.json
```

### Smoke test (no dataset required)

```bash
pip install -e ".[dev]"
pytest tests/unit -q
# Expected: 100+ tests pass in < 60 seconds
```

### LongMemEval — episode-only baseline (~2-3 min)

```bash
python tests/integration/longmemeval_eval.py \
  --dataset data/longmemeval/longmemeval_oracle.json \
  --no-consolidate \
  --out data/longmemeval/runs/my_lme_episode_only.json
```

Expected: **~60.2%** overall, 0 LLM calls.

### LongMemEval — oracle canonical run (~8 min)

```bash
python tests/integration/longmemeval_eval.py \
  --dataset data/longmemeval/longmemeval_oracle.json \
  --assignment-threshold 0.85 \
  --top-k 10 \
  --no-consolidate \
  --out data/longmemeval/runs/my_lme_oracle.json
```

Expected: **~87.8%** overall, 0 LLM calls.
Per-category: knowledge-update ~94.9%, multi-session ~79.7%, temporal ~87.2%, single-session-pref ~76.7%.

### LongMemEval — fullhaystack canonical run (~2.3 h)

```bash
python tests/integration/longmemeval_eval.py \
  --dataset data/longmemeval/longmemeval_s_cleaned.json \
  --assignment-threshold 0.85 --top-k 10 \
  --out data/longmemeval/runs/my_lme_fullhaystack.json
```

Expected: **~93.4%** overall, 0 LLM calls.
Per-category: knowledge-update ~94.9%, multi-session ~86.5%, temporal ~96.2%, single-session-pref **~100% (windfall artefact — treat oracle 76.7% as the conservative number for this category)**.
Ingest: ~16.4 s/question, ~14.7 MB DB/question. Total: ~2.3 h for n=500.

> Requires `longmemeval_s_cleaned.json`. Download from https://github.com/xiaowu0162/LongMemEval and place at `data/longmemeval/longmemeval_s_cleaned.json`.

### LoCoMo — episode-only baseline (~1 min)

```bash
python tests/integration/locomo_eval.py \
  --dataset data/locomo/locomo10.json \
  --no-consolidate \
  --out data/locomo/runs/my_locomo_episode_only.json
```

Expected: **~74.6%** overall, 0 LLM calls.

### LoCoMo — canonical run (~3 min)

```bash
python tests/integration/locomo_eval.py \
  --dataset data/locomo/locomo10.json \
  --assignment-threshold 0.85 \
  --no-consolidate \
  --out data/locomo/runs/my_locomo.json
```

Expected: **~81%** total, adversarial ~91%, multi-session ~86%, 0 LLM calls.

### StaleMemory -- implicit belief staleness

```bash
# Sample run (120 scenarios, ~80s on M-series)
python tests/integration/stalememory_eval.py \
  --limit 5 \
  --out data/stalememory/runs/my_stale_sample.json

# Full run (1,200 scenarios, ~15 min)
python tests/integration/stalememory_eval.py \
  --out data/stalememory/runs/my_stale_full.json
```

Expected (sample, 120 scenarios with synthetic timestamp injection):
- **Detection rate: ~37–43%** (post-drift value recalled correctly), 0 LLM calls
- Stale persistence: ~38% (pre-drift anchor recalled instead)
- No answer: ~19–25%

Full run (1 200 scenarios) expected: **~46% detection**, 0 LLM calls.

Timestamps are injected automatically (sessions spread over 180-day window). This activates salience decay and the temporal recency bonus. Per-attribute range: 0% (`explanation_approach`, `example_scope`) to 100% (`programming_language`, `naming_convention`).

### Original MemGPT DMR source candidate — retrieval-context metric

Download source data from Hugging Face:

```bash
mkdir -p data/dmr_original
curl -L -o data/dmr_original/token_efficiency.md \
  https://huggingface.co/datasets/MemGPT/MSC-Self-Instruct/resolve/main/README.md
curl -L -o data/dmr_original/msc_self_instruct.jsonl \
  https://huggingface.co/datasets/MemGPT/MSC-Self-Instruct/resolve/main/msc_self_instruct.jsonl
```

Run the retrieval-context evaluator:

```bash
python tests/integration/dmr_original_eval.py \
  --dataset data/dmr_original/msc_self_instruct.jsonl \
  --out data/dmr_original/runs/my_dmr_original_retrieval.json
```

Expected: **~86–87%** retrieval-context keyword hit-rate over 500 records in the latest full-suite runs (older standalone runs reached ~91%), 0 LLM calls, ~6–18 ms recall. This is **not** the published MemGPT/Zep generated-answer + LLM-judge protocol.

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

## Reproducibility caveats

1. **FAISS tie-breaks** may differ on different hardware, affecting <1% of questions.
2. **Embedding model version**: if `sentence-transformers` downloads a different model revision the scores may shift slightly. Pin to a specific commit if exact reproduction is required.
3. **Dataset version**: numbers are for LongMemEval and LoCoMo as of April–May 2026.
4. **consolidation=True runs are per-question**: each question gets its own fresh DB; the consolidation step runs inline. This matches how an agent would actually use Slowave in production.

## Expected numbers at a glance

| Benchmark | Config | Expected score |
|---|---|---|
| LongMemEval (oracle) | episode-only, `--no-consolidate` | ~60.2% |
| LongMemEval (oracle) | `--no-consolidate --assignment-threshold 0.85 --top-k 10` | **~87.8%** |
| LongMemEval (full haystack) | `--assignment-threshold 0.85 --top-k 10` | **~93.4%** |
| LoCoMo | `--no-consolidate` (episode-only) | ~74.6% |
| LoCoMo | `--assignment-threshold 0.85` (with consolidation) | **~81%** |
| DMR | default | **~86–87%** |
| StaleMemory | full, ts-injected | **~46% detection** |

---

## Reporting deviations

If your run differs materially from the reported numbers, open an issue with:
- `slowave doctor` output
- `slowave --version`
- Python version and OS
- The JSON summary block from your run
