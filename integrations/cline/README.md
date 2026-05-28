# Cline + Slowave

Goal: configure Cline with Slowave long-term memory quickly.

Cline requires **both**:

1. MCP server configuration so the `slowave_*` tools are available.
2. `.clinerules` instructions so Cline consistently follows the memory lifecycle.

## 1. Install and verify Slowave

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

```bash
which slowave
which slowave-mcp
slowave --help
slowave-mcp --help
slowave stats
```

Copy the absolute path printed by `which slowave-mcp`.

## 2. Configure Cline MCP

Open Cline's MCP settings JSON and add or merge this block, replacing `/absolute/path/to/slowave-mcp` with your actual path:

```jsonc
{
  "mcpServers": {
    "slowave": {
      "command": "/absolute/path/to/slowave-mcp"
    }
  }
}
```

Restart/reload Cline after editing MCP settings.

## 3. Add `.clinerules`

Add this to global `~/.clinerules` or repo-local `.clinerules`:

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

## 4. Start the worker

Episodes are created immediately when each session ends. The worker performs offline replay/consolidation so those episodes become durable schemas for future `slowave_context` calls.

For quick testing, run this in a separate terminal:

```bash
slowave worker --interval 300
```

For daily use, install an auto-restarting user service. See [../../docs/install.md#run-consolidation-in-the-background](../../docs/install.md#run-consolidation-in-the-background).

## 5. Verify

Ask Cline:

```text
Remember that my temporary Slowave Cline test preference is chamomile tea.
```

Then run:

```bash
slowave stats
slowave recall "chamomile tea" --top-k 5 --evidence
slowave dashboard --no-open
```

Expected signs:

- Cline called `slowave_session_start`.
- It logged the user request with `slowave_event`.
- It called `slowave_context`.
- It logged work events during the task.
- It called `slowave_session_end`.
- `slowave recall "chamomile tea"` finds the test memory.
