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
- Task start: call slowave_context(query=<current task/chat message>,
  application=<your-agent-or-app>, topics=<optional high-level topics>) to load a
  small working-memory brief, then slowave_session_start(agent=<your-agent-id>)
  to get a session_id.
- Coding agents may additionally pass project=<workspace-or-repo-name> as an
  environmental cue on slowave_context/session/logging calls, but project is not
  required for generic chatbots and is not the primary context key.
- During the task: call slowave_event(session_id, ...) for EVERY user message and EVERY assistant
  response — do not skip turns or wait until something seems "important".
- Durable decisions/facts: call slowave_remember(content, project=<name>) — high-salience path,
  no session_id required.
- Lookups: slowave_recall(query, project=<name>). Cite returned ids as [sch_xxx] or [epi_xxx].
- Task end: call slowave_session_end(session_id) to encode the session into memory.
```

## Session lifecycle

```
# 1. Build a cue from the current task/chat state.
current_task = "Fix the execute_sql Pydantic AI retry bug"
application = "claude-code"

# Optional coding/workspace cue. Generic chatbots can omit this and rely on
# query/topics/entities instead.
project = basename(cwd)   # e.g. "my-repo", optional

# 2. Load prior memory and start session
slowave_context(query=current_task, application=application)  →  working-memory brief
slowave_session_start(agent="claude-code", project=project)  →  session_id

  slowave_event(session_id, "user_message",      "…")
  slowave_event(session_id, "assistant_message", "…")
  slowave_event(session_id, "decision",          "We'll use SQLite.")
  slowave_remember("We use SQLite for this project", type="decision", project=project)

slowave_session_end(session_id)   # fast, no LLM — episodes form immediately
```

Consolidation (prototype clustering → latent schemas) is decoupled. Run in the background:

```bash
slowave worker --interval 300 &   # every 5 min, detached
slowave worker --once             # single pass (after a long session)
```

## Monitor with the local dashboard

Run the dashboard while using an agent to inspect live memory health, MCP
processes, sessions, schemas, DB integrity, recall results, and the schema graph:

```bash
slowave dashboard
# open http://127.0.0.1:8765
```

If the default port is busy:

```bash
slowave dashboard --port 8766 --no-open
```

The **Processes** tab is useful when multiple Cline/IDE sessions spawn separate
`slowave-mcp` processes. The **Schema Graph** tab visualizes explicit schema
relations and can be filtered by status, project, and minimum salience.

See [dashboard.md](dashboard.md) for the full dashboard guide.

## MCP tools

| Tool | Description |
|---|---|
| `slowave_session_start(agent?, project?)` | Begin a session, returns `session_id` |
| `slowave_event(session_id, type, content)` | Log a turn |
| `slowave_session_end(session_id)` | Close session — fast, no LLM |
| `slowave_recall(query, top_k?, evidence?)` | Semantic recall |
| `slowave_remember(content, type?, project?)` | Explicit durable memory |
| `slowave_context(query?, application?, topics?, entities?, project?, limit?, mode?)` | Gated working-memory brief for task/chat start |
| `slowave_consolidate()` | Trigger consolidation manually |
| `slowave_stats()` | Episode / prototype / schema counts |

**Event types:** `user_message` `assistant_message` `tool_call` `tool_result` `decision` `error` `task_complete` `task_failed`

**Memory types for `slowave_remember`:** `fact` `preference` `decision` `constraint` `procedure` `lesson` `warning`

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `SLOWAVE_DB` | `~/.slowave/slowave.db` | SQLite file path |
| `SLOWAVE_PROJECT` | *(none)* | Optional fallback workspace/project cue for coding-agent integrations |
| `SLOWAVE_MODEL` | `qwen2.5:7b-instruct` | Only used with `--schema-mode llm` |
| `SLOWAVE_OLLAMA_URL` | `http://localhost:11434` | Only used with `--schema-mode llm` |
| `OPENROUTER_API_KEY` | *(none)* | Cloud LLM backend (legacy) |

For the brain-only default, only `SLOWAVE_DB` is relevant.

## Working-memory context gate

`slowave_context` is intentionally stricter than `slowave_recall`. Recall is a
broad hippocampal/associative lookup; context is the small set of memories that
enters the downstream agent's active prompt. The gate uses a brain-like
activation/inhibition step:

1. collect candidate schemas from global salience, FTS/embedding matches for the
   current query/topic/entity cue, and optional environment cues such as
   project/workspace;
2. suppress memories that should not enter default prompt context, such as raw
   transcript-like `User:`/`Assistant:` summaries, `latent` schemas, schemas
   marked `injectable=false`, `needs_review`, or assistant/tool-result summaries;
3. compute activation from cue/topic/entity overlap, salience, stability,
   memory layer, source quality, and optional project match;
4. enforce a small working-memory budget before rendering compact bullets.

For generic chatbots, pass the current user message as `query` and optional
high-level `topics`/`entities`:

```python
slowave_context(
    query="Can you help me plan meals for next week?",
    application="chatbot",
    topics=["food", "meal planning"],
)
```

For coding agents, `project` can be supplied as an extra environmental cue, but
it is not required and is not a hardcoded namespace rule:

```python
slowave_context(
    project="cimmeria",
    query="Fix the execute_sql Pydantic AI retry bug",
    application="cline-tui",
)
```

Use `mode="debug"` to inspect activation traces and suppression reasons while
tuning the memory system. Use `slowave_recall` when the user explicitly asks to
search memory or inspect verbose evidence.
