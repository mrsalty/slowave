# Slowave — Benchmark Reproducibility

This document describes how to reproduce the benchmark numbers in [docs/benchmarks.md](benchmarks.md).

## Environment

| Requirement | Tested value |
|---|---|
| Python | 3.11+ |
| Slowave | latest (`pip install slowave`) |
| RAM | ≥ 8 GB recommended |
| LLM required | No (LLM-judge scoring is optional, requires API key) |

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
  - `data/longmemeval/longmemeval_oracle.json` — 500 questions, evidence-only sessions
  - `data/longmemeval/longmemeval_s_cleaned.json` — 500 questions, ~48 sessions/question with distractors, full haystack

### LoCoMo
- **Source:** https://snap-stanford.github.io/locomo/ (ACL 2024, public)
- **File after download:** `data/locomo/locomo10.json` — 1,986 questions, 5 categories, 10 conversations

### DMR (MSC-Self-Instruct)
- **Source:** https://huggingface.co/datasets/MemGPT/MSC-Self-Instruct (Apache-2.0)
- **File after download:** `data/dmr_original/msc_self_instruct.jsonl` — 500 records

### StaleMemory
- **Source:** Synthetically generated benchmark
- **File after download:** `data/stalememory/scenarios.jsonl` — 1,200 scenarios, 8 attributes × 3 drift patterns
- Deterministically generated; no LLM required to reproduce it.

## Running benchmarks

Evaluation harnesses are in `tests/benchmarks/`. All benchmarks use **engine defaults** with consolidation enabled — no `--top-k`, `--assignment-threshold`, or `RetrievalConfig` overrides. This matches production behavior.

### Run the full suite (keyword-overlap, no LLM judge)

```bash

# Full run no llm-judge (all datasets but BEAM must be present)
python tests/benchmarks/run_full_benchmark.py --no-llm

# Full run (needs `OPENROUTER_API_KEY` for llm-judge, all datasets must be present)
python tests/benchmarks/run_full_benchmark.py

# Quick smoke across all benchmarks (~5 min)
python tests/benchmarks/run_full_benchmark.py --limit 1

# Skip a specific benchmark
python tests/benchmarks/run_full_benchmark.py --skip stalememory

# Results saved to data/suite_runs/<timestamp>/summary.json
```

### Smoke test (no dataset required)

```bash
pip install -e ".[dev]"
pytest tests/unit -q
# Expected: 100+ tests pass in < 60 seconds
```

### LongMemEval (keyword-overlap)

```bash
# Full haystack with consolidation (canonical run, ~10 min)
python tests/benchmarks/longmemeval_eval.py   --dataset data/longmemeval/longmemeval_s_cleaned.json   --consolidate   --out data/longmemeval/runs/my_lme.json
```

Expected: **~87.8%** keyword-overlap, 0 LLM calls.

### LongMemEval (LLM-judge)

```bash
# Semantic grading with deepseek-v4-flash (~5 min + API time)
python tests/benchmarks/longmemeval_eval.py   --dataset data/longmemeval/longmemeval_s_cleaned.json   --consolidate   --judge-model deepseek-v4-flash   --out data/longmemeval/runs/my_lme_judge.json
```

Expected: **~55.8%** LLM-judge, 500 API calls. Requires `OPENROUTER_API_KEY`.

### LoCoMo (keyword-overlap)

```bash
# With consolidation (canonical run, ~3 min)
python tests/benchmarks/locomo_eval.py   --dataset data/locomo/locomo10.json   --consolidate   --out data/locomo/runs/my_locomo.json
```

Expected: **~85.75%** keyword-overlap, 0 LLM calls.

### LoCoMo (LLM-judge)

```bash
python tests/benchmarks/locomo_eval.py   --dataset data/locomo/locomo10.json   --consolidate   --judge-model deepseek-v4-flash   --out data/locomo/runs/my_locomo_judge.json
```

Expected: **~69.3%** LLM-judge, 1,540 API calls. Requires `OPENROUTER_API_KEY`.

### DMR

```bash
python tests/benchmarks/dmr_original_eval.py   --dataset data/dmr_original/msc_self_instruct.jsonl   --consolidate   --out data/dmr_original/runs/my_dmr.json
```

Expected: **~99.0%** keyword-overlap, 0 LLM calls. Near-ceiling retrieval benchmark.

### StaleMemory

```bash
python tests/benchmarks/stalememory_eval.py   --dataset data/stalememory/scenarios.jsonl   --consolidate   --out data/stalememory/runs/my_stalememory.json
```

Expected: **~39.5%** detection overall, 0 LLM calls.
Per-attribute range: 0% (`explanation_approach`, `example_scope`, `error_handling`) to 100% (`programming_language`).
Timestamps are injected automatically (sessions spread over 180-day window) to activate salience decay and temporal recency.

### BEAM (LLM-judge only)

```bash
# Full run (~2 h, requires OPENROUTER_API_KEY)
python tests/benchmarks/beam_eval.py   --consolidate   --judge-model deepseek-v4-flash   --workers 6   --out data/beam/runs/my_beam.json
```

Expected: **~41.6%** LLM-judge with ≤4.1% parse-error rate. BEAM measures retrieval + answer-generation as a compound score — Recall@20 is 97–100% across all categories. See [docs/benchmarks.md](benchmarks.md) for the retrieval-vs-reasoning distinction.

## Configuration

All benchmarks use **engine defaults** — no `--top-k`, `--assignment-threshold`, or `RetrievalConfig` overrides. The engine is tested as a black box, matching production behavior. BEAM uses its own sanctioned overrides (`assignment_threshold=0.65`, `max_prototypes_per_replay=64`) for dense 1,700-message conversations.

Core retrieval parameters at defaults:

| Parameter | Value |
|---|---|
| `episodic_top_k` | 10 |
| `spread_episodic_top_k` | 10 |
| `semantic_top_k` | 6 |
| `neighbor_top_k` | 6 |
| `episodes_per_prototype` | 6 |
| `use_spreading` | True |
| `use_temporal` | True |
| `use_transition` | True |

## Reproducibility caveats

1. **FAISS tie-breaks** may differ on different hardware, affecting <1% of questions.
2. **Embedding model version**: if `sentence-transformers` downloads a different model revision the scores may shift slightly. Pin to a specific commit if exact reproduction is required.
3. **Dataset version**: numbers are for LongMemEval and LoCoMo as of April–May 2026.
4. **Consolidation runs are per-question**: each question gets its own fresh DB; the consolidation step runs inline. This matches how an agent would actually use Slowave in production.

---

## Reporting deviations

If your run differs materially from the reported numbers, open an issue with:
- `slowave doctor` output
- `slowave --version`
- Python version and OS
- The JSON summary block from your run
