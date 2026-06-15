# Windsurf + Slowave — quick-ref

Full guide: **[../../docs/install.md](../../docs/install.md)**

---

## Setup

```bash
pipx install slowave
slowave setup --client windsurf
```

`slowave setup` handles everything automatically:
- Patches Windsurf's MCP config to connect to the Slowave HTTP daemon
- Injects the lifecycle instruction block into `~/.codeium/windsurf/memories/global_rules.md`
- Installs the background worker service

Restart / reload Windsurf, then [verify](#verify).

---

## What gets configured

| What | Where |
|---|---|
| MCP server | `~/.codeium/windsurf/mcp_config.json` |
| Lifecycle instructions | `~/.codeium/windsurf/memories/global_rules.md` |
| Background worker | launchd (macOS) / systemd (Linux) / Task Scheduler (Windows) |

---

## Lifecycle instructions

`slowave setup` injects the lifecycle block into `~/.codeium/windsurf/memories/global_rules.md`.
This file is Windsurf's **global rules** surface — always-on, injected into every Cascade conversation.

**Full lifecycle documentation:** [docs/install.md#lifecycle-instruction-block](../../docs/install.md#lifecycle-instruction-block)

---

## Manual MCP config (if `slowave setup` didn't work)

Edit `~/.codeium/windsurf/mcp_config.json` (create it if missing):

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

Make sure the daemon is running (`slowave serve start`). Restart Windsurf after editing.

---

## Verify

Ask Windsurf's Cascade:

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
| Tools don't appear | Run `slowave serve start`, then `slowave serve status`; restart Windsurf |
| Tools appear but aren't called | `global_rules.md` block missing — re-run `slowave setup` |
| Sessions are empty | Verify `global_rules.md` has the Slowave lifecycle block — re-run `slowave setup` |

