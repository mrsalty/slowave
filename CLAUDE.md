# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core thesis

Slowave is a neuroscience-inspired long-term memory system for AI agents. The central claim: **memory consolidation does not require language**. The LLM is an output-only channel (verbalization), never a memory operator. Memory is pure geometry over embeddings.

Memory consolidation runs entirely in brain-only mode: no LLM calls, no Ollama, no cloud service required.

## Commands

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
scripts/slowave-check.sh          # Verify Python imports and encoder

# Unit tests (no GPU required)
.venv/bin/python -m pytest tests/unit/test_smoke.py -v

# Benchmarks
.venv/bin/python tests/integration/longmemeval_eval.py --out /tmp/lme_run.json
.venv/bin/python tests/integration/locomo_eval.py --assignment-threshold 0.65 --out /tmp/locomo_run.json

# Format
.venv/bin/python -m black --line-length 100 slowave/
.venv/bin/python -m isort --profile black slowave/
```

## Architecture

The system has two layers:

### Latent layer (`slowave/latent/`) — geometry only, no language

- **EpisodicStore** — append-only event memories. Embeddings + salience + timestamp, stored in SQLite + FAISS.
- **SemanticStore** — prototype clusters at two scales: *fine* (CA3, threshold 0.85) for exact retrieval, *coarse* (CA1, threshold 0.55) for pattern completion. Agreement between scales is a confidence signal.
- **ReplayEngine** — offline consolidation worker: samples episodes → clusters prototypes → salience decay → trains TransitionModel.
- **RetrievalPipeline** — multi-mechanism recall: cosine seed → predictive seed (TransitionModel) → spreading activation over prototype graph → temporal bias.
- **GraphManager** — inter-prototype co-activation edges. Self-supervised replay reinforces missed bridges.
- **TransitionModel** — graph-based successor-representation model predicting next-state embedding from learned prototype transition weights (Hebbian co-occurrence). Also provides prediction-error surprise signal for episode salience.
- **LatentSchemaBuilder** (`latent/schema.py`) — schemas as pure prototype geometry: centroid + SVD principal axes + temporal anchor + confidence. No LLM.

### Symbolic layer (`slowave/symbolic/`) — language interface

- **RawLog** — raw event storage (user/assistant turns), keyed by session_id.
- **EpisodeTextStore** — human-readable episode summaries linked to latent episodes.
- **SchemaStore** — typed claims with facets, status (active/needs_review/contradicted/superseded), salience, confidence, supporting episode links.
- **TextEncoder** (`encoder.py`) — sentence-transformers wrapper (`all-MiniLM-L6-v2`, dim=384), lazy-loaded.

### Engine & storage

- **SlowaveEngine** (`core/engine.py`) — facade wiring latent + symbolic + storage. Session lifecycle: `session_start` → `event_append` (encode+store, ~1ms) → `session_end` (form episodes, non-blocking) → background worker (replay → prototypes → schemas).
- **SQLiteDB** (`storage/sqlite_db.py`, `storage/schema.sql`) — single-file SQLite; all state is durable here. Schema auto-migrates on `init_schema`.
- **Config** (`core/config.py`) — embedding dim and per-subsystem configs. No LLM fields.

## Data flow

```
event_append → raw log + FAISS (1ms, no LLM)
session_end  → micro/macro episodes from raw events (fast)
worker       → replay → prototypes (fine+coarse) → latent schemas → graph reinforcement
recall       → cosine + predictive + spreading-activation + temporal → ranked episodes/schemas
```

Consolidation is fully decoupled from ingest — the agent never waits on it.

## Key environment variables

```
SLOWAVE_DB           Default: ~/.slowave/slowave.db
```

## Testing strategy

- **Unit** (`tests/unit/test_smoke.py`): import check + synthetic latent end-to-end. No external deps.
- **Integration** (`tests/integration/`): LongMemEval, LoCoMo, DMR, StaleMemory. All support ablation flags (`--no-multi-scale`, `--no-transition`, `--no-consolidate`). See `docs/benchmarks.md` for reproducing all numbers.
- **Temporal** (`tests/temporal_eval/`): 6 internal scenarios (chain, decay, reinforcement, coactivation, completion, supersession) for validating individual mechanism correctness.

## Slowave memory usage (this repo)

This repo has Slowave MCP configured. When working here use the 5-verb cognitive cycle:

> **Scope rule:** Always set `scope="project:slowave"` for all calls in this repo.
> Omitting scope causes memories from unrelated projects to bleed into retrieval results.

1. **Task start**: `slowave_activate(query="<task>", scope="project:slowave", goal="<3-6 word verb-noun phrase>", task_type="<category>")` → stores `retrieval_id` and `session_id`.
2. **Durable facts**: `slowave_remember(content, type, scope="project:slowave")` — for decisions, lessons, constraints, architectural facts that persist across sessions. Do NOT store ephemeral state (current PR, in-progress bug, temp workarounds) — that belongs in events, encoded automatically.
3. **Mid-task lookup**: `slowave_recall(query, scope="project:slowave")` — when you need specific historical context not surfaced by activate. Always pass scope to avoid cross-project bleed.
4. **Feedback** *(mandatory after using memories)*: `slowave_reinforce(retrieval_id, feedback, outcome, used_memory_ids=[...])`. Feedback is NOT auto-fired; skipping it means slowave cannot learn.
5. **Task end**: `slowave_commit(scope="project:slowave", outcome="success|partial|failure")` — closes session, forms episodes.
