# Slowave

**Brain-inspired, latent-space long-term memory for MCP-compatible AI agents, coding assistants, and chats.  
Shared across sessions, clients, and tools.**

[![PyPI](https://img.shields.io/pypi/v/slowave?color=2f6f4e)](https://pypi.org/project/slowave/)
[![Python](https://img.shields.io/pypi/pyversions/slowave?color=4c6f91)](https://pypi.org/project/slowave/)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE)

Slowave plugs into **Claude Code**, **Cline**, and **Claude Desktop** through MCP, giving them a shared local memory that accumulates, consolidates, adapts, and recalls across sessions.

Slowave is not just a transcript store or a conventional RAG layer. It is inspired by the idea that memory is a dynamic system shaped by association, time, salience, replay, and retrieval. The default memory path uses local embeddings, SQLite, FAISS, deterministic geometry, and background consolidation — without requiring an LLM call in the core memory loop.

> **Slowave core idea:** sessions create episodes, replay distills recurring patterns, time changes salience, contradiction-aware updates keep memory current, and recall reinforces memories that prove useful.

## Status

**v0.1.5 — Alpha.** The core local memory path, MCP server, CLI, and dashboard are functional. Python 3.10–3.12 is supported and tested; Python 3.13 is not yet supported.

Run `slowave doctor` after installing to verify your environment.

## At a glance

| What you get | Why it matters |
|---|---|
| **No LLM in the core memory loop** | No API key, cloud extraction step, or per-query model call required. Memory ingest, consolidation, and retrieval are all LLM-free. |
| **Privacy-first local memory** | Memory is stored and processed locally; no cloud memory backend, API extraction step, or remote LLM inference is required. |
| **Local CPU inference** | Uses BAAI/bge-small-en-v1.5 embeddings, SQLite, FAISS, and deterministic geometry. |
| **Brain-inspired consolidation** | Raw events become episodes; episodes replay into prototypes; prototypes consolidate into latent schemas. |
| **Active recall** | Retrieved memories are reinforced, so recall changes the memory system over time. |
| **Time-aware memory** | Salience, decay, temporal anchors, supersession, and contradiction-aware updates help keep memory current. Episodes are date-stamped (ISO 8601) and recalled with temporal context. |
| **Gated working memory** | `slowave_context` injects a compact, cue-relevant brief instead of dumping history into the prompt. |

```mermaid
flowchart LR
    A([💬 Events]) -->|session end| B([🧠 Episodes])
    B -->|replay| C([🌀 Prototypes])
    C -->|consolidation| D([📖 Schemas])
    D -->|recall| E([⚡ Context brief])
    E -.->|reinforces| B
    E -.->|reinforces| C

    style A fill:#2d4a3e,stroke:#4caf87,color:#e8f5e9
    style B fill:#1a3a5c,stroke:#4a9eff,color:#e3f0ff
    style C fill:#3a2d5c,stroke:#9b7fee,color:#f0ebff
    style D fill:#4a2d1a,stroke:#ff9944,color:#fff3e0
    style E fill:#1a3a2d,stroke:#44cc88,color:#e8f5e9
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
# Recommended — isolated, no virtualenv management needed
pipx install slowave

# pip
pip install slowave

# macOS Homebrew (formula lives in the main repo)
brew tap mrsalty/slowave https://github.com/mrsalty/slowave
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

Verify your environment:

```bash
slowave doctor           # check Python version, torch, faiss, embedding backend
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
| [docs/benchmarks.md](docs/benchmarks.md) | Benchmark results, run conditions, per-category breakdown |
| [docs/limitations.md](docs/limitations.md) | Known limitations: schema quality, language support, scale |
| [docs/reproducibility.md](docs/reproducibility.md) | How to reproduce benchmark numbers |

## Benchmarks

> **Alpha-stage numbers.** Internal runs, not independently verified. Treat as directional. See [docs/benchmarks.md](docs/benchmarks.md) for full run conditions and known gaps.

**All runs: brain-only path, local CPU, BAAI/bge-small-en-v1.5 embeddings, SQLite + FAISS, zero LLM calls.**

Two modes are reported. The **with-consolidation** numbers (70.0% / 74.6%) represent the full Slowave pipeline: sessions → episodes → replay → latent schemas → recall. The **episode-only baseline** (60.2% / 74.6%) is retrieval without consolidation — episodes recalled directly, no schemas. The difference shows the contribution of the consolidation layer.

### Overall results

| Benchmark | Questions | With consolidation | Episode-only baseline | Cosine-only ablation¹ |
|---|---:|---:|---:|---:|
| LongMemEval | 500 | **70.0%** | 60.2% | ~60.0% |
| LoCoMo | 1 986 | **74.6%** | 74.6%² | ~68.0% |

*Metric: keyword hit-rate. All runs: zero LLM calls, ~10 ms recall latency, data on device.*

¹ Cosine-only ablation: spreading activation, graph expansion, and transition model all disabled.  
² LoCoMo is multi-session by design; episode retrieval already captures most of the signal and consolidation adds schemas on top of a strong baseline.

### Deep Memory Retrieval (DMR)

DMR (MemGPT paper) tests factual recall across multi-session persona conversations: 10 personas × 10 questions = 100 questions total. Published baselines from arXiv:2501.13956.

| System | Score | LLM calls | Cost |
|---|---:|---|---|
| **Slowave v0.1.5** | **95.0%** | **0** | **$0.00** |
| Zep (SOTA) | 94.8% | Many | $ |
| MemGPT baseline | 93.4% | Many | $ |

Slowave beats both published LLM-augmented baselines with zero API cost and ~9 ms recall latency.

### LongMemEval per-category (with consolidation)

| Category | Score | Notes |
|---|---:|---|
| Single-session-user | **91.4%** | ✅ strong |
| Knowledge-update | **92.3%** | ✅ strong |
| Single-session-assistant | **66.1%** | ✅ solid |
| Temporal-reasoning | **67.7%** | ✅ solid |
| Multi-session | 60.9% | ⚠ number aggregation gap |
| Single-session-preference | 20.0% | ⚠ preference abstraction gap |

### LoCoMo per-category (with consolidation)

| Category | Score | Notes |
|---|---:|---|
| Multi-session | **86.2%** | ✅ strong cross-session recall |
| Adversarial | **82.3%** | ✅ robust |
| Single-session | 64.9% | ✅ solid |
| Temporal | **56.1%** | ✅ solid |
| Commonsense | 27.1% | — world knowledge not in store |

### Known gaps

| Gap | Root cause | Status |
|---|---|---|
| Temporal date arithmetic | "How many days between X and Y?" requires arithmetic, not retrieval | Open — answer-construction layer |
| Multi-session aggregation (LME 60.9%) | Summing quantities across episodes — no single episode holds the answer | Open — explicit aggregation layer |
| Preference abstraction (LME 20%) | Implicit preferences not abstracted into queryable schema entries | Open — preference-extraction layer |

### Language support

**All core memory operations are language-agnostic** — episode storage, embedding, retrieval, FAISS search, salience, spreading activation, the prototype graph, and multi-scale consolidation work on embedding vectors and numeric metadata with no language dependency.

**One component is English-only: the temporal anchor probe (Stage 10).** This component estimates which past time period a query refers to ("last month", "two weeks ago") by comparing the query embedding against a set of pre-embedded English landmark phrases. For non-English queries, the temporal anchor probe does not fire and the system falls back to the previous default: the temporal re-ranking bonus is computed from "now", which is correct for atemporal queries and slightly suboptimal for past-anchored ones. No other capability is affected.

The probe phrase list is in `slowave/latent/temporal.py` (`_TEMPORAL_PROBES`). Adding phrases in other languages extends the compass to those languages without any other code change.

For full per-category results, run conditions, and known gaps see [docs/benchmarks.md](docs/benchmarks.md).  
For evaluation scripts and reproduction steps see [docs/reproducibility.md](docs/reproducibility.md).  
For known limitations see [docs/limitations.md](docs/limitations.md).

## License

Slowave is licensed under the **GNU Affero General Public License v3.0 or later** starting with version **0.1.5**.

Versions published before 0.1.5 were released under the MIT License; those earlier releases remain available under the terms they were originally published with.

This license keeps Slowave open for research, experimentation, and community use while ensuring that modified versions offered over a network make their source available under the same terms. Commercial licenses may be available for organizations that want to use Slowave in proprietary products, hosted services, or other contexts where AGPL compliance is not suitable. See [COMMERCIAL.md](COMMERCIAL.md).
