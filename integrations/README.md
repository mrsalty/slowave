# Slowave — client integrations

Full install and setup guide: **[../docs/install.md](../docs/install.md)**

---

## Quick-start (all clients)

```bash
pipx install slowave
slowave setup
slowave doctor
```

`slowave setup` auto-configures every client it detects, injects lifecycle instructions, and installs the background worker. It is idempotent — safe to re-run.

> **Claude Desktop:** after `slowave setup`, **restart Claude Desktop** — the Skill is installed automatically. See [docs/install.md → Step 2a](../docs/install.md#step-2a--claude-desktop-restart-after-setup) if the automatic install failed.

---

## Client quick-ref cards

| Client | Quick-ref | What's different |
|---|---|---|
| Claude Desktop | [claude-desktop/README.md](claude-desktop/README.md) | Requires Skill upload (no hooks API) |
| Claude Code | [claude-code/README.md](claude-code/README.md) | CLAUDE.md + enforcement hooks |
| Cline | [cline/README.md](cline/README.md) | .clinerules injection |

Each card is a one-screen reminder of the client-specific steps. The full guide for every scenario is in [docs/install.md](../docs/install.md).
