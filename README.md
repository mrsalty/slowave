# Slowave

Brain-inspired long-term memory for AI agents. **Zero LLM during ingest or retrieval.**

Memory consolidation, abstraction, and recall happen entirely in continuous vector space — shaped by neuroscience mechanisms (Hebbian learning, slow-wave replay, salience decay, spreading activation). Language is an output channel only.

## Results

**Agent Memory (Long-term context)**:
| Benchmark | Cosine RAG | **Slowave** | Δ | Mem0 SOTA |
|---|---|---|---|---|
| LongMemEval (500q) | 60.0% | **70.0%** | +10pp | 94.4% |
| LoCoMo (1986q) | 68.0% | **75.5%** | +7.5pp | 92.5% |

**Retrieval-Augmented Generation (QA)**:
| Benchmark | **Slowave** | HippoRAG | Δ |
|---|---|---|---|
| 2WikiMultiHopQA Recall@5 | **82.5%** | 87% | −5.2% |

→ [docs/benchmarks.md](docs/benchmarks.md) for reproducing all results.

**Brain-only path:** $0/query · ~10ms recall · no API · data stays on device.
- The ~24pp gap to Mem0 on agent memory is about meta-cognition categories that require LLM extraction by construction, not retrieval. See [docs/design.md](docs/design.md).
- The 5.2% gap to HippoRAG on QA is despite HippoRAG using knowledge graphs + structured retrieval, while Slowave uses pure geometry. See [docs/benchmarks/hipporag-qa-comparison.md](docs/benchmarks/hipporag-qa-comparison.md).

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
| [docs/install.md](docs/install.md) | All install paths including brew, conda, from source |
| [docs/benchmarks.md](docs/benchmarks.md) | Reproduce the numbers, ablation flags |
| [docs/stages/](docs/stages/) | Research history — each mechanism documented and benchmarked |

## License

MIT.
