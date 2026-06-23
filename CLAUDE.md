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

# WikiScenarios (18 ablation scenarios, no external data)
.venv/bin/python tests/wiki_scenarios/run_wiki_scenarios.py

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
- **TextEncoder** (`encoder.py`) — sentence-transformers wrapper (`all-MiniLM-L6-v2`, dim=384), lazy-loaded.

### Core modules (`slowave/core/`) — procedural memory, feedback, context gating, supersession

- **ProceduralMemoryStore** (`procedural.py`) — deterministic scope-aware procedural memory. Matching is lexical/metadata scoring + feedback-updated confidence, no LLM. Statuses: candidate → active → deprecated. Supports cross-scope transfer with affinity scoring.
- **ProceduralEnforcement** (`procedural_enforcement.py`) — Tier 1 enforcement: step-coverage matching via cosine similarity between procedure steps and session remember:* events. Called from session_end to auto-record feedback.
- **ProceduralEnrichment** (`procedural_enrichment.py`) — Tier 2 enrichment: extracts and deduplicates procedure steps from successful sessions to replace generic placeholder steps.
- **SupersessionManifold** (`supersession_manifold.py`) — SVD1-based latent supersession direction. Computes a single axis in embedding space that best explains concrete value-substitution supersession across 7 domains. Used to flag `needs_review` for candidate supersessions.
- **FeedbackSystem** (`feedback.py`) — brain-inspired numeric learning signals derived from symbolic feedback labels (useful/irrelevant/stale/wrong/missing). Maps labels to valence, context_fit, truth_error, temporal_error, and salience/confidence deltas.
- **WorkingMemoryGate** (`context.py`) — gating system for admitting long-term memories into an agent's working context. Activation-based selection with token budget enforcement.
- **Scope helpers** (`scope.py`) — scope normalization: `project:slowave` → kind=`project`, value=`slowave`.
- **Paths** (`paths.py`) — `default_db_path()` resolves `SLOWAVE_DB` env or `~/.slowave/slowave.db`.

### Engine & storage

- **SlowaveEngine** (`core/engine.py`) — facade wiring latent + symbolic + storage + procedural. Session lifecycle, remember/recall, consolidation, feedback, stats. Key methods: `session_start`, `session_end`, `event_append`, `remember`, `recall`, `context`, `retrieval_feedback`, `consolidate_once`, `promote_procedure_candidates_from_feedback`.
- **SQLiteDB** (`storage/sqlite_db.py`, `storage/schema.sql`) — single-file SQLite; all state is durable here. Schema auto-migrates on `init_schema`.
- **Config** (`core/config.py`) — embedding dim and per-subsystem configs. Supports `disable_encoder` for cheap encoder-free engine instances.

### MCP servers (`slowave/mcp/`)

- **server.py** — stdio MCP server (subprocess). Entry: `slowave-mcp` or `python -m slowave.mcp.server`.
- **http_server.py** — HTTP MCP daemon (streamable-HTTP, uvicorn+starlette). Entry: `slowave-mcp-http` or `slowave serve start`. Port 8766 by default, single-instance via PID file.
- **daemon.py** — PID file lifecycle for the HTTP daemon (`write_pid`, `remove_pid`, `is_running`, `stop_daemon`).
- **tools.py** — shared `register_tools(mcp, build_engine)` attaches all 6 tools to any FastMCP instance (both stdio and HTTP).
- **compact.py** — `CompactSchema` for token-efficient MCP responses (~150-200 tokens vs ~500 for full schemas).
- **session_reaper.py** — background thread that closes sessions idle longer than `SLOWAVE_SESSION_IDLE_TIMEOUT` (default 3600s).
- **session_resolver.py** — per-scope implicit session resolver so `remember(session_id=None)` finds the session opened by `activate()`.

### Dashboard (`slowave/dashboard/`)

- **app.py** — local web UI served via `slowave dashboard`. Zero deps: stdlib HTTP server + SQLite read APIs + embedded HTML/JS/CSS. Default port 8765.

## Data flow

```
event_append → raw log + FAISS (1ms, no LLM)
session_end  → micro/macro episodes from raw events (fast) → procedural enforcement
worker       → replay → prototypes (fine+coarse) → latent schemas → graph reinforcement
               → promote procedure candidates → supersession detection
recall       → cosine + predictive + spreading-activation + temporal → ranked episodes/schemas/procedures
```

Consolidation is fully decoupled from ingest — the agent never waits on it.

## MCP tools (the 5-verb cognitive cycle)

The MCP server exposes exactly 6 tools. Old tools (`slowave_context`, `slowave_session_start`, `slowave_session_end`, `slowave_event`, `slowave_retrieval_feedback`, `slowave_context_feedback`) have been **deleted**.

| Tool | Purpose |
|------|---------|
| `slowave_activate` | Prime working memory; opens implicit session |
| `slowave_remember` | Encode a durable typed claim (fact, decision, lesson, etc.) |
| `slowave_recall` | Semantic retrieval mid-task |
| `slowave_reinforce` | Strengthen/suppress memories via feedback |
| `slowave_commit` | Close the task; form episodes |
| `slowave_stats` | Return system counts |

## Key environment variables

```
SLOWAVE_DB                       Default: ~/.slowave/slowave.db
SLOWAVE_MCP_IDLE_TIMEOUT         Process watchdog idle timeout (default 1800s for stdio, 0=disabled for HTTP)
SLOWAVE_SESSION_IDLE_TIMEOUT     Session-level idle reaper timeout (default 3600s; 0=disabled)
SLOWAVE_DAEMON_PID               PID file path for HTTP daemon (default ~/.slowave/daemon.pid)
SLOWAVE_MCP_HOST                 HTTP daemon bind host (default 127.0.0.1)
SLOWAVE_MCP_HTTP_PORT            HTTP daemon bind port (default 8766)
KMP_DUPLICATE_LIB_OK             Set to TRUE for macOS (faiss + ONNX coexistence)
OMP_NUM_THREADS                  Set to 1 (prevent thread oversubscription)
TOKENIZERS_PARALLELISM           Set to false (prevent deadlocks in HF tokenizers)
```

## CLI commands

All commands accept `--db` and `--json` flags (inherited from the top-level group).

| Command | Description |
|---------|-------------|
| `slowave session` | Start/end sessions |
| `slowave event` | Append an event to an active session |
| `slowave remember` | Store a durable fact |
| `slowave recall` | Retrieve memories by semantic query |
| `slowave context` | Get working-memory context for an agent prompt |
| `slowave show` | Show a specific memory/schema by reference |
| `slowave schema` | List schemas (supports `--needs-review` filter) |
| `slowave stats` | System counts |
| `slowave status` | Health check (doctor-lite) |
| `slowave dashboard` | Launch local web UI (port 8765) |
| `slowave doctor` | Full system diagnostic |
| `slowave setup` | Install/configure MCP servers across clients |
| `slowave uninstall` | Remove Slowave configuration |
| `slowave serve start/stop/status/restart` | HTTP MCP daemon lifecycle |
| `slowave backup` | Daily SQLite backup with gzip rotation |
| `slowave dedup-schemas` | Deduplicate schemas (supports `--apply`) |
| `slowave consolidate` | Run one consolidation pass |
| `slowave worker` | Run the consolidation worker in a loop |

## Testing strategy

- **Unit** (`tests/unit/test_smoke.py`): import check + synthetic latent end-to-end. No external deps.
- **Procedural unit** (`tests/unit/test_procedural_enforcement_tier1.py`, `tests/unit/test_procedural_generalization.py`): procedural memory matching and enrichment tests.
- **Supersession** (`tests/unit/test_supersession_geometry.py`): supersession detection geometry tests.
- **Integration** (`tests/integration/`): LongMemEval, LoCoMo, DMR, StaleMemory. All support ablation flags (`--no-multi-scale`, `--no-transition`, `--no-consolidate`).
- **WikiScenarios** (`tests/wiki_scenarios/`): 18 ablation scenarios testing supersession, consolidation, graph, salience effects across factual and preference domains. Run via `tests/wiki_scenarios/run_wiki_scenarios.py`.
- **Temporal** (`tests/temporal_eval/`): 6 internal scenarios (chain, decay, reinforcement, coactivation, completion, supersession) for validating individual mechanism correctness.

## Python imports

To avoid loading FAISS / ONNX / sentence-transformers at import time, import specific classes instead of `import slowave`:

```python
from slowave.core.engine import SlowaveEngine
from slowave.core.config import SlowaveConfig
```

The MCP server sets `KMP_DUPLICATE_LIB_OK=TRUE`, `OMP_NUM_THREADS=1`, `TOKENIZERS_PARALLELISM=false` at import time to prevent runtime crashes.

## Slowave memory usage (this repo)

This repo has Slowave MCP configured. Use the 5-verb cognitive cycle:

> **Scope rule:** Always set `project="slowave"` for all calls in this repo.
> Omitting project causes memories from unrelated projects to bleed into retrieval results.

**Lifecycle — mandatory:**

1. **Task start**: `slowave_activate(query="<verbatim task>", goal="<3-6 word verb-noun>", scope="project:slowave")` → returns `retrieval_id` and `session_id`.
2. **During work**: call `slowave_remember(content, type, scope="project:slowave")` for durable facts (decisions, constraints, lessons, warnings). Types: `fact|preference|decision|constraint|procedure|task|open_question|warning|lesson|artifact`.
3. **Mid-task lookup**: `slowave_recall(query)` when you need specific historical context.
4. **After using memories**: `slowave_reinforce(retrieval_id=<id>, feedback="useful|partially_useful|irrelevant|stale|wrong|missing|too_much_context", outcome="success|partial|failure|unknown", used_memory_ids=[...])`.
5. **Task end**: `slowave_commit(scope="project:slowave", outcome="success|partial|failure")` — closes session, forms episodes.

**Anti-patterns to avoid:**
- Calling only `slowave_activate` without `slowave_commit` at the end.
- Using `slowave_recall` for default task priming (use `slowave_activate` instead).
- Forgetting to call `slowave_remember` for durable facts that should survive independently.
- Skipping `slowave_reinforce` after using retrieved memories (breaks the learning loop).
- Skipping `slowave_commit` at task close (session stays open until idle reaper fires).
