# Slowave

**A shared local memory layer for your AI tools.**

Install once. Your AI tools share the same evolving local memory across sessions and across tools.

Slowave lets Claude Code, Cursor, Cline, Windsurf, Claude Desktop, and any MCP-compatible client read from and write to the same local memory. 

Everything runs locally with no cloud backend and no additional LLM calls for memory operations.

[![PyPI](https://img.shields.io/pypi/v/slowave?color=2f6f4e)](https://pypi.org/project/slowave/)
[![Python](https://img.shields.io/badge/python-3.11%2B-4c6f91)](https://pypi.org/project/slowave/)
[![PyPI Status](https://img.shields.io/pypi/status/slowave?color=orange)](https://pypi.org/project/slowave/)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE)
[![Downloads](https://static.pepy.tech/badge/slowave)](https://pepy.tech/project/slowave)

---

## Typical workflow

![Demo](img/demo.gif)

You use your AI tools normally.

- Start a new session → relevant context is recalled.
- Work as usual → useful information is stored automatically.
- Switch to another client → the same memory is available.
- Resume later → previous work can be recalled without replaying entire conversations.

Instead of relying on chat history or project-specific markdown files, multiple AI clients continuously build and reuse the same evolving memory.

---

## How memory evolves

Slowave is designed around memory consolidation rather than note storage.

Individual interactions become **episodes**. Related episodes are consolidated into **prototypes**. Repeated prototypes become **schemas** representing recurring conventions, preferences, and project knowledge.

Useful memories become easier to retrieve through reinforcement. Outdated memories gradually weaken through decay. When newer information replaces older facts, supersession allows recent knowledge to take precedence.

Over time, recall shifts from isolated facts toward recurring project patterns and decisions.

The overall feedback loop looks like this:

```text
use your AI tools
    → Slowave stores durable memory
        → offline consolidation
            → more useful recall
                → better context in future sessions
```

The first sessions mostly accumulate experience. As more work is stored, recall increasingly reflects recurring project conventions, previous decisions, debugging history, and personal workflows rather than isolated conversations.

---

### Why Slowave is different

Slowave is built around one central idea:

> Memory consolidation does not require language.

In Slowave, memory is not managed as prompts or replayed transcripts. Stored claims live alongside evolving embedding-based state, and consolidation, reinforcement, decay, supersession, and retrieval all operate directly over that representation.

The language model does not maintain memory. It authors what gets remembered and receives the final recalled context — but no LLM call is involved in consolidating, ranking, or revising what is stored.

This separation has direct consequences:

- Memory is shared across all MCP-compatible clients, since it lives outside any single tool’s prompt or history.
- No cloud or external service is required, because all operations are local.
- Memory operations do not require LLM calls, since consolidation and retrieval happen in embedding space.
- Context injected into the model is compact and selective, rather than a replay of past conversations.
- Memory can evolve through reinforcement and decay rather than static accumulation of notes.
- Scope control (project, domain, global) prevents unrelated contexts from interfering with each other.
Additional background:

See:
> [Design rationale](docs/design.md)
> 
> [Architecture](docs/architecture.md)

---

## Installation

Install Slowave:

```bash
pipx install slowave

# or

brew tap mrsalty/slowave https://github.com/mrsalty/slowave
brew install slowave
```

Configure every supported client:

```bash
slowave setup --dry-run
slowave setup
slowave doctor
```

`slowave setup` is idempotent and safe to run multiple times.

Claude Desktop and Cursor require one manual paste because their instruction surfaces cannot currently be modified programmatically. During setup, Slowave prints the exact text and destination path.

See the complete installation guide:

- [docs/install.md](docs/install.md)

The default embedding model is downloaded from Hugging Face on first use (~45 MB). Subsequent runs work offline.

Memory is stored locally as a SQLite database:

```
~/.slowave/slowave.db
```

The database is fully inspectable and remains on your machine. It is not encrypted by default, so sensitive information should be protected using normal operating system permissions or full-disk encryption.

---

## Dashboard

Watch memory evolve through the local dashboard.

Inspect stored memories, browse recall results, visualize relationships, and observe consolidation over time.

![dashboard.png](img/dashboard.png)

![dashboard_graph.png](img/dashboard_graph.png)

## Benchmarks

Benchmarks were run internally during development to evaluate recall quality, stability, and context efficiency. Results have not yet been independently reproduced.

Slowave does not use an LLM for memory operations; all evaluation is based on embedding retrieval and local consolidation.

| Benchmark | What it evaluates | Result |
|---|---|---:|
| LongMemEval | Multi-session factual recall with noise and distractors | 87.8% |
| LoCoMo | Cross-session conversational recall across categories | 76% |
| StaleMemory | Detection of outdated or superseded preferences | 86–89% |

These results are not directly comparable with systems that use LLM-as-a-judge scoring, since Slowave relies on embedding-based matching metrics.

Full benchmark methodology and reproducibility details:
- [docs/benchmarks.md](docs/benchmarks.md)

---

## Honest limits

Slowave is useful in practice but intentionally constrained by its design.

- It recalls stored information; it does not infer missing preferences.
- It retrieves relevant memories; it does not perform reasoning over memory graphs.
- Contradiction handling is heuristic and may not always resolve conflicts correctly.
- It is not designed for safety-critical or compliance-critical memory use cases.
- Memory quality depends on the quality and consistency of prior interactions.

These limitations are a direct consequence of the zero-LLM memory design rather than implementation gaps.

See: [docs/limitations.md](docs/limitations.md)

---

## What it is not

Slowave is not:

- a language model
- an agent framework
- a reasoning system
- a prompt manager
- a markdown-based memory store
- a vector database wrapper

The AI client remains responsible for planning, reasoning, and execution.

Slowave only provides persistent, evolving context injection based on prior interactions.

---

## Documentation

- [design.md](docs/design.md) — design rationale, boundaries, and positioning
- [architecture.md](docs/architecture.md) — brain-inspired memory model and lifecycle
- [install.md](docs/install.md) — setup and client integration
- [benchmarks.md](docs/benchmarks.md) — evaluation methodology and results
- [limitations.md](docs/limitations.md) — known constraints and trade-offs
- [token_efficiency.md](docs/token_efficiency.md) — context efficiency analysis

---

## Contributing

Slowave is open source under the AGPL-3.0-or-later license.

Contributions are welcome, especially in:
- client integrations
- recall quality improvements
- evaluation datasets
- performance optimization

See [CONTRIBUTING.md](./CONTRIBUTING.md) before submitting a pull request.

Commercial licensing may be considered in the future.