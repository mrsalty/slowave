# Cline + Slowave — quick-ref

Full guide: **[../../docs/install.md](../../docs/install.md)**

---

## Setup

```bash
pipx install slowave
slowave setup --client cline
```

`slowave setup` handles everything automatically:
- Patches Cline's MCP settings JSON with the `slowave-mcp` server block
- Injects the lifecycle instruction block into `~/.clinerules`
- Installs the background worker service

Restart / reload Cline, then [verify](#verify).

---

## What gets configured

| What | Where |
|---|---|
| MCP server | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` (VS Code, macOS) |
| Lifecycle instructions | `~/.clinerules` |
| Background worker | launchd (macOS) / systemd (Linux) / Task Scheduler (Windows) |

---

## Manual MCP config (if `slowave setup` didn't work)

Open Cline's MCP settings JSON and add or merge:

```jsonc
{
  "mcpServers": {
    "slowave": {
      "command": "/absolute/path/to/slowave-mcp"
    }
  }
}
```

Use the path from `which slowave-mcp`. Restart / reload Cline after editing.

---

## Verify

Ask Cline:

```text
Remember that my temporary Slowave test preference is chamomile tea.
```

Then in a terminal:

```bash
slowave stats
slowave recall "chamomile tea" --top-k 5 --evidence
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tools don't appear | Check MCP path (`slowave setup --dry-run`), restart Cline |
| Tools appear but aren't called | `.clinerules` block missing — re-run `slowave setup` |
| Sessions are empty | Verify `.clinerules` is present and Cline is calling `slowave_event` during work |
