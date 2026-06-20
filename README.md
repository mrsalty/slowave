# Slowave

**One private memory layer across your AI clients.**

[![PyPI](https://img.shields.io/pypi/v/slowave?color=2f6f4e)](https://pypi.org/project/slowave/)
[![Python](https://img.shields.io/badge/python-3.11%2B-4c6f91)](https://pypi.org/project/slowave/)
[![PyPI Status](https://img.shields.io/pypi/status/slowave?color=orange)](https://pypi.org/project/slowave/)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE)
[![Downloads](https://static.pepy.tech/badge/slowave)](https://pepy.tech/project/slowave)

Slowave gives Claude Code, Cline, Cursor, Claude Desktop, Windsurf, and other MCP-compatible tools access to the same persistent memory. Instead of each tool forgetting in isolation, they share one memory layer that persists across sessions, follows you across tools, and costs $0 — no LLM in the loop, fully local.

## Demo

See Slowave in action: cold start → memory acquisition → cross-session recall across both Claude and Cline:

![Demo](img/demo.gif)

> The demo shows:
> 
> (1) Cold start on a fresh project — Slowave ingests Markdown memory files and builds initial knowledge.
>
> (2) An agent stores a new rule (“run tests & lint before pushing”).
>
> (3) A new Claude session — implements a feature, pushes changes, and correctly recalls the stored rule.
>
> (4) A new Cline session — queried for remembered context and retrieves all relevant memories, including the testing/linting rule.

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

## What makes Slowave different?

**👊 Central memory across every AI tool.**  
Claude Code, Cline, Claude Desktop, Cursor, Windsurf, and any MCP-compatible client read from and write to the same memory store. Fix a bug in Claude Code tonight — Cline recalls the lesson tomorrow. Context follows you across tools instead of dying inside one chat.

**🧠 Adaptive memory, not just notes or a vector index.**  
Memory changes with use: useful memories are reinforced, stale ones decay, and outdated ones are superseded. Recall is shaped by salience, time, scope, and feedback — not just raw vector similarity.

**⚙️ Procedural memory: workflows that stick.**  
Slowave stores reusable procedures — "how we do deploys in this repo", "steps to implement a new feature across projects". Recalled by goal and situation, not keyword search. Your agents learn habits, not just facts.

**🔒 Fully local, zero LLM calls.**  
Ingestion, consolidation, and recall run on your machine using embeddings, FAISS, and SQLite — no API key, no cloud backend. Memory operations cost $0 per query.

**💰 Compact context instead of history replay.**  
Slowave injects a small working-memory brief instead of replaying full chat history. In internal tests, this reduced context size by 86% over 20 sessions while preserving high recall quality. [See the test →](docs/token_efficiency.md)

## Benchmarks

> Alpha-stage numbers. Internal runs, not independently verified. See [docs/benchmarks.md](docs/benchmarks.md) for per-category results, known gaps, and reproducibility.

On **fact-recall benchmarks**, Slowave reaches scores competitive with LLM-based memory systems — **with zero LLM calls**. Gaps remain in implicit preference inference and behavioral style drift, which require LLM reasoning that Slowave deliberately avoids. [See known gaps →](docs/limitations.md)

| Benchmark |    n | Slowave | Published / reported comparator | Slowave LLM calls |
|---|-----:|---:|---|:---:|
| LoCoMo (multi-session recall) | 1 986 | **81%** | Zep 75.1% · LangMem 58.1% · GPT-4 fine-tuned ~76% | **0** |
| LongMemEval (full haystack) | 500 | **93.4%** | Mem0 94.4%† | **0** |
| StaleMemory — concrete preference drift‡ | 900 | **86–89%** | no published baseline | **0** |

> † Mem0 uses GPT-5 as judge; Slowave uses keyword-overlap. The 1 pp LME gap falls within the expected difference between these two scoring protocols — the gap would likely narrow on the same scorer, but this has not been directly measured. The LoCoMo gap is large enough to hold across any reasonable scorer. All Slowave runs: zero LLM calls, fully local. [Full methodology →](docs/benchmarks.md)
>
> ‡ Concrete-keyword subset of 1,200 total StaleMemory scenarios. Abstract behavioral drift (the remaining 300 scenarios) scores 0–1% — a structural limit of retrieval-only systems. [See known gaps →](docs/limitations.md)

## How Slowave compares

|  | MEMORY.md | Plain RAG | Mem0 / Zep / Graphiti | Letta / LangMem | **Slowave** |
|---|:---:|:---:|:---:|:---:|:---:|
| Persistent across sessions | ✅ | ✅ | ✅ | ✅ | ✅ |
| Shared across MCP tools | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Local-first by default | ✅ | ✅ | ⚠️ | ⚠️ | ✅ |
| Adaptive recall over time | ❌ | ❌ | ⚠️ | ⚠️ | ✅ |
| Reinforcement / decay without LLM calls | ❌ | ❌ | ❌ | ❌ | ✅ |
| Supersession / stale-memory handling | ❌ | ❌ | ✅ | ⚠️ | ✅ |
| Procedural memory / workflows | ⚠️ | ❌ | ⚠️ | ✅ | ✅ |
| Zero memory API cost | ✅ | ✅ | ❌ | ⚠️ | ✅ |

> ✅ = native or central capability.  
> ⚠️ = possible, partial, backend-dependent, or LLM-mediated.  
> ❌ = not a primary/default capability.


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

## What Slowave remembers

Anything that should survive across sessions and tools: preferences, decisions, constraints, lessons learned, open questions, and reusable workflows — for work, research, or personal use. Each memory carries a timestamp, decays if never recalled, and strengthens when it proves useful. Contradictions are detected geometrically and old facts are superseded automatically — no LLM required.

Memory is scoped flexibly: `project:my-app`, `domain:cooking`, `relationship:alex` — or unscoped for universal context.

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
