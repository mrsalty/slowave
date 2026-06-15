# Claude Code + Slowave — quick-ref

Full guide: **[../../docs/install.md](../../docs/install.md)**

---

## Setup

```bash
pipx install slowave
slowave setup --client claude-code
```

`slowave setup` handles everything automatically:
- Adds the MCP server entry to `~/.claude.json` (user-scope MCP registry)
- Injects `UserPromptSubmit` + `Stop` enforcement hooks into `~/.claude/settings.json` (fire every turn)
- Injects the lifecycle instruction block into `~/.claude/CLAUDE.md`
- Installs the background worker service

Restart Claude Code, then [verify](#verify).

---

## What gets configured

| What | Where |
|---|---|
| MCP server | `~/.claude.json` (user-scope MCP registry) |
| Lifecycle instructions | `~/.claude/CLAUDE.md` |
| Enforcement hooks | `UserPromptSubmit` + `Stop` in `~/.claude/settings.json` |
| Background worker | launchd (macOS) / systemd (Linux) / Task Scheduler (Windows) |

---

## Lifecycle instructions

`slowave setup` injects the lifecycle block into `~/.claude/CLAUDE.md` and installs enforcement hooks.

**Full lifecycle documentation:** [docs/install.md#lifecycle-instruction-block](../../docs/install.md#lifecycle-instruction-block)

---

## Manual MCP config (if `slowave setup` didn't work)

Edit `~/.claude.json` (create it if it doesn't exist):

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

Make sure the daemon is running (`slowave serve start`). Restart Claude Code after editing.

---

## Verify

Ask Claude Code:

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
| Tools don't appear | Run `slowave serve start`, then `slowave serve status`; restart Claude Code |
| Tools appear but aren't called | `CLAUDE.md` block or hooks missing — re-run `slowave setup` |
| Sessions are empty | Hooks should enforce this on every turn; check `~/.claude/settings.json` has the hook entries |
