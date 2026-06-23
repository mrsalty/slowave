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

This repo has Slowave MCP configured. Use the session-event-context lifecycle:

> **Scope rule:** Always set `project="slowave"` for all calls in this repo.
> Omitting project causes memories from unrelated projects to bleed into retrieval results.

**Session lifecycle — mandatory:**

1. **Task start**: `slowave_session_start(agent="cline-tui", project="slowave")` → store returned `session_id`.
2. **Log user request**: `slowave_event(session_id, "user_message", "<self-contained summary>")`.
3. **Prime context**: `slowave_context(project="slowave", limit=8, query="<task>", application="cline-tui", topics=[], entities=["Slowave"], mode="default")`.
4. **During work**: call `slowave_event(session_id, type, content)` for every meaningful exchange, decision, tool result, or error. Types: `user_message`, `assistant_message`, `tool_call`, `tool_result`, `decision`, `discovery`, `error`, `task_complete`, `task_failed`.
5. **Task end**: `slowave_event(session_id, "assistant_message", "<summary>")` then `slowave_session_end(session_id)`.

**Durable facts** (facts that survive independently): `slowave_remember(content, type, project="slowave")` — for long-lived preferences, decisions, constraints, lessons, procedures, warnings, tasks, or open questions. Types: `fact`, `preference`, `decision`, `constraint`, `procedure`, `task`, `open_question`, `warning`, `lesson`, `artifact`.

**Broad memory search** (investigation, evidence drill-through): `slowave_recall(query, top_k=5, evidence=true)` — intentionally broad, may return cross-project summaries. Do NOT use for default scoped context; use `slowave_context` instead.

**Anti-patterns to avoid:**
- Calling only `slowave_session_start` + `slowave_session_end` with no events between.
- Batching all events into one giant call at the end.
- Using `slowave_recall` for default task priming (use `slowave_context` instead).
- Forgetting to log `tool_result` events when tools reveal new information.
