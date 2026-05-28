# Installing Slowave

For the fastest client-specific walkthroughs, start with [integrations/](../integrations/).

Slowave has two different setup layers:

1. **Install the local binaries**: `slowave` and `slowave-mcp`.
2. **Wire an AI client correctly**: MCP config plus prompt/rules injection.

The second layer is mandatory for real long-term memory. MCP only exposes tools; it does not make a model call them. Slowave works at regime only when the client is explicitly instructed to start sessions, log events, load context, and end sessions.

## Requirements

- Python 3.10+
- macOS or Linux recommended
- CPU is enough for the default path
- No Ollama, OpenRouter, or other LLM backend required

The default memory path is brain-only: sentence-transformer embeddings, SQLite, FAISS, replay/consolidation, and geometry-based recall.

## 1. Install

### pipx recommended

```bash
pipx install slowave
```

Use `pipx` when you want the CLI and MCP server globally available without mixing dependencies into another project.

### pip inside an existing environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install slowave
```

### Homebrew

```bash
brew tap mrsalty/slowave
brew install slowave
```

### From source

```bash
git clone https://github.com/mrsalty/slowave
cd slowave
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
scripts/slowave-check.sh
```

## 2. Verify local commands

```bash
slowave --help
slowave-mcp --help
slowave stats
```

Find the MCP executable path. Use this absolute path in client config:

```bash
which slowave-mcp
```

Slowave stores data in `~/.slowave/slowave.db` by default. Set `SLOWAVE_DB=/absolute/path/to/slowave.db` only when you intentionally want a different memory database.

## 3. Configure MCP

Add `slowave-mcp` to the client MCP configuration.

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

Known client locations:

| Client | MCP config location |
|---|---|
| Claude Code | `~/.claude/settings.json` |
| Cline | Cline MCP settings JSON |
| Claude Desktop | macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`; then upload the Slowave Skill bundle |

Notes:

- Use an absolute executable path, not `slowave-mcp`, if the client runs with a restricted PATH.
- `KMP_DUPLICATE_LIB_OK`, `OMP_NUM_THREADS`, and `TOKENIZERS_PARALLELISM` avoid common local PyTorch/FAISS tokenizer/OpenMP issues.
- If multiple clients share the same default DB, they share the same long-term memory.

## 4. Inject the Slowave lifecycle prompt

Add a Slowave rule block to the instruction surface the client actually reads. For Claude Desktop, use the Skill upload path rather than relying only on a freeform custom instruction.

| Client | Instruction location |
|---|---|
| Claude Code | global/user `~/.claude/CLAUDE.md` and/or repo `CLAUDE.md` |
| Cline | global `~/.clinerules` or repo `.clinerules` |
| Claude Desktop | Settings -> Connectors -> Customize -> Skills -> Create -> Upload [`integrations/claude-desktop/slowave.skill`](../integrations/claude-desktop/slowave.skill) |

Use this minimal block:

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


### Claude Desktop Skill upload

After MCP is configured in Claude Desktop, upload the packaged Slowave Skill:

1. Open **Settings**.
2. Go to **Connectors**.
3. Click **Customize**.
4. Open **Skills**.
5. Click **Create**.
6. Click **Upload**.
7. Select [`integrations/claude-desktop/slowave.skill`](../integrations/claude-desktop/slowave.skill).

This is the tested Claude Desktop path for injecting the Slowave lifecycle instructions. Without the Skill upload, Claude Desktop may expose the MCP tools but not consistently call them.

Recommended ids:

| Client | `agent` / `application` |
|---|---|
| Claude Code | `claude-code` |
| Cline | `cline-tui` |
| Claude Desktop | `claude-desktop` |

## 5. Verify the integration

After configuring MCP and prompt injection, run a tiny task such as:

```text
Remember that my temporary Slowave install test preference is chamomile tea.
```

Then verify from a terminal:

```bash
slowave stats
slowave recall "chamomile tea" --top-k 5 --evidence
slowave dashboard --no-open
```

Expected signs of a working integration:

1. The client called `slowave_session_start`.
2. The first user request was logged with `slowave_event`.
3. The client called `slowave_context` with the current query.
4. The client logged at least one assistant response or task event.
5. The client called `slowave_session_end`.
6. `slowave stats` shows non-zero events/episodes after the task.

## 6. Run consolidation in the background

Episodes are created immediately on `slowave_session_end`. Distilled schemas are produced by replay/consolidation. For regular daily use, run a worker periodically:

```bash
slowave worker --interval 300
```

For a one-off pass after a long session:

```bash
slowave worker --once
# or
slowave consolidate
```

## 7. Inspect with the dashboard

```bash
slowave dashboard
# open http://127.0.0.1:8765
```

The dashboard is local and read-only. It shows DB health, Slowave/MCP processes, schemas, recall results, and the schema graph.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Client does not show Slowave tools | MCP path wrong or client not restarted | Use `which slowave-mcp`, use an absolute path, restart the client |
| Client sees tools but never calls them | Prompt/rules injection missing | Add the lifecycle block to `CLAUDE.md`, `.clinerules`, or custom instructions |
| Sessions exist but memory is empty | Client starts/ends sessions without events | Require immediate `user_message` and event logging during the task |
| Recall returns stale/noisy memories | Client uses `slowave_recall` as default priming | Use `slowave_context` for prompt injection; reserve recall for broad evidence search |
| Distilled schemas do not appear | Worker/consolidation not running | Run `slowave worker --once` or keep `slowave worker --interval 300` running |
| macOS OpenMP/tokenizer warnings | Local numeric/tokenizer libraries | Keep the env vars from the MCP config above |
