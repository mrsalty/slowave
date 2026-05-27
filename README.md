# Slowave

Brain-inspired long-term memory for AI agents. **Zero LLM during ingest or retrieval.**

Memory consolidation, abstraction, and recall happen entirely in continuous vector space — shaped by neuroscience mechanisms (Hebbian learning, slow-wave replay, salience decay, spreading activation). Language is an output channel only.

## Results

| Benchmark | Cosine RAG | **Slowave** | Δ | Mem0 SOTA |
|---|---|---|---|---|
| LongMemEval (500q) | 60.0% | **70.0%** | +10pp | 94.4% |
| LoCoMo (1986q) | 68.0% | **75.5%** | +7.5pp | 92.5% |

Brain-only path: **$0/query · ~10ms recall · no API · data stays on device.**

The ~24pp gap to Mem0 is structurally about meta-cognition categories that require LLM extraction by construction, not about retrieval. See [docs/design.md](docs/design.md).

## Install

```bash
pip install slowave            # or: pipx install slowave
brew tap mrsalty/slowave && brew install slowave
conda install -c conda-forge slowave
```

→ [docs/install.md](docs/install.md) for full options including from source.

## Quick start

```bash
SID=$(slowave --json session start --agent myagent \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["session_id"])')

slowave event --session "$SID" --type user_message --content "I prefer SQLite for MVPs."
slowave session end "$SID"
slowave worker --once                          # consolidate into memory
slowave recall "database preference"
slowave remember "Using SQLite for the MVP" --type decision
slowave dashboard                              # local web UI at http://127.0.0.1:8765
```

## Command list

| Command | Purpose |
|---|---|
| `slowave session start --agent <name> --project <project>` | Start a memory session |
| `slowave event --session <sid> --type <type> --content <text>` | Append a raw event to a session |
| `slowave session end <sid>` | Close a session and form episodes, fast/no LLM by default |
| `slowave remember <text> --type <type> --project <project>` | Store an explicit high-salience memory |
| `slowave recall <query> --top-k 5 --evidence` | Retrieve relevant schemas, episodes, and optional raw evidence |
| `slowave context --project <project> --limit 10` | Print a memory brief for agent context |
| `slowave schema --needs-review --limit 50` | List schemas, optionally the review queue |
| `slowave show sch_123` | Inspect a schema, episode, or raw event by ref |
| `slowave stats` | Print episode/prototype/schema/edge counts |
| `slowave status` | Print DB health, schema health, and local Slowave process snapshot |
| `slowave dedup-schemas --apply` | Merge exact duplicate active schemas; dry-run by default |
| `slowave consolidate` | Run replay + latent schema consolidation once |
| `slowave worker --interval 300` | Run periodic background consolidation |
| `slowave dashboard --port 8765` | Run the local read-only web dashboard |

## Local dashboard

Run a local read-only web UI for live inspection:

```bash
slowave dashboard
# open http://127.0.0.1:8765
```

Slowave uses `~/.slowave/slowave.db` by default. Set `SLOWAVE_DB` or pass
`--db /path/to/slowave.db` only when you intentionally want a different DB.

Useful options:

```bash
slowave dashboard --port 8766 --no-open
slowave dashboard --refresh-ms 5000
```

The dashboard is dependency-free and binds to `127.0.0.1` by default. It shows overview stats, DB health, Slowave/MCP processes, schemas, recall playground, and a schema graph with status filters plus a minimum-salience slider.

→ [docs/dashboard.md](docs/dashboard.md) for screenshots-by-description, API endpoints, and operational notes.

## Use with a coding agent

Register `slowave-mcp` in your agent's MCP config:

```jsonc
{
  "mcpServers": {
    "slowave": {
      "command": "/path/to/.venv/bin/slowave-mcp"
    }
  }
}
```

Add to the agent's system prompt:

```
You have access to Slowave long-term memory via slowave_* MCP tools.
At task start: call slowave_context (load prior memory), then slowave_session_start (get session_id).
During the task: call slowave_event(session_id, ...) for EVERY user message and EVERY assistant response — do not skip turns.
For durable decisions/facts: call slowave_remember (no session_id needed).
For lookups: call slowave_recall.
At task end: call slowave_session_end(session_id).
```

→ [docs/agents.md](docs/agents.md) for session lifecycle, all tools, and event types.

## Documentation

| | |
|---|---|
| [docs/design.md](docs/design.md) | Why LLM was removed from the memory loop — the pivot and its data |
| [docs/architecture.md](docs/architecture.md) | How it works — mechanisms, data flow, storage layout |
| [docs/agents.md](docs/agents.md) | MCP integration, session lifecycle, environment variables |
| [docs/dashboard.md](docs/dashboard.md) | Local web dashboard, schema graph, process/DB health monitoring |
| [docs/install.md](docs/install.md) | All install paths including brew, conda, from source |
| [docs/benchmarks.md](docs/benchmarks.md) | Reproduce the numbers, ablation flags |
| [docs/stages/](docs/stages/) | Research history — each mechanism documented and benchmarked |

## License

MIT.
