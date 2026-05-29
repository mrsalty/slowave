# Claude Desktop + Slowave — quick-ref

Full guide: **[../../docs/install.md](../../docs/install.md)**

---

## Setup

```bash
pipx install slowave
slowave setup --client claude-desktop
```

`slowave setup` configures the MCP server and background worker automatically.
One manual step remains: add the lifecycle instructions to Claude Desktop.

---

## Step 1 — Add Custom Instructions (required)

Open Claude Desktop → **Settings → General → Instructions for Claude**

Copy and paste the entire block below, then click Save:

```
At the start of every new conversation, before your first word:
1. slowave_session_start(agent="claude-desktop", project=null) — store session_id
2. slowave_event(session_id, "user_message", "<verbatim first message>")
3. slowave_context(query="<first message>", application="claude-desktop", limit=8)
Do not respond until all three calls complete.

During the conversation, call slowave_event for every meaningful exchange
(user_message, assistant_message, decision, error, discovery).

Before your last message:
4. slowave_event(session_id, "task_complete" or "task_failed", "<1-3 sentence outcome>")
5. slowave_session_end(session_id)
```

> **Why Custom Instructions, not a Skill?**
> Claude Desktop Skills fire from turn 2 onward. Custom Instructions fire before turn 1.
> The Custom Instructions field is stored server-side — `slowave setup` prints the same
> block so you can copy it directly from the terminal.

---

## What `slowave setup` configures automatically

| What | Where |
|---|---|
| MCP server | `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) |
| Background worker | launchd user service (macOS) / systemd (Linux) / Task Scheduler (Windows) |

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
| Tools don\'t appear | Check MCP path (`slowave setup --dry-run`), check JSON syntax, restart Claude Desktop |
| Tools appear but aren\'t called | Custom Instructions not set — complete Step 1 above |
| Only works from turn 2 | Custom Instructions not set (Skills fire too late) — complete Step 1 above |
| Sessions are empty | Confirm Claude is calling `slowave_event` during work |
| Stale MCP path after `brew upgrade` | Re-run `slowave setup` — it detects and fixes the stale path |
