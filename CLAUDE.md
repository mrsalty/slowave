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

# Format
.venv/bin/python -m black --line-length 100 slowave/
.venv/bin/python -m isort --profile black slowave/

# Run all fast unit tests (skip slow, benchmark, requires_model)
.venv/bin/python -m pytest tests/ -m "not slow and not benchmark and not requires_model and not requires_faiss" -v

# Smoke test only
.venv/bin/python -m pytest tests/unit/test_smoke.py -v

# FAISS integration tests
.venv/bin/python -m pytest tests/ -m "requires_faiss" -v

# Benchmarks
.venv/bin/python tests/integration/longmemeval_eval.py --out /tmp/lme_run.json
.venv/bin/python tests/integration/locomo_eval.py --assignment-threshold 0.65 --out /tmp/locomo_run.json
```

## Architecture

The system has two core layers plus supporting infrastructure:

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
- **SchemaStore** — typed claims with facets, status (active/needs_review/contradicted/superseded/archived), salience, confidence, supporting episode links.
- **TextEncoder** (`encoder.py`) — sentence-transformers wrapper (all-MiniLM-L6-v2, dim=384), lazy-loaded.

### Core modules (`slowave/core/`) — procedural memory, feedback, context gating, supersession

- **ProceduralMemoryStore** (`procedural.py`) — deterministic scope-aware procedural memory. Matching is lexical/metadata scoring + feedback-updated confidence, no LLM. Statuses: candidate → active → deprecated.
  - Procedural behavior is implicit via schemas + prototypes + TransitionModel

- **SupersessionManifold** (`supersession_manifold.py`) — SVD1-based latent supersession direction across 7 domains.
- **FeedbackSystem** (`feedback.py`) — numeric learning signals from symbolic labels (useful/irrelevant/stale/wrong/missing).
- **WorkingMemoryGate** (`context.py`) — activation-based selection with token budget enforcement for working context.
- **Scope helpers** (`scope.py`) — scope normalization (kind + value).
- **Paths** (`paths.py`) — `default_db_path()` resolves SLOWAVE_DB env or ~/.slowave/slowave.db.

### Engine & storage

- **SlowaveEngine** (`core/engine.py`) — facade wiring latent + symbolic + storage + procedural. Session lifecycle, remember/recall, consolidation, feedback, stats, consolidation.
- **SQLiteDB** (`storage/sqlite_db.py`, `storage/schema.sql`) — single-file SQLite; all state durable here. Auto-migrates on init.
- **Config** (`core/config.py`) — embedding dim and per-subsystem configs. Supports `disable_encoder` for cheap encoder-free instances.

### MCP servers (`slowave/mcp/`)

- **server.py** — stdio MCP server (subprocess). Entry: `slowave-mcp`.
- **http_server.py** — HTTP MCP daemon (streamable-HTTP, uvicorn+starlette). Port 8766, single-instance via PID file.
- **daemon.py** — PID file lifecycle (write/remove/is_running/stop).
- **tools.py** — shared `register_tools()` for both stdio and HTTP servers.
- **compact.py** — CompactSchema for token-efficient responses (~150-200 tokens).
- **session_reaper.py** — background thread closing sessions idle > SLOWAVE_SESSION_IDLE_TIMEOUT (default 3600s).
- **session_resolver.py** — per-scope implicit session resolver.

### Dashboard (`slowave/dashboard/app.py`)

Local web UI served via `slowave dashboard`. Zero deps: stdlib HTTP server + SQLite + embedded HTML/JS. Port 8765.

## Data flow

```
event_append → raw log + FAISS (1ms, no LLM)
session_end  → micro/macro episodes → procedural enforcement
worker       → replay → prototypes → latent schemas → graph reinforcement
               → promote procedure candidates → supersession detection
recall       → cosine + predictive + spreading-activation + temporal → ranked episodes/schemas
```

Consolidation is fully decoupled from ingest.

## MCP tools (5-verb cognitive cycle)

Old tools (slowave_context, slowave_session_start/end, slowave_event, slowave_retrieval_feedback, slowave_context_feedback) are **deleted**. Exposed tools:

| Tool | Purpose |
|------|---------|
| slowave_activate | Prime working memory; opens implicit session |
| slowave_remember | Encode a durable typed claim |
| slowave_recall | Semantic retrieval mid-task |
| slowave_reinforce | Strengthen/suppress memories via feedback |
| slowave_commit | Close the task; form episodes |
| slowave_stats | Return system counts |

## Key environment variables

```
SLOWAVE_DB                       Default: ~/.slowave/slowave.db
SLOWAVE_MCP_IDLE_TIMEOUT         Process idle timeout (1800s stdio, 0=disabled HTTP)
SLOWAVE_SESSION_IDLE_TIMEOUT     Session idle reaper timeout (3600s default)
SLOWAVE_DAEMON_PID               HTTP daemon PID file path
SLOWAVE_MCP_HOST                 HTTP daemon bind host (127.0.0.1)
SLOWAVE_MCP_HTTP_PORT            HTTP daemon bind port (8766)
KMP_DUPLICATE_LIB_OK             Set TRUE on macOS for faiss + ONNX
OMP_NUM_THREADS                  Set to 1
TOKENIZERS_PARALLELISM           Set to false
```

## Testing strategy

- **Unit** (`tests/unit/test_smoke.py`): import check + synthetic latent end-to-end.
- **Procedural** (`tests/unit/test_procedural_enforcement_tier1.py`, `test_procedural_generalization.py`)
- **Supersession** (`tests/unit/test_supersession_geometry.py`)
- **Integration** (`tests/integration/`): LongMemEval, LoCoMo, DMR, StaleMemory. All support ablation flags.
- **Temporal** (`tests/temporal_eval/`): 6 scenarios (chain, decay, reinforcement, coactivation, completion, supersession).

## Python imports

Avoid loading FAISS/ONNX at import time — import specific classes:

```python
from slowave.core.engine import SlowaveEngine
from slowave.core.config import SlowaveConfig
```

## Slowave memory usage (this repo)

This repo has Slowave MCP configured. Use the 5-verb cognitive cycle:

> **Scope rule:** Always set `scope="project:slowave"` for all calls.

**Lifecycle:**
1. **Task start**: `slowave_activate(query, goal="<3-6 word verb-noun>", scope="project:slowave")`
2. **During work**: `slowave_remember(content, type, scope="project:slowave")` for durable facts
3. **Mid-task lookup**: `slowave_recall(query)`
4. **After using memories**: `slowave_reinforce(retrieval_id, feedback, outcome, used_memory_ids=[...])`
5. **Task end**: `slowave_commit(scope="project:slowave", outcome="success|partial|failure")`

## Behavioral guidelines

These rules reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/kaborojeff/status/1935181458847178833) on LLM coding pitfalls. They bias toward caution over speed — for trivial tasks, use judgment.

### 1. Think Before Coding
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First
- Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes
- Touch only what you must. Clean up only your own mess.
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.
- Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution
- Define verifiable success criteria before coding.
- Transform vague tasks into testable goals:
  - "Add validation" → "Write tests for invalid inputs, then make them pass"
  - "Fix the bug" → "Write a test that reproduces it, then make it pass"
  - "Refactor X" → "Ensure tests pass before and after"
- For multi-step tasks, state a brief plan with verification steps.
- Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

**Signs these are working**: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, clarifying questions come before implementation rather than after mistakes.
