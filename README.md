# Slowave

**Brain-inspired long-term memory for AI agents and desktop AI chats.**

[![PyPI](https://img.shields.io/pypi/v/slowave?color=2f6f4e)](https://pypi.org/project/slowave/)
[![Python](https://img.shields.io/pypi/pyversions/slowave?color=4c6f91)](https://pypi.org/project/slowave/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Slowave plugs into **Claude Code**, **Cline**, and **Claude Desktop** through MCP, giving them a shared local memory that accumulates, consolidates, adapts, and recalls across sessions.

> **Core idea**
> Language is not the memory system; language is one interface to it. Slowave stores text once as embeddings, then lets memory evolve through geometry, time, salience, replay, and activation.

## At a glance

| What you get | Why it matters |
|---|---|
| **No LLM in the core memory loop** | No API key, cloud extraction step, or per-query model call. |
| **Local CPU inference** | BAAI/bge-small-en-v1.5 embeddings, SQLite, FAISS, deterministic geometry. |
| **Brain-inspired consolidation** | Raw events become episodes; episodes replay into prototypes; prototypes become latent schemas. |
| **Active recall** | Retrieved memories are reinforced, so recall changes the memory system. |
| **Time-aware memory** | Salience, decay, temporal anchors, supersession, and contradiction handling keep memory current. |
| **Gated working memory** | `slowave_context` injects a compact, cue-relevant brief instead of dumping history into the prompt. |

```text
events ──session end──▶ episodes ──replay──▶ prototypes ──consolidation──▶ schemas
  ▲                                                                           │
  └──────────────────────────── recall reinforces useful memory ◀─────────────┘
```

## What Slowave is for

Slowave is a local long-term memory substrate for tools that otherwise forget between sessions. It can remember:

| Memory type | Examples |
|---|---|
| Project context | conventions, architectural decisions, recurring commands |
| Personal context | preferences, communication style, planning patterns |
| Work history | debugging sessions, lessons learned, open questions |
| Constraints | warnings, artifacts, superseded decisions, active assumptions |
| Desktop chat context | non-coding conversations that should persist locally |

It is intentionally not just a RAG layer. Existing memory systems usually retrieve stored text or ask an LLM to rewrite memories. Slowave treats memory as a living system: sessions create episodes, replay distills patterns, time changes salience, contradiction updates beliefs, and recall reinforces what was useful.

## Install in minutes

Installing Slowave gives you two commands:

| Command | Purpose |
|---|---|
| `slowave` | CLI, dashboard, manual recall/debugging. |
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

Default storage is `~/.slowave/slowave.db`. No Ollama, OpenRouter, or other LLM backend is required for the default brain-only path.

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
| [docs/install.md](docs/install.md) | Install, MCP setup, prompt/rules injection, verification |
| [docs/architecture.md](docs/architecture.md) | Brain-inspired mechanisms, data flow, storage, recall, consolidation |
| [docs/design.md](docs/design.md) | Why the LLM path was removed from the memory loop |
| [docs/dashboard.md](docs/dashboard.md) | Local dashboard guide |
| [docs/cli.md](docs/cli.md) | CLI quickstart and command reference |

## Benchmarks

Public retrieval/RAG-style benchmarks are useful regression tests, but they do not measure every Slowave feature. They mostly test fact recovery, not long-term accumulation, distillation, time-aware adaptation, or recall-driven memory reinforcement.

| Benchmark | Cosine RAG | **Slowave** | Δ | Mem0 SOTA |
|---|---:|---:|---:|---:|
| LongMemEval (500q) | 60.0% | **70.0%** | +10pp | 94.4% |
| LoCoMo (1986q) | 68.0% | **75.5%** | +7.5pp | 92.5% |

**Brain-only path:** `$0/query` · `~10ms recall` · `no API` · `data stays on device`

The gap to Mem0 is structurally about categories that reward LLM extraction/meta-cognition by construction, not just retrieval. See [docs/design.md](docs/design.md) for the design rationale.

## License

MIT.
