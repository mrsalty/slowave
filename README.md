# Slowave

**Brain-inspired long-term memory for AI agents and desktop AI chats.** Slowave plugs into Claude Code, Cline, and Claude Desktop through MCP, giving them a shared memory that accumulates, consolidates, adapts, and recalls across sessions.

Slowave's core thesis is simple: **language is not the memory system; language is one interface to it.** The memory engine works in latent space, the way brains appear to operate over distributed internal representations rather than over transcripts. Text is embedded once, then memory evolves through geometry, time, salience, replay, and activation. The default path uses **no LLM for ingest, consolidation, or recall**: inference is local, fast, CPU-friendly, private, and independent of any model provider.

Critical features:

- **No LLM in the core memory loop** — no API key, no cloud extraction step, no per-query model call.
- **Local CPU inference** — BAAI/bge-small-en-v1.5 embeddings, SQLite, FAISS, and deterministic geometry.
- **Brain-inspired consolidation** — raw events become episodes, episodes replay into prototypes, prototypes become latent schemas.
- **Recall changes memory** — retrieved memories are reinforced; recall is an active operation, not a passive database lookup.
- **Time-aware memory** — salience, decay, temporal anchors, supersession, and contradiction handling keep memory current.
- **Generic ingestion** — not code-assistant-specific; it can remember coding work, planning, preferences, decisions, chat context, or any text interaction.
- **Gated working memory** — `slowave_context` injects only a compact, cue-relevant memory brief instead of dumping history into the prompt.
- **Provenance and inspection** — schemas trace back to episodes/raw events; the local dashboard exposes memory health and recall behavior.

## What Slowave is for

Slowave is a local long-term memory substrate for tools that otherwise forget between sessions. It is useful when you want an AI assistant to remember:

- project conventions and architectural decisions;
- personal preferences and communication style;
- recurring workflows and commands;
- previous debugging sessions and lessons learned;
- open questions, warnings, constraints, and artifacts;
- non-coding chat context from desktop AI conversations.

It is intentionally not just a RAG layer. Existing memory systems usually retrieve stored text or ask an LLM to rewrite memories. Slowave treats memory as a living system: sessions create episodes, replay distills patterns, time changes salience, contradiction updates beliefs, and recall itself reinforces what was useful.

## Install in minutes

Slowave is a local memory service. Installing the package gives you two commands:

- `slowave`: CLI, dashboard, manual recall/debugging.
- `slowave-mcp`: MCP server used by Claude Desktop, Claude Code, and Cline.

Recommended for isolated CLI installs:

```bash
pipx install slowave
```

Or install with pip:

```bash
pip install slowave
```

Homebrew is also available on macOS:

```bash
brew tap mrsalty/slowave
brew install slowave
```

To install from source:

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

Then choose your client and follow the short guide:

| Client | Setup guide |
|---|---|
| Claude Desktop | [integrations/claude-desktop/](integrations/claude-desktop/) |
| Claude Code | [integrations/claude-code/](integrations/claude-code/) |
| Cline | [integrations/cline/](integrations/cline/) |

**Important:** MCP setup alone is not enough. Every client needs:

1. MCP configuration so the `slowave_*` tools are visible.
2. Instruction/rules injection so the client actually calls Slowave during the task.
3. A background worker for ongoing consolidation into distilled schemas.

Episodes are created immediately when a session ends. The worker is what turns accumulated episodes into durable latent schemas for better future `slowave_context` injection.

The integration guides contain the exact MCP JSON, prompt/rules block, worker setup, and verification command for each client. Start at [integrations/](integrations/) if you are unsure.

Default storage: `~/.slowave/slowave.db`. No Ollama, OpenRouter, or other LLM backend is required for the default brain-only path.

## Local dashboard

Run a local read-only web UI for memory inspection:

```bash
slowave dashboard
# open http://127.0.0.1:8765
```

The dashboard binds to `127.0.0.1` by default and shows DB health, Slowave/MCP processes, schemas, recall playground, and a schema graph.

## CLI usage

The CLI is useful for debugging, manual memory writes, dashboard access, and benchmark/research workflows. It should not be the first path for most users; real agent memory needs MCP plus prompt/rules injection.

See [docs/cli.md](docs/cli.md) for the command list and a CLI-only quickstart.

## Documentation

| | |
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

Brain-only path: **$0/query · ~10ms recall · no API · data stays on device.**

The gap to Mem0 is structurally about categories that reward LLM extraction/meta-cognition by construction, not just retrieval. See [docs/design.md](docs/design.md) for the design rationale.

## License

MIT.
