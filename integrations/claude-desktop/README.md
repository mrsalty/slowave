# Claude Desktop + Slowave — quick-ref

Full guide: **[../../docs/install.md](../../docs/install.md)**

---

## Setup

```bash
pipx install slowave
slowave setup --client claude-desktop
```

Then upload the Slowave Skill once (see below) and restart Claude Desktop.

---

## What `slowave setup` configures automatically

| What | Where |
|---|---|
| MCP server | `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) |
| Background worker | launchd user service (macOS) / systemd (Linux) / Task Scheduler (Windows) |

---

## Add Custom Instructions (required)

`slowave setup` handles MCP config and the worker. For Claude Desktop, lifecycle instructions must be added manually — the Custom Instructions field is stored server-side and has no automation path.

**Settings → General → Instructions for Claude** — paste this:

```
At the start of every new conversation, before your first word, call:
  slowave_session_start(agent="claude-desktop", project=null)
  slowave_event(session_id, "user_message", <verbatim first message>)
  slowave_context(query=<first message>, application="claude-desktop", limit=8)
Do not respond until all three calls complete.
Log every exchange with slowave_event. End each conversation with
slowave_event(task_complete/failed, <outcome>) then slowave_session_end(session_id).
```

`slowave setup` prints this block so you can copy it directly.

---

## Manual MCP config (if `slowave setup` didn't work)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```jsonc
{
  "mcpServers": {
    "slowave": {
      "command": "/absolute/path/to/slowave-mcp"
    }
  }
}
```

Use the path from `which slowave-mcp`. Restart Claude Desktop after editing.

---

## Verify

Ask Claude Desktop:

```text
Remember that my preferred temporary food is spaghetti.
```

Then in a terminal:

```bash
slowave stats
slowave recall "what is my favourite food" --top-k 5 --evidence
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tools don't appear | Check MCP path (`slowave setup --dry-run`), check JSON syntax, restart Claude Desktop |
| Tools appear but aren't called | Re-run `slowave setup` (re-installs skill), then restart Claude Desktop |
| Sessions are empty | Confirm Claude is calling `slowave_event` during work; check skill is enabled in Settings |
| Stale MCP path after `brew upgrade` | Re-run `slowave setup` — it detects and fixes the stale path |
