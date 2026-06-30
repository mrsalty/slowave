# Slowave

> A private, local memory layer that every AI tool you use reads from and writes to — one brain-shaped memory across Claude Code, Cline, Cursor, Windsurf, and any MCP client. Alpha. Built on the idea that **memory consolidation does not require language.**

[![PyPI](https://img.shields.io/pypi/v/slowave?color=2f6f4e)](https://pypi.org/project/slowave/)
[![Python](https://img.shields.io/badge/python-3.11%2B-4c6f91)](https://pypi.org/project/slowave/)
[![PyPI Status](https://img.shields.io/pypi/status/slowave?color=orange)](https://pypi.org/project/slowave/)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE)
[![Downloads](https://static.pepy.tech/badge/slowave)](https://pepy.tech/project/slowave)

Memory is the bottleneck of AI agents. Each session starts from scratch, context dies inside one chat, and when you switch from Claude Code to Cline the lesson you learned tonight is gone tomorrow. Slowave fixes that with one shared memory store — local, private, $0 per query.

## What it is

![Demo](img/demo.gif)

Slowave gives every MCP-compatible client one persistent memory running on your laptop. **Fix a bug in Claude Code on Monday — Cline recalls the lesson, in a different project, on Thursday.** Nothing leaves your machine.

> **The idea behind it all:** memory consolidation does not require language. The LLM verbalizes what memory already knows; it never operates on memory itself. So consolidation runs as pure geometry over embeddings — like the brain consolidates overnight, silently, without talking. That is the whole reason it can run locally, make zero LLM calls, and cost $0 per query. [Why →](docs/design.md)

## Five moves, one memory

Every agent runs the same five-tool cycle — `activate → remember → recall → reinforce → commit` — and what it learns is reusable across every tool, forever:

```text
You start a task: "add validation to the signup form"

1. slowave_activate   primes working memory; surfaces "we use Zod", "tests live in __tests__"
2. slowave_remember   stores "validation uses Zod schemas, not class-validator"
3. slowave_recall     mid-task, pulls the project's existing validation patterns
4. slowave_reinforce  you mark the Zod memory useful → it strengthens
5. slowave_commit     session closes → an episode forms, consolidated offline into a prototype

Days later, in a different tool: "add validation to checkout"
→ the Zod preference is recalled instantly. You never re-teach it.
```

That is the whole product. Everything below is consequence of that one idea.

## What you get

- **Memory that learns and forgets.** Useful memories strengthen every time they help; stale ones decay; outdated facts are superseded automatically. Recall is shaped by salience, time, scope, and your feedback — not raw vector similarity.
- **One memory across every tool.** Claude Code, Cline, Claude Desktop, Cursor, Windsurf, and any MCP-compatible client read from and write to the same store. Context follows you across tools instead of dying inside one chat.
- **$0 per query, fully local.** Ingestion, consolidation, and recall run on your machine — no API key, no cloud, nothing leaves your laptop. Only possible because consolidation is geometry, not language.
- **86% smaller context.** Slowave injects a small working-memory brief instead of replaying full chat history. Measured over 20 sessions with recall quality preserved. [Test →](docs/token_efficiency.md)
- **Workflows that stick.** As agents repeat similar tasks, Slowave learns what tends to come next and surfaces it in the right context. It describes what usually happens; the agent still decides what to do.
- **Zero-config cold start.** Drop it into a new project and it auto-discovers key facts from `CLAUDE.md`, `README.md`, and other knowledge files. Agents walk into context with no prompt from you.
- **Smart scoping.** `project:my-app`, `domain:cooking`, `relationship:alex` — or unscoped for universal context. Cross-project bleed is prevented by default.

## What it is not

A markdown file manager, a static RAG system, or an LLM wrapper over a vector database. It keeps memory strictly separate from reasoning: not a language model, not a reasoning engine, not an agent framework. It is the persistent memory layer those systems plug into. Two layers under the hood:

- **Latent** — pure geometry over embeddings. Consolidation, reinforcement, decay, supersession, and graph connections. Zero LLM calls, ever.
- **Symbolic** — the language interface. Text is stored and retrieved, but only rendered into natural language when an agent asks for it.

[Design rationale →](docs/design.md) · [Architecture →](docs/architecture.md) · [Big picture ↓](#the-big-picture)

## Install

```bash
pipx install slowave
# or
brew tap mrsalty/slowave https://github.com/mrsalty/slowave && brew install slowave
```

Then wire every client it finds:

```bash
slowave setup --dry-run   # see what will change
slowave setup             # wire clients, inject lifecycle hooks, start the worker
slowave doctor            # verify installation
```

`slowave setup` detects your platform, wires every client it finds, injects lifecycle hooks, and starts the background worker. **Idempotent** and safe to re-run. [What gets modified →](docs/slowave_setup.md)

> [!NOTE]
> The default text encoder downloads its model from HuggingFace on first use (~45 MB); subsequent runs work fully offline.

`slowave setup` wires every client it finds automatically. Claude Desktop and Cursor need one manual paste (their instruction surfaces aren't programmatically editable) — `slowave setup` prints the exact text and path. [Full install guide →](docs/install.md)

Memory is stored at `~/.slowave/slowave.db` — a plain SQLite file. No Ollama, no vector database, no cloud service. Inspect it with any SQLite tool.

**Privacy:** all memory (facts, episodes, embeddings, logs) stays in that one local file. It is never sent to a cloud service and is unencrypted by default so you can inspect it — protect it with OS-level permissions or full-disk encryption if you store sensitive data.

## Benchmarks

All runs: zero LLM calls, local CPU, no API key.

| Benchmark | What it tests | Slowave |
|---|---|---:|
| LongMemEval | Facts, updates, preferences across many sessions with realistic distractors | **87.8%** |
| LoCoMo | Cross-session recall across real conversations, 5 categories | **76%** |
| StaleMemory | Detecting when a stored preference has silently changed | **86–89%** |

> Alpha-stage results. Internal runs, not independently verified. Slowave scores with keyword-overlap; most competitors use an LLM-as-judge, so numbers are not directly comparable. [Full benchmarks →](docs/benchmarks.md)

## The big picture

![Slowave flow](img/flow.png)

## Dashboard

Watch and steer it through a local web UI — no deps, plain SQLite under it. Use it, and Slowave starts connecting the dots.

![dashboard.png](img/dashboard.png)
![dashboard_graph.png](img/dashboard_graph.png)

## Documentation

- **[design.md](docs/design.md)** — the brain-inspired rationale. Read this first if you want to understand *why*.
- **[architecture.md](docs/architecture.md)** — how consolidation actually works.
- **[install.md](docs/install.md)** — install, setup, per-client wiring, troubleshooting.
- **[benchmarks.md](docs/benchmarks.md)** — per-category results, strengths, known gaps, reproducibility.
- **[limitations.md](docs/limitations.md)** — capability gaps and design trade-offs. Read this before relying on it for anything important.
- **[token_efficiency.md](docs/token_efficiency.md)** — vs. history replay and static knowledge files.
- **[slowave_setup.md](docs/slowave_setup.md)** · **[manual_setup.md](docs/manual_setup.md)** · **[cli.md](docs/cli.md)** · **[dashboard.md](docs/dashboard.md)** — reference.

## Contributing

Open source under AGPL-3.0-or-later. Bug reports, install feedback, and focused improvements are welcome — read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening a PR. Commercial licensing terms may be offered in the future.
