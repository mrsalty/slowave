# OpenCode + Slowave — quick-ref

Full guide: **[../../docs/install.md](../../docs/install.md)**

---

## Setup

```bash
pipx install slowave
slowave setup --client opencode
```

`slowave setup` handles everything automatically:
- Creates or patches OpenCode global config at `~/.config/opencode/opencode.json`
- Registers Slowave as a remote MCP server under the `mcp` key
- Writes a Slowave-owned lifecycle instruction file
- Registers the instruction file in OpenCode's `instructions` config
- Installs the background worker service

Then start the daemon and restart OpenCode:

```bash
slowave serve start
```

---

## What gets configured

| What | Where |
|---|---|
| MCP server (remote) | `~/.config/opencode/opencode.json` → `mcp.slowave` |
| Lifecycle instructions | `~/.config/opencode/slowave-instructions.md` (registered via `instructions` key) |
| Background worker | launchd (macOS) / systemd (Linux) / Task Scheduler (Windows) |

---

## Lifecycle instructions

`slowave setup` injects the lifecycle block into `~/.config/opencode/slowave-instructions.md`
and registers it in OpenCode's config under the `instructions` array. OpenCode will pick it
up automatically on next launch.

**Full lifecycle documentation:** [docs/install.md#lifecycle-instruction-block](../../docs/install.md#lifecycle-instruction-block)

---

## Manual MCP config (if `slowave setup` didn't work)

Edit `~/.config/opencode/opencode.json` (create it if it doesn't exist):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "slowave": {
      "type": "remote",
      "url": "http://127.0.0.1:8766/mcp",
      "enabled": true
    }
  },
  "instructions": [
    "/absolute/path/to/slowave-instructions.md"
  ]
}
```

Make sure the daemon is running (`slowave serve start`). Restart OpenCode after editing.

---

## Verify

Ask OpenCode:

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
| Tools don't appear | Run `slowave serve start`, then `slowave serve status`; restart OpenCode |
| Tools appear but aren't called | `~/.config/opencode/slowave-instructions.md` block missing — re-run `slowave setup` |
| Sessions are empty | Verify `slowave-instructions.md` is present and registered in `instructions` — re-run `slowave setup` |
| Config not detected | Ensure `~/.config/opencode/opencode.json` exists and has a `mcp.slowave` entry with `"type": "local"` |

---

## Design notes

- OpenCode uses the **`mcp`** config key (not `mcpServers` like Claude/Cline/Cursor).
- Remote MCP servers use `"type": "remote"` with a `"url"` field.
- Lifecycle instructions use a **Slowave-owned file** (`slowave-instructions.md`) registered through OpenCode's `instructions` array — this avoids modifying `AGENTS.md` and keeps setup/uninstall clean.
- OpenCode connects to the **same HTTP daemon** (`slowave serve start`) as all other clients — no per-session subprocess overhead.