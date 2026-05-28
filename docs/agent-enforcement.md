# Making AI clients use Slowave consistently

Slowave works best when the client treats memory as part of its lifecycle, not as an optional lookup tool. MCP configuration only makes the `slowave_*` tools available. It does **not** force the model to call them.

To get consistent memory, configure both layers:

1. **MCP tool availability**: register `slowave-mcp` in the client MCP config.
2. **Prompt/rules enforcement**: add explicit Slowave lifecycle rules to the instruction surface the client reads.

For now the public examples are limited to Claude Code, Cline, and Claude Desktop. For fastest setup, use [../integrations/](../integrations/).

## Public compact rule

The user's local `.clinerules` can be longer; this compact public form keeps the parts that matter for reliable memory without overwhelming first-time users.

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

## Client-specific instruction locations

| Client | Instruction location | MCP config location | Recommended ids |
|---|---|---|---|
| Claude Code | global/user `~/.claude/CLAUDE.md` and/or repo `CLAUDE.md` | `~/.claude/settings.json` | `agent="claude-code"`, `application="claude-code"` |
| Cline | global `~/.clinerules` or repo `.clinerules` | Cline MCP settings JSON | `agent="cline-tui"`, `application="cline-tui"` |
| Claude Desktop | Upload [`integrations/claude-desktop/slowave.skill`](../integrations/claude-desktop/slowave.skill) via Settings -> Connectors -> Customize -> Skills -> Create -> Upload | macOS: `~/Library/Application Support/Claude/claude_desktop_config.json` | `agent="claude-desktop"`, `application="claude-desktop"` |

## Claude Code block

```md
## Slowave memory

Use Slowave MCP tools as long-term memory for every task/session.

Mandatory lifecycle:
1. First Slowave call: `slowave_session_start(agent="claude-code", project="<repo-name>")` and store the returned `session_id`.
2. Immediately log the user request: `slowave_event(session_id, "user_message", "<self-contained request>")`.
3. Load working memory: `slowave_context(query="<task>", application="claude-code", project="<repo-name>", topics=[...], entities=[...], limit=8, mode="default")`.
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

## Cline block

```md
## Slowave memory

Use Slowave MCP tools as long-term memory for every task/session.

Mandatory lifecycle:
1. First Slowave call: `slowave_session_start(agent="cline-tui", project="<repo-name-or-null>")` and store the returned `session_id`.
2. Immediately log the user request: `slowave_event(session_id, "user_message", "<self-contained request>")`.
3. Load working memory: `slowave_context(query="<current task>", application="cline-tui", project="<repo-name-or-null>", topics=[...], entities=[...], limit=8, mode="default")`.
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

## Claude Desktop

For Claude Desktop, use the packaged Skill rather than pasting instructions manually:

1. Configure MCP in `~/Library/Application Support/Claude/claude_desktop_config.json`.
2. Upload [`integrations/claude-desktop/slowave.skill`](../integrations/claude-desktop/slowave.skill): Settings -> Connectors -> Customize -> Skills -> Create -> Upload.

The Skill contains the same compact lifecycle, adapted to:

```text
agent="claude-desktop"
application="claude-desktop"
```

## Verification checklist

After configuring a client, run one small task and verify:

1. `slowave_stats()` count increases after the task ends.
2. The dashboard shows a new session/episodes.
3. The session has at least one `user_message` and one `assistant_message`.
4. `slowave_context` was called with a task-specific `query` and correct `application`.
5. No default rule forces `slowave_recall` after every context call.
6. A follow-up task can recall or receive the relevant memory through context.

Useful CLI checks:

```bash
slowave status
slowave stats
slowave dashboard --no-open
slowave recall "<thing you just asked the client to remember>" --top-k 5
```

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Client never calls Slowave | MCP server is configured, but rules are missing | Add lifecycle rules to the client's instruction surface |
| Empty sessions | Client starts/ends sessions but does not call `slowave_event` | Require immediate user event and event logging during work |
| Cross-domain/noisy context | Client uses `slowave_recall` as default priming | Use `slowave_context` for working memory; reserve recall for broad search |
| Events are useless later | Content says only “ran command” or “fixed bug” | Require 1-3 self-contained sentences with reason/result |
| Wrong memories surface | Missing or stale `project`, `query`, `topics`, or `entities` cues | Pass the current task/message as `query` and use optional domain/project cues |
| Client loses session id | Rules do not say to store/reuse `session_id` | Explicitly require reusing the returned `session_id` |
