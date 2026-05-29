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

## Upload the Slowave Skill (required, one-time)

Claude Desktop resets its skills directory on each launch, so the Skill must be uploaded via the UI. `slowave setup` prints the file path.

1. Open Claude Desktop → **Settings** → **Connectors** → **Customize** → **Skills**
2. Click **Create** → **Upload**
3. Select the `slowave.skill` file — path printed by `slowave setup`, or download:
   [slowave.skill](https://github.com/mrsalty/slowave/raw/main/integrations/claude-desktop/slowave.skill)
4. Restart Claude Desktop

This is a one-time step — Claude Desktop persists uploaded skills across restarts.

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
