# Slowave Benchmarks

> **Alpha-stage results.** Numbers reported here are from internal runs and have not been independently verified. Treat as directional indicators. Reproducibility scripts are in `tests/integration/`.

## Overview

All runs use the **brain-only path**: local CPU, BAAI/bge-small-en-v1.5 embeddings, SQLite + FAISS — **zero LLM calls**, no API key, no cloud service.

Two modes are tracked:

- **With consolidation** — the full pipeline: episodes → replay → prototypes → latent schemas → recall. Schemas are formed per-question during ingest and contribute to recall.
- **Episode-only (no consolidation)** — episodes ingested and recalled directly, no prototype/schema layer. This is the faster path and a meaningful baseline.

The delta between the two shows the contribution of the consolidation layer.

## Overall Results

| Benchmark | n | With consolidation | Episode-only | Cosine-only ablation¹ |
|---|---:|---:|---:|---:|
| LongMemEval | 500 | **70.0%** | 60.2% | ~60.0% |
| LoCoMo | 1 986 | **74.6%** | 74.6%² | ~68.0% |

**Metric:** keyword hit-rate (answer keywords present in retrieved context).  
**Recall latency:** ~10 ms per query on local Mac M-series CPU.  
**Data:** stays fully on device.  
**LLM calls:** 0 in all runs.

¹ Cosine-only: spreading activation, graph expansion, and transition model disabled. Plain FAISS nearest-neighbour.  
² LoCoMo is multi-session by design; episode retrieval already captures the signal. Consolidation adds latent schemas on top of an already-strong baseline.

## Run Conditions

| Parameter | Value |
|---|---|
| Embedding model | `BAAI/bge-small-en-v1.5` (384 dim) |
| Hardware | MacBook Pro M-series CPU |
| Schema mode | `latent` (brain-only, zero LLM) |
| LLM calls | 0 |
| Python | 3.12 |
| LME elapsed | 149 s (episode-only) • ~10 min (with consolidation) |
| LoCoMo elapsed | 57 s (episode-only) |

## Deep Memory Retrieval (DMR)

DMR (MemGPT paper, arXiv:2310.08560) tests factual recall across multi-session persona conversations: 10 personas × 10 questions = 100 questions. Published baselines use LLM-augmented memory; Slowave uses zero LLM calls.

| System | Score | LLM calls | Cost |
|---|---:|---|---|
| **Slowave** | **95.0%** | **0** | **$0.00** |
| Zep SOTA (arXiv:2501.13956) | 94.8% | Many | $ |
| MemGPT baseline | 93.4% | Many | $ |

**Recall latency:** ~9 ms/q.  **Dataset:** `data/dmr/dmr.json`.  **Script:** `tests/integration/dmr_eval.py`.

Per-persona breakdown:

| Persona | N | Hits | Hit% |
|---|---:|---:|---:|
| David | 10 | 10 | **100%** |
| Maria | 10 | 10 | **100%** |
| James | 10 | 10 | **100%** |
| Priya | 10 | 10 | **100%** |
| Tom | 10 | 10 | **100%** |
| Elena | 10 | 10 | **100%** |
| Marcus | 10 | 10 | **100%** |
| Yuki | 10 | 9 | 90% |
| Robert | 10 | 9 | 90% |
| Sarah | 10 | 7 | 70% |
| **TOTAL** | **100** | **95** | **95%** |

The 5 misses are concentrated on Sarah's introductory session turn (first-turn salience gap — early episodes get lower initial salience before replay) and two near-miss keyword overlaps (ks just below 0.5).

---

## LongMemEval Per-Category (with consolidation)

| Category | Score | Notes |
|---|---:|---|
| Single-session-user | **91.4%** | ✅ strong |
| Knowledge-update | **92.3%** | ✅ strong |
| Single-session-assistant | **66.1%** | ✅ solid |
| Temporal-reasoning | **67.7%** | ✅ solid |
| Multi-session | 60.9% | ⚠ number aggregation gap |
| Single-session-preference | 20.0% | ⚠ preference abstraction gap |

**Consolidation contribution on LME:**

| Category | Episode-only | With consolidation | Δ |
|---|---:|---:|---:|
| knowledge-update | 66.7% | 92.3% | **+25.6 pp** |
| temporal-reasoning | 55.6% | 67.7% | **+12.1 pp** |
| multi-session | 51.1% | 60.9% | **+9.8 pp** |
| single-session-assistant | 66.1% | 66.1% | 0 |
| single-session-user | 91.4% | 91.4% | 0 |
| single-session-preference | 20.0% | 20.0% | 0 |

The knowledge-update and temporal-reasoning gains come from the latent schema layer: schemas capture cross-session patterns that individual episodes do not retain.

## LoCoMo Per-Category (with consolidation)

| Category | Score | Notes |
|---|---:|---|
| Multi-session | **86.2%** | ✅ strong cross-session recall |
| Adversarial | **82.3%** | ✅ robust |
| Single-session | 64.9% | ✅ solid |
| Temporal | **56.1%** | ✅ solid |
| Commonsense | 27.1% | — world knowledge not in store |

## Known Gaps

| Gap | Root cause | Status |
|---|---|---|
| Temporal date arithmetic (LME) | Arithmetic over two retrieved timestamps — not a retrieval problem | Open — answer-construction layer |
| Multi-session LME (60.9%) | Aggregate answer is never in a single episode | Open — explicit aggregation |
| Preference LME (20%) | Implicit preferences not abstracted into queryable schema entries | Open — preference-extraction layer |
| Commonsense LoCoMo (27.1%) | Requires world knowledge not in the memory store | Out of scope for local memory |

## Comparison Notes

The table below is informational only. Systems differ in encoder, metric, and evaluation protocol.

| System | LongMemEval | LoCoMo | Notes |
|---|---:|---:|---|
| Slowave (with consolidation) | 70.0% | 74.6% | keyword hit-rate, zero LLM |
| Slowave (episode-only) | 60.2% | 74.6% | keyword hit-rate, zero LLM, no consolidation |
| Cosine RAG (ablation) | ~60.0% | ~68.0% | same encoder, brain mechanisms disabled |
| Mem0 (reported) | ~94.4% | ~92.5% | LLM extraction; different metric and protocol |

Mem0 uses LLM-based extraction and a different evaluation protocol. Slowave is for developers who want private, local, zero-LLM memory that runs entirely on device.

## Reproducibility

Evaluation scripts are in `tests/integration/`. Both default to `--schema-mode latent` and `--no-consolidate` (episode-only path). Omit `--no-consolidate` for the full pipeline run.

```bash
# Episode-only (fast, ~2-3 min)
python tests/integration/longmemeval_eval.py \
  --dataset data/longmemeval/longmemeval_oracle.json \
  --out data/longmemeval/runs/my_run.json

# Full pipeline with consolidation (~10 min)
python tests/integration/longmemeval_eval.py \
  --dataset data/longmemeval/longmemeval_oracle.json \
  --out data/longmemeval/runs/my_run_consolidated.json
  # (omit --no-consolidate; consolidation runs per-question)
```

See [docs/reproducibility.md](reproducibility.md) for dataset download links and caveats.
