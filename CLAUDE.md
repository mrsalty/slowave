# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core thesis

Slowave is a neuroscience-inspired long-term memory system for AI agents. The central claim: **memory consolidation does not require language**. The LLM is an output-only channel (verbalization), never a memory operator. Memory is pure geometry over embeddings.

Current default: **brain-only mode** (`--schema-mode latent`). The LLM-extraction path (stages 0–5) is preserved for comparison but deprecated.

Benchmark results: LongMemEval 70.00%, LoCoMo 76.03% — zero LLM calls during ingest/retrieval.

## Commands

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
scripts/slowave-check.sh          # Verify Python imports, encoder, Ollama (optional)

# Unit tests (no Ollama/GPU required)
.venv/bin/python -m pytest tests/unit/test_smoke.py -v

# Benchmarks
.venv/bin/python tests/integration/longmemeval_eval.py --schema-mode latent --out data/longmemeval/runs/run.json
.venv/bin/python tests/integration/locomo_eval.py --schema-mode latent --assignment-threshold 0.65 --out data/locomo/runs/run.json

# Format
.venv/bin/python -m black --line-length 100 slowave/
.venv/bin/python -m isort --profile black slowave/
```

## Architecture

The system has two layers:

### Latent layer (`slowave/latent/`) — geometry only, no language

- **EpisodicStore** — append-only event memories. Embeddings + salience + timestamp, stored in SQLite + FAISS.
- **SemanticStore** — prototype clusters at two scales: *fine* (CA3, threshold 0.85) for exact retrieval, *coarse* (CA1, threshold 0.55) for pattern completion. Agreement between scales is a confidence signal (Stage 9).
- **ReplayEngine** — offline consolidation worker: samples episodes → clusters prototypes → salience decay → trains TransitionModel.
- **RetrievalPipeline** — multi-mechanism recall: cosine seed → predictive seed (TransitionModel, Stage 3) → spreading activation over prototype graph (Stage 1) → temporal bias (Stage 7).
- **GraphManager** — inter-prototype co-activation edges. Self-supervised replay (Stage 5) reinforces missed bridges.
- **TransitionModel** — small MLP predicting next-state embedding; also provides surprise signal for salience.
- **LatentSchemaBuilder** (`latent/schema.py`) — schemas as pure prototype geometry: centroid + SVD principal axes + temporal anchor + confidence. No LLM. This is the Stage 6 breakthrough (+10pp).

### Symbolic layer (`slowave/symbolic/`) — language interface

- **RawLog** — raw event storage (user/assistant turns), keyed by session_id.
- **EpisodeTextStore** — human-readable episode summaries linked to latent episodes.
- **SchemaStore** — typed claims with facets, status (active/needs_review/contradicted/superseded), salience, confidence, supporting episode links.
- **SchemaExtractor** — **legacy LLM path**, disabled in brain-only mode.
- **TextEncoder** (`encoder.py`) — sentence-transformers wrapper (`all-MiniLM-L6-v2`, dim=384), lazy-loaded.

### Engine & storage

- **SlowaveEngine** (`core/engine.py`) — facade wiring latent + symbolic + storage. Session lifecycle: `session_start` → `event_append` (encode+store, ~1ms) → `session_end` (form episodes, non-blocking) → background worker (replay → prototypes → schemas).
- **SQLiteDB** (`storage/sqlite_db.py`, `storage/schema.sql`) — single-file SQLite; all state is durable here. Schema auto-migrates on `init_schema`.
- **Config** (`core/config.py`) — `schema_mode` ("latent" or "llm"), embedding dim, per-subsystem configs.

## Data flow

```
event_append → raw log + FAISS (1ms, no LLM)
session_end  → micro/macro episodes from raw events (fast)
worker       → replay → prototypes (fine+coarse) → latent schemas → graph reinforcement
recall       → cosine + predictive + spreading-activation + temporal → ranked episodes/schemas
```

Consolidation is fully decoupled from ingest — the agent never waits on it.

## Stage history

Each stage is a tested hypothesis. Stages are documented in `docs/stages/`.

| Stage | Mechanism | Net effect |
|-------|-----------|------------|
| 1 | Spreading activation | +2–3pp |
| 3 | Predictive completion at recall | **+6.7pp** |
| 6 | Latent schemas (zero LLM) | **+10pp** |
| 7–9 | Temporal context, pattern separation, multi-scale | neutral (target sequential/multi-shot scenarios) |

Stages 7–9 are architecturally correct but empirically neutral on current public benchmarks. Do not remove them; they address failure modes not covered by LongMemEval/LoCoMo.

## Key environment variables

```
SLOWAVE_DB           Default: ~/.slowave/slowave.db
SLOWAVE_PROJECT      Default project scope (MCP)
SLOWAVE_MODEL        Legacy LLM model (qwen2.5:7b-instruct), only for --schema-mode llm
SLOWAVE_OLLAMA_URL   Default: http://localhost:11434
OPENROUTER_API_KEY    Cloud LLM backend (legacy)
```

## Testing strategy

- **Unit** (`tests/unit/test_smoke.py`): import check + synthetic latent end-to-end. No external deps.
- **Integration** (`tests/integration/`): LongMemEval and LoCoMo. Both support ablation flags (`--no-multi-scale`, `--no-transition`, `--schema-mode llm`). See `docs/benchmarks.md` for reproducing all numbers.
- **Temporal** (`tests/temporal_eval/`): 6 internal scenarios (chain, decay, reinforcement, coactivation, completion, supersession) for validating individual mechanism correctness.
