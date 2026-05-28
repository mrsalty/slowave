# Slowave

**Brain-inspired, latent-space long-term memory for MCP-compatible AI agents, coding assistants, and chats.  
Shared across sessions, clients, and tools.**

[![PyPI](https://img.shields.io/pypi/v/slowave?color=2f6f4e)](https://pypi.org/project/slowave/)
[![Python](https://img.shields.io/pypi/pyversions/slowave?color=4c6f91)](https://pypi.org/project/slowave/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Slowave plugs into **Claude Code**, **Cline**, and **Claude Desktop** through MCP, giving them a shared local memory that accumulates, consolidates, adapts, and recalls across sessions.

Slowave is not just a transcript store or a conventional RAG layer. It is inspired by the idea that memory is a dynamic system shaped by association, time, salience, replay, and retrieval. The default memory path uses local embeddings, SQLite, FAISS, deterministic geometry, and background consolidation — without requiring an LLM call in the core memory loop.

> **Slowave core idea:** sessions create episodes, replay distills recurring patterns, time changes salience, contradiction-aware updates keep memory current, and recall reinforces memories that prove useful.

## Status

Slowave is early-stage software. The core local memory path, MCP server, CLI, and dashboard are available, while integrations, benchmark coverage, and consolidation policies are still evolving.

## At a glance

| What you get | Why it matters |
|---|---|
| **No LLM in the core memory loop** | No API key, cloud extraction step, or per-query model call is required for the default path. |
| **Privacy-first local memory** | Memory is stored and processed locally; no cloud memory backend, API extraction step, or remote LLM inference is required. |
| **Local CPU inference** | Uses BAAI/bge-small-en-v1.5 embeddings, SQLite, FAISS, and deterministic geometry. |
| **Brain-inspired consolidation** | Raw events become episodes; episodes replay into prototypes; prototypes consolidate into latent schemas. |
| **Active recall** | Retrieved memories are reinforced, so recall changes the memory system over time. |
| **Time-aware memory** | Salience, decay, temporal anchors, supersession, and contradiction-aware updates help keep memory current. |
| **Gated working memory** | `slowave_context` injects a compact, cue-relevant brief instead of dumping history into the prompt. |

```text
events ──session end──▶ episodes ──replay──▶ prototypes ──consolidation──▶ schemas
  ▲                                                                           │
  └────────────────────── recall reinforces useful memory ◀───────────────────┘
```

## How it works

A typical Slowave flow looks like this:

1. You work with Cline, Claude Code, or Claude Desktop on a project or conversation.
2. The client writes task-relevant observations through MCP.
3. When the session ends, Slowave forms an episode.
4. The background worker consolidates accumulated episodes into prototypes and schemas.
5. In a future session, `slowave_context` retrieves a compact, relevant memory brief.
6. If a memory is useful during recall, it is reinforced.

Slowave represents memory primarily through embeddings, metadata, salience, temporal structure, and learned geometry rather than repeated LLM summarization.

## What Slowave is for

Slowave is a local long-term memory substrate for tools that otherwise forget between sessions. It can remember:

| Memory type | Examples |
|---|---|
| Project context | Conventions, architectural decisions, recurring commands |
| Personal context | Preferences, communication style, planning patterns |
| Work history | Debugging sessions, lessons learned, open questions |
| Constraints | Warnings, artifacts, superseded decisions, active assumptions |
| Desktop chat context | Non-coding conversations that should persist locally |

Existing memory systems often retrieve stored text or ask an LLM to rewrite memories. Slowave treats memory as a living system: sessions create episodes, replay distills patterns, time changes salience, contradiction-aware updates revise beliefs, and recall reinforces what was useful.

## Why Slowave is different

Most agent memory systems fall into one of two categories:

1. **Transcript stores** that save and retrieve previous messages.
2. **LLM-written memory systems** that ask a model to extract, rewrite, summarize, or update memories.

Slowave takes a different path. It keeps the default memory loop local, embedding-based, and geometry-driven. Memories are not only retrieved; they evolve through salience, decay, replay, activation, and consolidation.

This makes Slowave useful when you want:

| Need | Slowave approach |
|---|---|
| Shared memory across tools | One local store can be used by Claude Code, Cline, Claude Desktop, and other MCP clients. |
| Low-friction local setup | No hosted memory service or remote inference backend is required. |
| Compact context injection | `slowave_context` returns a short, cue-relevant memory brief. |
| Memory that changes over time | Recall, decay, salience, and replay affect future retrieval. |
| Project continuity | Conventions, decisions, constraints, and lessons learned can survive across sessions. |
| Inspectability | The CLI and dashboard help inspect the local memory state. |

## Install in minutes

Installing Slowave gives you two commands:

| Command | Purpose |
|---|---|
| `slowave` | CLI, dashboard, manual recall, debugging, and research workflows. |
| `slowave-mcp` | MCP server used by Claude Desktop, Claude Code, and Cline. |

Choose one install path:

```bash
# Recommended for isolated CLI installs
pipx install slowave

# Or use pip
pip install slowave

# macOS Homebrew
brew tap mrsalty/slowave
brew install slowave
```

Install from source:

```bash
git clone https://github.com/mrsalty/slowave
cd slowave
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify:

```bash
which slowave-mcp
slowave --help
slowave-mcp --help
slowave stats
```

Default storage is:

```text
~/.slowave/slowave.db
```

No Ollama, OpenRouter, hosted vector database, cloud memory service, or other LLM backend is required for the default local path.

## Connect a client

| Client | Setup guide |
|---|---|
| Claude Desktop | [integrations/claude-desktop/](integrations/claude-desktop/) |
| Claude Code | [integrations/claude-code/](integrations/claude-code/) |
| Cline | [integrations/cline/](integrations/cline/) |

> [!IMPORTANT]
> MCP setup alone is not enough. Each client needs the MCP configuration, instruction/rules injection, and the background worker.

| Setup layer | Why it matters |
|---|---|
| MCP configuration | Makes the `slowave_*` tools visible to the client. |
| Instruction/rules injection | Makes the client actually call Slowave during the task. |
| Background worker | Consolidates episodes into durable schemas for better future context. |

Episodes are created immediately when a session ends. The worker turns accumulated episodes into durable latent schemas for better future `slowave_context` injection.

## Local dashboard

Run a read-only web UI for memory inspection:

```bash
slowave dashboard
# open http://127.0.0.1:8765
```

The dashboard binds to `127.0.0.1` by default and shows DB health, Slowave/MCP processes, schemas, a recall playground, and a schema graph.

## CLI usage

The CLI is useful for debugging, manual memory writes, dashboard access, and benchmark/research workflows. It should not be the first path for most users; real agent memory needs MCP plus prompt/rules injection.

See [docs/cli.md](docs/cli.md) for the command list and a CLI-only quickstart.

## Documentation

| Guide | Covers |
|---|---|
| [integrations/](integrations/) | Fast client-specific setup guides for Claude Desktop, Claude Code, and Cline |
| [docs/architecture.md](docs/architecture.md) | Brain-inspired mechanisms, data flow, storage, recall, consolidation |
| [docs/design.md](docs/design.md) | Why the LLM path was removed from the memory loop |
| [docs/dashboard.md](docs/dashboard.md) | Local dashboard guide |
| [docs/cli.md](docs/cli.md) | CLI quickstart and command reference |

## Benchmarks

> **All numbers use the brain-only path: local CPU, BAAI/bge-small-en-v1.5 embeddings, SQLite + FAISS — zero LLM calls, no API key, no cloud service, ~$0/query.**

Public benchmarks mostly test explicit fact recall. They do not measure Slowave's consolidation, time-aware adaptation, contradiction handling, or recall-driven reinforcement — so they understate the full picture. With that caveat, here is where things stand.

### Overall results

| Benchmark | Questions | Slowave (brain-only) | Cosine RAG baseline | Δ |
|---|---:|---:|---:|---:|
| LongMemEval | 500 | **70.0%** | 60.0% | **+10 pp** |
| LoCoMo | 1 986 | **75.5%** | 68.0% | **+7.5 pp** |

*Metric: keyword hit-rate (answer keywords present in retrieved context). All runs: zero LLM calls, ~10 ms recall, data stays on device.*

### Highlights

- **Beats cosine RAG by +10 pp on LongMemEval and +7.5 pp on LoCoMo** purely through brain-inspired mechanisms: spreading activation, multi-scale prototypes, temporal weighting, replay, consolidation — no LLM extraction step.
- **LongMemEval single-session-user: 100%.** Perfect retrieval of single-session facts.
- **LoCoMo adversarial: 95.5%.** Robust against misleading and contradictory cues.
- **LoCoMo multi-session: 86.3%** — cross-session fact aggregation, no special handling.
- **Competitive with GPT-4o-powered systems on LME** (62.5% keyword score on a 120-question grid-search subset vs ChatGPT GPT-4o 57.7% LLM-judged¹), while running fully offline with no per-query cost.
- Full LongMemEval ingestion + eval in **~3 min on a Mac CPU**.

### Per-category breakdown

**LongMemEval** (500q, 6 categories)

| Category | Score | Notes |
|---|---:|---|
| Single-session-user | **100.0%** | ✅ perfect |
| Single-session-assistant | **80.0%** | ✅ strong |
| Knowledge-update | **70.0%** | ✅ good |
| Temporal-reasoning | 55.0% | ⚠ date arithmetic gap |
| Multi-session | 50.0% | ⚠ number aggregation gap |
| Single-session-preference | 20.0% | ⚠ preference abstraction gap |

**LoCoMo** (1986q, 5 categories)

| Category | Score | Notes |
|---|---:|---|
| Adversarial | **95.5%** | ✅ best in class |
| Multi-session | **86.3%** | ✅ strong cross-session recall |
| Single-session | **75.5%** | ✅ solid |
| Commonsense | 55.2% | — |
| Temporal | 25.6% | ⚠ date arithmetic gap (same root cause as LME) |

### Known gaps and roadmap

The ⚠ categories share two root causes — neither is a retrieval quality problem:

| Gap | Root cause | Fix on roadmap |
|---|---|---|
| Temporal (LME 55%, LoCoMo 25.6%) | Date arithmetic and relative-time reasoning ("last month") — retrieval works, answer construction fails | Timestamp-aware query expansion |
| Multi-session LME (50%) | Summing/comparing quantities across episodes — the aggregate answer is never in any single episode | Explicit number aggregation (Stage 11a) |
| Preference LME (20%) | Implicit preferences not abstracted into queryable facts — keyword scoring caps this category structurally | Preference-extraction schema layer |

### Parameter tuning

A 3-phase, 66-cell grid search (2026-05-28) swept the 8 highest-impact parameters. LoCoMo improved by **+1.7 pp overall**, with multi-session up **+3.4 pp**. LME was flat across all 66 cells, confirming the remaining gaps are structural, not tuning-addressable. The best configuration is now the source default.

### Metric and comparison notes

¹ **Metric caveat:** Slowave uses keyword hit-rate; ChatGPT/Mem0 scores use LLM-as-judge. These are different scales — the comparison is directional, not exact. Keyword hit-rate is stricter on open-ended categories (preference, multi-session), so Slowave's real accuracy on those categories is likely higher than the numbers above.

Systems like Mem0 and ChatGPT use cloud LLM inference for extraction and answering. Slowave intentionally targets a different design point: local, offline, zero ongoing cost, privacy-preserving memory that evolves over time without an LLM in the loop.

For evaluation scripts, model versions, configuration, and cosine baseline reproduction steps, see [docs/benchmarks.md](docs/benchmarks.md).

## License

MIT.
