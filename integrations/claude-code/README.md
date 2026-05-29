# Claude Code + Slowave — quick-ref

Full guide: **[../../docs/install.md](../../docs/install.md)**

---

## Setup

```bash
pipx install slowave
slowave setup --client claude-code
```

`slowave setup` handles everything automatically:
- Patches `~/.claude/settings.json` with the MCP server block
- Injects `UserPromptSubmit` + `Stop` enforcement hooks (fire every turn)
- Injects the lifecycle instruction block into `~/.claude/CLAUDE.md`
- Installs the background worker service

Restart Claude Code, then [verify](#verify).

---

## What gets configured

| What | Where |
|---|---|
| MCP server | `~/.claude/settings.json` |
| Lifecycle instructions | `~/.claude/CLAUDE.md` |
| Enforcement hooks | `UserPromptSubmit` + `Stop` in `~/.claude/settings.json` |
| Background worker | launchd (macOS) / systemd (Linux) / Task Scheduler (Windows) |

---

## Manual MCP config (if `slowave setup` didn't work)

Edit `~/.claude/settings.json`:

```jsonc
{
  "mcpServers": {
    "slowave": {
      "command": "/absolute/path/to/slowave-mcp"
    }
  }
}
```

Use the path from `which slowave-mcp`. Restart Claude Code after editing.

---

## Verify

Ask Claude Code:

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
| Tools don't appear | Check MCP path (`slowave setup --dry-run`), restart Claude Code |
| Tools appear but aren't called | `CLAUDE.md` block or hooks missing — re-run `slowave setup` |
| Sessions are empty | Hooks should enforce this on every turn; check `~/.claude/settings.json` has the hook entries |
