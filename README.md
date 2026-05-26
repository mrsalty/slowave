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
```

## Use with a coding agent

Register `slowave-mcp` in your agent's MCP config:

```jsonc
{
  "mcpServers": {
    "slowave": {
      "command": "/path/to/.venv/bin/slowave-mcp",
      "env": { "SLOWAVE_DB": "~/.slowave/slowave.db" }
    }
  }
}
```

Add to the agent's system prompt:

```
Use slowave_* MCP tools for memory.
Start of task: slowave_context. Salient turns: slowave_event. Decisions: slowave_remember. Lookups: slowave_recall. End of task: slowave_session_end.
```

→ [docs/agents.md](docs/agents.md) for session lifecycle, all tools, and event types.

## Documentation

| | |
|---|---|
| [docs/design.md](docs/design.md) | Why LLM was removed from the memory loop — the pivot and its data |
| [docs/architecture.md](docs/architecture.md) | How it works — mechanisms, data flow, storage layout |
| [docs/agents.md](docs/agents.md) | MCP integration, session lifecycle, environment variables |
| [docs/install.md](docs/install.md) | All install paths including brew, conda, from source |
| [docs/benchmarks.md](docs/benchmarks.md) | Reproduce the numbers, ablation flags |
| [docs/stages/](docs/stages/) | Research history — each mechanism documented and benchmarked |

## License

MIT.
