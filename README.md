# Slowave

**One private memory layer across your AI clients.**

[![PyPI](https://img.shields.io/pypi/v/slowave?color=2f6f4e)](https://pypi.org/project/slowave/)
[![Python](https://img.shields.io/badge/python-3.11%2B-4c6f91)](https://pypi.org/project/slowave/)
[![PyPI Status](https://img.shields.io/pypi/status/slowave?color=orange)](https://pypi.org/project/slowave/)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE)
[![Downloads](https://static.pepy.tech/badge/slowave)](https://pepy.tech/project/slowave)

Slowave gives every MCP-compatible tool a shared, persistent memory. No LLM in the loop, fully local, $0 per query.

## Demo

See Slowave in action:

![Demo](img/demo.gif)

> Cold start discovers project facts. Rule stored in Claude. Recalled days later in Cline — same memory, different sessions, different tools.

## What makes Slowave different?

**👊 Central memory across every AI tool.**  
Claude Code, Cline, Claude Desktop, Cursor, Windsurf, and any MCP-compatible client read from and write to the same memory store. Fix a bug in Claude Code tonight — Cline recalls the lesson tomorrow. Context follows you across tools instead of dying inside one chat.

**🧠 Memory that learns from use.**  
Slowave runs a 5-verb cognitive cycle: *activate* → *remember* → *recall* → *reinforce* → *commit*. Useful memories get stronger, stale ones decay, and outdated facts are superseded automatically. Recall is shaped by salience, time, scope, and feedback — not just raw vector similarity.

**🔮 Zero-config cold start.**  
Drop Slowave into a new project and it auto-discovers key facts from `CLAUDE.md`, `README.md`, and other knowledge files. Your agents walk into context without you writing a single prompt.

**⚙️ Procedural memory: workflows that stick.**  
Store reusable procedures — "how we do deploys in this repo", "steps to implement a new feature across projects". Recalled by goal and situation, not keyword search. Your agents learn habits, not just facts.

**📐 Smart scoping.**  
Memory is scoped to exactly what matters: `project:my-app`, `domain:cooking`, `relationship:alex` — or unscoped for universal context. Cross-project bleed is prevented by default.

**🔒 Fully local, zero LLM calls.**  
Ingestion, consolidation, and recall run on your machine using embeddings, FAISS, and SQLite — no API key, no cloud backend. Memory operations cost $0 per query.

**💰 Compact context instead of history replay.**  
Slowave injects a small working-memory brief instead of replaying full chat history. In internal tests, this reduced context size by 86% over 20 sessions while preserving high recall quality. [See the test →](docs/token_efficiency.md)

## What Slowave is — and isn't

Slowave is **not** a markdown file manager, **not** a static RAG system, and **not** an LLM wrapper over a vector database.

It's built on a single idea:

> **Memory consolidation does not require language.**

Under the hood, Slowave has two layers:

- **Latent layer** — pure geometry over embeddings. Consolidation, reinforcement, decay, supersession, and graph-based connections all run here. Zero LLM calls, ever.
- **Symbolic layer** — the language interface. Text is stored and retrieved, but only *rendered* into natural language when an agent asks for it.

The LLM is an output channel — it verbalizes what memory already knows. It never operates on memory itself.

[Design rationale →](docs/design.md) — [Architecture →](docs/architecture.md)

## The big picture
```
┌────────────┐   work with   ┌─────────────┐
│            │ ────────────▶ │ Claude Code │ ◀───┐
│            │               └─────────────┘     │    (mcp)
│    You     │               ┌─────────────┐     │    context         ┌────────────┐
│  (local)   │ ────────────▶ │    Cline    │ ◀───┼──▶ remember  ◀───▶ │  Slowave   │◀──────┐
│            │               └─────────────┘     │    recall          │  (local)   │       │
│            │               ┌─────────────┐     │    procedure       └─────┬──────┘       │
│            │ ────────────▶ │   Cursor    │ ◀───┘    feedback              │ evolves      │
└────────────┘               └──────┬──────┘                                │ decays       │
                                    │                                       │ reinforces   │
                                    │                                       │ consolidates │
                                    ▼                                       │ learns       │
                              ┌────────────┐                                │ workflows    │
                              │    LLM     │                                └──────────────┘
                              └────────────┘
```

## Install

**pipx**

```bash
pipx install slowave
```

**Homebrew**

```bash
brew tap mrsalty/slowave https://github.com/mrsalty/slowave
brew install slowave
```

Then run setup:

```bash
slowave setup --dry-run
slowave setup
slowave doctor
```

`slowave setup` detects your platform, wires every client it finds, injects lifecycle hooks, and starts the background worker. **Idempotent** and safe to re-run. See [what gets modified →](docs/slowave_setup.md)

> [!NOTE]
> The default text encoder downloads its model from HuggingFace on first use (~45 MB); subsequent runs work fully offline.

> [!IMPORTANT]
> **Claude Desktop:** after setup, paste the lifecycle block into **Settings → General → Instructions for Claude**.
> **Cursor:** after setup, paste the lifecycle block into **Settings → Rules for AI**.
> `slowave setup` prints the exact text and location for both. All other clients (Cline, Claude Code, Windsurf) are fully automated.

```bash
slowave doctor   # verify installation
slowave stats    # memory snapshot
```

Memory is stored at `~/.slowave/slowave.db`. No Ollama, no vector database, no cloud service required.

**Privacy:** Slowave stores all memory (facts, episodes, embeddings, logs) locally in a plain SQLite database file. No memory leaves your machine — it's never sent to a cloud service, and the database file is unencrypted (you can inspect it with SQLite tools). If you store sensitive information, protect the database file using OS-level permissions or full-disk encryption.

**[Full install guide →](docs/install.md)**

## Benchmarks

**93.4%** LongMemEval · **81%** LoCoMo · **86–89%** stale-memory detection — all with **zero LLM calls**, fully local. [Full benchmarks →](docs/benchmarks.md)

## What Slowave remembers

Anything that should survive across sessions and tools: preferences, decisions, constraints, lessons learned, open questions, and reusable workflows — for work, research, or personal use. Each memory carries a timestamp, decays if never recalled, and strengthens when it proves useful. Contradictions are detected geometrically and old facts are superseded automatically — no LLM required.

## Dashboard

Keep Slowave always under control through the local dashboard.

![dashboard.png](img/dashboard.png)

Use it, and Slowave starts connecting the dots.

![dashboard_graph.png](img/dashboard_graph.png)

## Documentation

|                                                      |                                                                |
|------------------------------------------------------|----------------------------------------------------------------|
| [docs/design](docs/design.md)                        | the brain-inspired rationale behind Slowave                    |
| [docs/architecture.md](docs/architecture.md)         | How memory consolidation works                                 |
| [docs/install.md](docs/install.md)                   | Install, setup, per-client wiring, troubleshooting             |
| [docs/slowave_setup.md](docs/slowave_setup.md)       | `slowave setup` command help                                   |
| [docs/manual_setup.md](docs/manual_setup.md)         | Step-by-step manual configuration guide                        |
| [docs/benchmarks.md](docs/benchmarks.md)             | Per-category results, strengths, known gaps, reproducibility   |
| [docs/token_efficiency.md](docs/token_efficiency.md) | Token efficiency vs. history replay and static knowledge files |
| [docs/limitations.md](docs/limitations.md)           | Capability gaps, design trade-offs, deployment limits          |
| [docs/cli.md](docs/cli.md)                           | CLI reference                                                  |
| [docs/dashboard.md](docs/dashboard.md)               | Local web UI (`slowave dashboard`)                             |

## Contributing

Slowave is open source under AGPL-3.0-or-later. Bug reports, install feedback, and focused improvements are welcome — read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a PR. Commercial licensing terms may be offered in the future.
