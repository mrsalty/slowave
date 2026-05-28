# Using Slowave with AI clients

Slowave exposes an MCP server (`slowave-mcp`) so MCP-aware clients can use local long-term memory. It is not specific to coding agents: the same memory system can be used from Claude Code, Cline, and Claude Desktop.

The important rule is:

> MCP makes Slowave tools available; prompt/rules injection makes the client use them.

For the fastest setup, use the client-specific guides in [integrations/](../integrations/). For copy/paste client rules, see [agent-enforcement.md](agent-enforcement.md). For installation and MCP config locations, see [install.md](install.md). For Claude Desktop, the tested instruction path is a Skill upload after MCP setup.

## Supported public examples

| Client | `agent` / `application` | MCP config | Instruction surface |
|---|---|---|---|
| Claude Code | `claude-code` | `~/.claude/settings.json` | global/user `~/.claude/CLAUDE.md` and/or repo `CLAUDE.md` |
| Cline | `cline-tui` | Cline MCP settings JSON | global `~/.clinerules` or repo `.clinerules` |
| Claude Desktop | `claude-desktop` | macOS: `~/Library/Application Support/Claude/claude_desktop_config.json` | Upload [`integrations/claude-desktop/slowave.skill`](../integrations/claude-desktop/slowave.skill) via Settings -> Connectors -> Customize -> Skills -> Create -> Upload |

## Register the MCP server

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

`SLOWAVE_DB` defaults to `~/.slowave/slowave.db` if omitted. Set it only when you intentionally want a different shared memory database.

## Required lifecycle

At the start of each task or chat session:

```text
slowave_session_start(agent=<client-id>, project=<repo-or-domain-or-null>) -> session_id
slowave_event(session_id, "user_message", <self-contained user request>)
slowave_context(query=<current task/message>, application=<client-id>, project=<optional repo/domain>, topics=[...], entities=[...], limit=8, mode="default")
```

During the task:

```text
slowave_event(session_id, "assistant_message", ...)
slowave_event(session_id, "tool_call", ...)
slowave_event(session_id, "tool_result", ...)
slowave_event(session_id, "decision", ...)
slowave_event(session_id, "discovery", ...)
slowave_event(session_id, "error", ...)
```

For durable explicit memories:

```text
slowave_remember(content=<fact/preference/decision/etc>, type=<type>, project=<optional scope>)
```

At the end:

```text
slowave_event(session_id, "task_complete", ...)
# or slowave_event(session_id, "task_failed", ...)
slowave_session_end(session_id)
```

Do **not** call `slowave_recall` by default after `slowave_context`. `slowave_context` is the scoped working-memory injection path. `slowave_recall` is broad memory/evidence search and can intentionally return verbose or cross-domain history.

## MCP tools

| Tool | Description |
|---|---|
| `slowave_session_start(agent?, project?)` | Begin a session; returns `session_id` |
| `slowave_event(session_id, type, content)` | Log user/assistant/tool/decision/error/completion events |
| `slowave_session_end(session_id)` | Close the session and form episodes immediately |
| `slowave_context(query?, application?, topics?, entities?, project?, limit?, mode?)` | Gated working-memory brief for prompt injection |
| `slowave_recall(query, top_k?, evidence?)` | Broad semantic recall with optional evidence |
| `slowave_remember(content, type?, project?)` | Explicit high-salience durable memory |
| `slowave_consolidate()` | Trigger replay/consolidation manually |
| `slowave_stats()` | Episode/prototype/schema counts |

Common event types:

```text
user_message
assistant_message
tool_call
tool_result
decision
discovery
error
task_complete
task_failed
```

Memory types for `slowave_remember`:

```text
fact
preference
decision
constraint
procedure
task
open_question
warning
lesson
artifact
```

## Working-memory context gate

`slowave_context` is intentionally stricter than `slowave_recall`. Recall is a broad hippocampal/associative lookup; context is the small set of memories that enters the downstream client prompt.

The gate:

1. collects candidate schemas from query/topic/entity cues, optional project/domain cues, lexical matches, embedding matches, and salience;
2. suppresses memories that should not enter default prompt context, such as transcript-like summaries, non-injectable schemas, review-needed schemas, and assistant/tool-result summaries;
3. computes activation from cue overlap, salience, stability, memory layer, source quality, and optional project/domain match;
4. enforces a small working-memory budget before rendering compact bullets.

Example for Claude Desktop or another generic chat surface:

```python
slowave_context(
    query="Can you help me plan meals for next week?",
    application="claude-desktop",
    topics=["food", "meal planning"],
)
```

Example for a coding task:

```python
slowave_context(
    project="my-repo",
    query="Fix the execute_sql Pydantic AI retry bug",
    application="claude-code",
)
```

Use `mode="debug"` to inspect activation traces and suppression reasons while tuning. Use `slowave_recall` when the user explicitly asks to search memory or inspect provenance.

## Monitor with the local dashboard

```bash
slowave dashboard
# open http://127.0.0.1:8765
```

The dashboard shows memory stats, DB health, local Slowave/MCP processes, schemas, recall results, and schema graph filters.
