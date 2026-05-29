# Installing and setting up Slowave

This is the single authoritative guide for every install and client setup scenario.
Client-specific quick-ref cards live in [`integrations/`](../integrations/).

---

## The short version

```bash
pipx install slowave
slowave setup
slowave doctor
```

`slowave setup` detects your platform, patches every AI client config it finds (Claude Desktop, Claude Code, Cline), injects lifecycle instructions, and installs the background worker — in one shot. It is idempotent: safe to re-run at any time.

If something went wrong or you want to do it manually, read on.

---

## Requirements

- Python 3.10+
- macOS, Linux, or Windows
- CPU is enough — no GPU, Ollama, OpenRouter, or cloud service required

---

## Step 1 — Install

Choose one method. They all give you the same two binaries: `slowave` (CLI) and `slowave-mcp` (MCP server).

**pipx** *(recommended — isolated, no venv management)*

```bash
pipx install slowave
```

**pip**

```bash
pip install slowave
```

**Homebrew (macOS)**

```bash
brew tap mrsalty/slowave https://github.com/mrsalty/slowave
brew install slowave
```

**From source**

```bash
git clone https://github.com/mrsalty/slowave
cd slowave
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify the install:

```bash
which slowave        # e.g. /opt/homebrew/bin/slowave
which slowave-mcp    # e.g. /opt/homebrew/bin/slowave-mcp
slowave doctor       # checks Python, torch, faiss, embedding backend
slowave stats        # shows stored events / episodes / schemas
```

> **Important:** always use the absolute path from `which slowave-mcp` — not just `slowave-mcp` — when configuring MCP clients. Some clients run with a restricted PATH and will not find the binary otherwise.

Slowave stores data in `~/.slowave/slowave.db`. Set `SLOWAVE_DB=/absolute/path` only if you intentionally want a different database.

---

## Step 2 — Wire clients and start the worker

```bash
slowave setup
```

Run once after install. What it does:

| Action | Detail |
|---|---|
| MCP config | Patches `~/.claude/settings.json` (Claude Code), `~/Library/Application Support/Claude/claude_desktop_config.json` (Claude Desktop, macOS), and Cline's MCP settings JSON |
| Lifecycle instructions | Injects the mandatory Slowave block into `~/.claude/CLAUDE.md` (Claude Code) and `~/.clinerules` (Cline) |
| Enforcement hooks | Adds `UserPromptSubmit` + `Stop` hooks in `~/.claude/settings.json` so Claude Code always calls Slowave on every turn |
| Background worker | Installs a user service: launchd plist on macOS, systemd user service on Linux, Task Scheduler task on Windows |

`slowave setup` is **idempotent** — re-running it is always safe. It reports `–` for anything already up-to-date and only writes what has changed.

Options:

```
slowave setup --client [claude-code|claude-desktop|cline|all]  # default: all
              --no-worker       # skip worker service install
              --no-hooks        # skip Claude Code hooks
              --dry-run         # preview without writing anything
```

> **Claude Desktop:** `slowave setup` now installs the Slowave Skill automatically by writing it directly to Claude Desktop's skills directory. Just **restart Claude Desktop** after running `slowave setup` — no manual upload required.
>
> If automatic install fails (e.g. Claude Desktop has never been opened yet), `slowave setup` will print manual fallback instructions.

### Step 2a — Claude Desktop: restart after setup

After `slowave setup` completes, **restart Claude Desktop**. The Slowave Skill is installed automatically into:

```
~/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/
```

You can verify it appeared by opening **Settings → Connectors → Customize → Skills** — "slowave" should be listed and enabled.

**If the automatic install failed** (printed a warning), install it manually:

1. Open **Settings** → **Connectors** → **Customize** → **Skills**
2. Click **Create** → **Upload**
3. Select the `slowave.skill` file — path printed by `slowave setup`, or download from:
   https://github.com/mrsalty/slowave/raw/main/integrations/claude-desktop/slowave.skill

---

## Step 3 — Verify

After setup, ask your client:

```text
Remember that my temporary Slowave install test preference is chamomile tea.
```

Then in a terminal:

```bash
slowave stats
slowave recall "chamomile tea" --top-k 5 --evidence
```

A working setup produces:
1. Non-zero event/episode counts in `slowave stats`
2. The chamomile tea memory in recall results

If it doesn't work, see [Troubleshooting](#troubleshooting) below.

---

## Manual setup (without `slowave setup`)

Use this if you prefer to configure things by hand, or if `slowave setup` can't find your client.

### What every client needs

Every client requires exactly three things:

1. **MCP server configuration** — so the `slowave_*` tools appear in the client
2. **Lifecycle instructions** — so the client actually calls those tools
3. **Background worker** — so episodes consolidate into durable schemas

MCP configuration alone is not sufficient. A client that can see the tools but has no instructions to call them will produce empty or sparse memory.

### MCP config block

```jsonc
{
  "mcpServers": {
    "slowave": {
      "command": "/absolute/path/to/slowave-mcp"
    }
  }
}
```

Replace `/absolute/path/to/slowave-mcp` with the output of `which slowave-mcp`.

| Client | Config file |
|---|---|
| Claude Code | `~/.claude/settings.json` |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Cline (VS Code / Cursor, macOS) | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` |

### Lifecycle instruction block

Paste this into the appropriate location for each client (see table below).

```md
## Slowave memory

Use Slowave MCP tools as long-term memory for every task/session.

Mandatory lifecycle:
1. First call: `slowave_session_start(agent="<client-id>", project="<repo-or-null>")` — store the returned `session_id`.
2. Log the user request: `slowave_event(session_id, "user_message", "<self-contained request>")`.
3. Load working memory: `slowave_context(query="<current task>", application="<client-id>", project="<repo-or-null>", limit=8)`.
4. During work: call `slowave_event(session_id, type, content)` for every meaningful message, decision, tool call/result, discovery, error, and completion.
5. End every session: `slowave_event(session_id, "task_complete"|"task_failed", "<outcome>")` then `slowave_session_end(session_id)`.

Event content = 1-3 self-contained sentences (reason + result). Not vague notes like "ran command".

Use `slowave_remember(content, type, project)` for durable facts, preferences, decisions, constraints, warnings, lessons.
Use `slowave_context` for default priming. Use `slowave_recall` only when broad history is explicitly needed.

Anti-patterns to avoid:
- Starting/ending a session with no `slowave_event` calls in between.
- Batching all events at the end of a session.
- Forgetting or changing the returned `session_id`.
```

**Where to put it:**

| Client | Location | `agent` value |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` (global) or repo `CLAUDE.md` | `claude-code` |
| Claude Desktop | Installed automatically by `slowave setup`; or upload manually — see [Step 2a](#step-2a--claude-desktop-restart-after-setup) | `claude-desktop` |
| Cline | `~/.clinerules` (global) or repo `.clinerules` | `cline-tui` |

### Background worker

The worker runs offline replay and consolidation so episodes become durable schemas.

**One-shot (for testing):**
```bash
slowave worker --once
```

**Persistent (recommended for daily use):**

*macOS — launchd:*

Create `~/Library/LaunchAgents/com.slowave.worker.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>com.slowave.worker</string>
    <key>ProgramArguments</key>
    <array>
      <string>/opt/homebrew/bin/slowave</string>
      <string>worker</string>
      <string>--interval</string>
      <string>300</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/tmp/slowave-worker.log</string>
    <key>StandardErrorPath</key><string>/tmp/slowave-worker.err</string>
  </dict>
</plist>
```

Replace `/opt/homebrew/bin/slowave` with the output of `which slowave`, then:

```bash
launchctl load ~/Library/LaunchAgents/com.slowave.worker.plist
launchctl list | grep slowave   # should show a pid
```

To stop/uninstall:

```bash
launchctl unload ~/Library/LaunchAgents/com.slowave.worker.plist
```

*Linux — systemd user service:*

Create `~/.config/systemd/user/slowave-worker.service`:

```ini
[Unit]
Description=Slowave background consolidation worker

[Service]
ExecStart=/usr/local/bin/slowave worker --interval 300
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

Replace `/usr/local/bin/slowave` with the output of `which slowave`, then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now slowave-worker
systemctl --user status slowave-worker
```

*Windows:* `slowave setup` handles Task Scheduler automatically. Run it with `--client all` or `--client claude-desktop`.

Verify the worker is running:

```bash
slowave status
tail -f /tmp/slowave-worker.log   # macOS launchd
```

---

## Dashboard

```bash
slowave dashboard
# open http://127.0.0.1:8765
```

Read-only local web UI. Shows DB health, Slowave/MCP processes, schemas, a recall playground, and the schema graph.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Client doesn't show Slowave tools | MCP path wrong or client not restarted | Run `slowave setup --dry-run` to check the configured path; restart the client after any config change |
| Client sees tools but never calls them | Lifecycle instructions missing | Run `slowave setup` — it injects `CLAUDE.md`, `.clinerules`, and Claude Code hooks |
| Claude Desktop sees tools but doesn't use them | Skill not installed or Claude Desktop not restarted | Re-run `slowave setup` (installs skill automatically), then restart Claude Desktop — see [Step 2a](#step-2a--claude-desktop-restart-after-setup) |
| Sessions exist but memory is empty | Client starts/ends sessions with no events | Verify the client is calling `slowave_event` during work; Claude Code hooks enforce this on every turn |
| Recall returns nothing or stale results | Worker not running, or `slowave_recall` used as default | Run `slowave worker --once`; use `slowave_context` for default priming, not `slowave_recall` |
| Schemas don't appear | Worker/consolidation not running | Run `slowave worker --once` or check the service is active (`launchctl list | grep slowave`) |
| `slowave setup` can't find `slowave-mcp` | Binary not on PATH | Run `which slowave-mcp`; if empty, re-install or use the absolute path |
| Stale versioned Cellar path after `brew upgrade` | Pre-v0.1.8 setup wrote the resolved Cellar path instead of the stable symlink | Re-run `slowave setup` — it detects the mismatch and rewrites the config with the stable `/opt/homebrew/bin/slowave-mcp` symlink |
