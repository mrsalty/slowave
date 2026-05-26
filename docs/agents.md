# Using Slowave with coding agents

Slowave exposes an MCP server (`slowave-mcp`) that any MCP-aware agent can use as a tool.

## Register the MCP server

```jsonc
// Claude Code: ~/.claude/settings.json
// Cline: cline_mcp_settings.json  |  Cursor: .cursor/mcp.json
{
  "mcpServers": {
    "slowave": {
      "command": "/full/path/to/.venv/bin/slowave-mcp",
      "env": {
        "SLOWAVE_DB": "/Users/you/.slowave/slowave.db",
        "KMP_DUPLICATE_LIB_OK": "TRUE",
        "OMP_NUM_THREADS": "1",
        "TOKENIZERS_PARALLELISM": "false"
      }
    }
  }
}
```

`SLOWAVE_DB` defaults to `~/.slowave/slowave.db` if omitted. The other three env vars suppress macOS OpenMP warnings from PyTorch/FAISS.

## System prompt addition

```
You have access to Slowave long-term memory via slowave_* MCP tools.
- Task start: call slowave_context to load prior memory for this project.
- During work: log salient turns with slowave_event (session_id from slowave_session_start).
- Durable decisions: use slowave_remember instead of slowave_event.
- Lookups: slowave_recall. Cite ids as [sch_xxx] or [epi_xxx].
- Task end: call slowave_session_end to encode the session into memory.
```

## Session lifecycle

```
slowave_session_start(agent="claude-code", project="my-repo")  →  session_id

  slowave_event(session_id, "user_message",      "…")
  slowave_event(session_id, "assistant_message", "…")
  slowave_event(session_id, "decision",          "We'll use SQLite.")
  slowave_remember("We use SQLite for this project", type="decision")  # high-salience, no session needed

slowave_session_end(session_id)   # fast, no LLM — episodes form immediately
```

Consolidation (prototype clustering → latent schemas) is decoupled. Run in the background:

```bash
slowave worker --interval 300 &   # every 5 min, detached
slowave worker --once             # single pass (after a long session)
```

## MCP tools

| Tool | Description |
|---|---|
| `slowave_session_start(agent?, project?)` | Begin a session, returns `session_id` |
| `slowave_event(session_id, type, content)` | Log a turn |
| `slowave_session_end(session_id)` | Close session — fast, no LLM |
| `slowave_recall(query, top_k?, evidence?)` | Semantic recall |
| `slowave_remember(content, type?, project?)` | Explicit durable memory |
| `slowave_context(project?, limit?)` | Memory brief for task start |
| `slowave_consolidate()` | Trigger consolidation manually |
| `slowave_stats()` | Episode / prototype / schema counts |

**Event types:** `user_message` `assistant_message` `tool_call` `tool_result` `decision` `error` `task_complete` `task_failed`

**Memory types for `slowave_remember`:** `fact` `preference` `decision` `constraint` `procedure` `lesson` `warning`

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `SLOWAVE_DB` | `~/.slowave/slowave.db` | SQLite file path |
| `SLOWAVE_PROJECT` | *(none)* | Default project scope |
| `SLOWAVE_MODEL` | `qwen2.5:7b-instruct` | Only used with `--schema-mode llm` |
| `SLOWAVE_OLLAMA_URL` | `http://localhost:11434` | Only used with `--schema-mode llm` |
| `OPENROUTER_API_KEY` | *(none)* | Cloud LLM backend (legacy) |

For the brain-only default, only `SLOWAVE_DB` is relevant.
