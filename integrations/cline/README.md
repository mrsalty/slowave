# Cline + Slowave — quick-ref

Full guide: **[../../docs/install.md](../../docs/install.md)**

---

## Setup

```bash
pipx install slowave
slowave setup --client cline
```

`slowave setup` handles everything automatically:
- Patches Cline's MCP settings JSON to connect to the Slowave HTTP daemon
- Injects the lifecycle instruction block into `~/.cline/rules/slowave.md`
- Installs the background worker service

Then start the daemon and restart Cline:

```bash
slowave serve start
```

---

## What gets configured

| What | Where |
|---|---|
| MCP server (HTTP) | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` (VS Code, macOS) |
| Lifecycle instructions | `~/.cline/rules/slowave.md` |
| Background worker | launchd (macOS) / systemd (Linux) / Task Scheduler (Windows) |

---

## Lifecycle instructions

`slowave setup` injects the lifecycle block into `~/.cline/rules/slowave.md`.

**Full lifecycle documentation:** [docs/install.md#lifecycle-instruction-block](../../docs/install.md#lifecycle-instruction-block)

---

## Manual MCP config (if `slowave setup` didn't work)

Open Cline's MCP settings JSON and add or merge:

```jsonc
{
  "mcpServers": {
    "slowave": {
      "type": "http",
      "url": "http://127.0.0.1:8766/mcp"
    }
  }
}
```

Make sure the daemon is running (`slowave serve start`). Restart / reload Cline after editing.

---

## Verify

Ask Cline:

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
| Tools don't appear | Check MCP path (`slowave setup --dry-run`), restart Cline |
| Tools appear but aren't called | `~/.cline/rules/slowave.md` block missing — re-run `slowave setup` |
| Sessions are empty | Verify `~/.cline/rules/slowave.md` is present and contains the Slowave lifecycle block — re-run `slowave setup` |
