# Cursor + Slowave — quick-ref

Full guide: **[../../docs/install.md](../../docs/install.md)**

---

## Setup

```bash
pipx install slowave
slowave setup --client cursor
```

`slowave setup` handles the MCP server and background worker automatically.
One manual step remains: add the lifecycle instructions to Cursor.

---

## Step 1 — Add Rules for AI (required)

Open Cursor → **Settings → Rules for AI** (or add a `.cursorrules` file at the root of your project).

**Paste the lifecycle instructions from:** [docs/install.md#lifecycle-instruction-block](../../docs/install.md#lifecycle-instruction-block)

> **Why Rules for AI, not just the MCP config?**
> Cursor's MCP integration exposes tools but does not automatically instruct the AI _when_ to call them. The Rules for AI field fires on every request and ensures Slowave's session/event lifecycle is honoured from the first message.

---

## What `slowave setup` configures automatically

| What | Where |
|---|---|
| MCP server | `~/.cursor/mcp.json` |
| Background worker | launchd user service (macOS) / systemd (Linux) / Task Scheduler (Windows) |

---

## Manual MCP config (if `slowave setup` didn't work)

Edit `~/.cursor/mcp.json` (create it if missing):

```jsonc
{
  "mcpServers": {
    "slowave": {
      "command": "/absolute/path/to/slowave-mcp"
    }
  }
}
```

Use the path from `which slowave-mcp`. Restart Cursor after editing.

---

## Verify

Ask Cursor (with a model that supports tool use):

```text
Remember that my preferred food is spaghetti.
```

Then in a terminal:

```bash
slowave stats
slowave recall "what is my favourite food"
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tools don't appear | Check MCP path (`slowave setup --dry-run`), check JSON syntax, restart Cursor |
| Tools appear but aren't called | Rules for AI block not set — complete Step 1 above |
| Sessions are empty | Confirm Rules for AI block is set — complete Step 1 above |
| Stale MCP path after `brew upgrade` | Re-run `slowave setup` — it detects and fixes the stale path |
