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

## Install and make it actually work

Installing the package is only step one. To run Slowave at regime with an AI client, you must do **both**:

1. **MCP wiring** — expose the `slowave_*` tools to the client.
2. **Prompt/rules injection** — tell the client that using Slowave is part of its lifecycle.

MCP alone is not enough. If the agent can see the tools but is not instructed to call them at task start, during the task, and at task end, memory will be sparse or empty.

### 1. Install the package

```bash
pipx install slowave
# or: pip install slowave
# or: brew tap mrsalty/slowave && brew install slowave
```

Verify the commands are available:

```bash
slowave --help
slowave-mcp --help
slowave stats
```

Slowave stores data in `~/.slowave/slowave.db` by default. No Ollama, OpenRouter, or other LLM backend is required for the default brain-only path.

### 2. Add the MCP server

Find the installed MCP executable:

```bash
which slowave-mcp
```

Use the absolute path in your client's MCP config:

```jsonc
{
  "mcpServers": {
    "slowave": {
      "command": "/absolute/path/to/slowave-mcp",
      "env": {
        "KMP_DUPLICATE_LIB_OK": "TRUE",
        "OMP_NUM_THREADS": "1",
        "TOKENIZERS_PARALLELISM": "false"
      }
    }
  }
}
```

Known integration points:

| Client | MCP config | Prompt/rules injection |
|---|---|---|
| **Claude Code** | `~/.claude/settings.json` | global/user `~/.claude/CLAUDE.md` and/or repo `CLAUDE.md` |
| **Cline** | Cline MCP settings JSON | global `~/.clinerules` or repo `.clinerules` |
| **Claude Desktop** | macOS: `~/Library/Application Support/Claude/claude_desktop_config.json` | Upload [`integrations/claude-desktop/slowave.skill`](integrations/claude-desktop/slowave.skill) via Settings -> Connectors -> Customize -> Skills -> Create -> Upload |

For Claude Desktop, MCP setup is necessary but not sufficient: also upload the Slowave Skill bundle at [`integrations/claude-desktop/slowave.skill`](integrations/claude-desktop/slowave.skill) from **Settings -> Connectors -> Customize -> Skills -> Create -> Upload**.

For the fastest client-specific setup, start with [integrations/](integrations/). See [docs/install.md](docs/install.md) for exact setup and verification steps.

### 3. Inject the required memory lifecycle

Add this block to the client instruction surface listed above:

```md
## Slowave memory

Use Slowave MCP tools as long-term memory for every task/session.

Mandatory lifecycle:
1. First Slowave call: `slowave_session_start(agent="<client-id>", project="<repo-or-domain-or-null>")` and store the returned `session_id`.
2. Immediately log the user request: `slowave_event(session_id, "user_message", "<self-contained request>")`.
3. Load working memory: `slowave_context(query="<current task or user message>", application="<client-id>", project="<repo-or-domain-or-null>", topics=[...], entities=[...], limit=8, mode="default")`.
4. During work, call `slowave_event(session_id, type, content)` for meaningful user/assistant messages, tool calls/results, decisions, discoveries, errors, and completion/failure.
5. End every task/session with a final `assistant_message` when applicable, `task_complete` or `task_failed`, then `slowave_session_end(session_id)`.

Event content must be 1-3 self-contained sentences with the reason/result, not vague notes like "ran command".

Use `slowave_remember(content, type, project)` for durable facts, preferences, decisions, constraints, procedures, warnings, lessons, tasks, open questions, or artifacts.

Use `slowave_context` for default prompt priming. Use `slowave_recall` only when broad history/evidence is explicitly needed. Do not call `slowave_recall` by default after `slowave_context`.

Broken-session anti-patterns:
- Starting and ending a session without `slowave_event` calls.
- Batching all events at the end.
- Forgetting or changing the returned `session_id`.
- Treating `slowave_recall` as default scoped context.
```


Recommended ids:

| Client | `agent` / `application` |
|---|---|
| Claude Code | `claude-code` |
| Cline | `cline-tui` |
| Claude Desktop | `claude-desktop` |

See [docs/agents.md](docs/agents.md) and [docs/agent-enforcement.md](docs/agent-enforcement.md) for client-specific templates.

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
| [docs/agents.md](docs/agents.md) | MCP tool behavior and lifecycle for Claude Code, Cline, Claude Desktop |
| [docs/agent-enforcement.md](docs/agent-enforcement.md) | Copy/paste prompt templates that make clients call Slowave consistently |
| [docs/architecture.md](docs/architecture.md) | Brain-inspired mechanisms, data flow, storage, recall, consolidation |
| [docs/design.md](docs/design.md) | Why the LLM path was removed from the memory loop |
| [docs/dashboard.md](docs/dashboard.md) | Local dashboard guide |
| [docs/cli.md](docs/cli.md) | CLI quickstart and command reference |
| [docs/benchmarks.md](docs/benchmarks.md) | Reproduce benchmark numbers and ablations |
| [docs/release.md](docs/release.md) | Release workflow and versioning |
| [docs/stages/](docs/stages/) | Research history for each mechanism |

## Benchmarks

Public retrieval/RAG-style benchmarks are useful regression tests, but they do not measure every Slowave feature. They mostly test fact recovery, not long-term accumulation, distillation, time-aware adaptation, or recall-driven memory reinforcement.

| Benchmark | Cosine RAG | **Slowave** | Δ | Mem0 SOTA |
|---|---:|---:|---:|---:|
| LongMemEval (500q) | 60.0% | **70.0%** | +10pp | 94.4% |
| LoCoMo (1986q) | 68.0% | **75.5%** | +7.5pp | 92.5% |

Brain-only path: **$0/query · ~10ms recall · no API · data stays on device.**

The gap to Mem0 is structurally about categories that reward LLM extraction/meta-cognition by construction, not just retrieval. See [docs/design.md](docs/design.md) and [docs/benchmarks.md](docs/benchmarks.md).

## License

MIT.
