# Slowave Setup: What Gets Modified

This page documents what files and system configurations `slowave setup` modifies on your machine.

## TL;DR

`slowave setup` is **idempotent** (safe to re-run) and modifies only configuration files — no code injection, no system-wide changes, no PATH modifications. Everything is user-scoped and can be cleanly removed with `slowave cleanup`.

---

## Why Automated Setup?

Unlike simple MCP servers that only respond to calls, Slowave is a **stateful memory system** that requires:

1. **Lifecycle integration** — agents must open sessions, log events, close sessions
2. **Event logging** — meaningful interactions must be recorded  
3. **Background consolidation** — a worker process transforms events into memories
4. **Multiple touchpoints** — MCP config + instruction injection + system service

Manual setup would require ~8 steps across 4-5 files. `slowave setup` automates this while remaining:
- ✅ **Idempotent** — safe to re-run, only writes what changed
- ✅ **Transparent** — reports every file it touches, including backup paths
- ✅ **Inspectable** — `slowave doctor` shows current state
- ✅ **Backed up** — every config file is backed up before modification (one backup per file, kept until `slowave cleanup`)
- ✅ **Reversible** — `slowave cleanup` removes everything, including backup files

## Backup files

Before overwriting any config file, `slowave setup` creates a timestamped copy next to the original:

```
~/.claude.json.bak.20260611_142300
~/.claude/settings.json.bak.20260611_142300
~/.claude/CLAUDE.md.bak.20260611_142300
```

- The backup path is printed during setup so you can find it immediately.
- Only **one backup is kept per file** — re-running setup replaces the previous backup, not accumulates copies.
- Backups are **not deleted automatically after setup** — they stay until you run `slowave cleanup` or delete them manually.
- `slowave cleanup` removes all `*.bak.*` files from config directories as part of its normal flow.

To restore from a backup manually:

```bash
cp ~/.claude.json.bak.20260611_142300 ~/.claude.json
```

---

## Files Modified (by Platform)

### macOS

| File | Purpose | What Changes |
|------|---------|--------------|
| `~/.claude.json` | Claude Code MCP config | Adds `mcpServers.slowave` entry with binary path (user-scope MCP registry) |
| `~/.claude/settings.json` | Claude Code hooks | Adds `hooks.UserPromptSubmit` and `hooks.Stop` for lifecycle enforcement; removes stale `mcpServers` written by Slowave ≤0.4.2 |
| `~/.claude/CLAUDE.md` | Claude Code instructions | Prepends lifecycle block between `<!-- slowave-lifecycle-start/end -->` markers |
| `~/Library/Application Support/Claude/claude_desktop_config.json` | Claude Desktop MCP config | Adds `mcpServers.slowave` entry with binary path |
| `~/.clinerules` | Cline instructions | Prepends lifecycle block between markers |
| `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` | Cline MCP config | Adds `mcpServers.slowave` entry (if VS Code detected) |
| `~/.config/Cursor/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` | Cline MCP config | Adds `mcpServers.slowave` entry (if Cursor detected) |
| `~/.cursor/mcp.json` | Cursor native MCP config | Adds `mcpServers.slowave` entry |
| `~/.codeium/windsurf/mcp_config.json` | Windsurf MCP config | Adds `mcpServers.slowave` entry |
| `~/.codeium/windsurf/memories/global_rules.md` | Windsurf global rules | Prepends lifecycle block between markers (always-on) |
| `~/Library/LaunchAgents/com.slowave.worker.plist` | Background worker service | Creates launchd plist; loads with `launchctl` |

### Linux

| File | Purpose | What Changes |
|------|---------|--------------|
| `~/.claude.json` | Claude Code MCP config | Same as macOS |
| `~/.claude/settings.json` | Claude Code hooks | Same as macOS |
| `~/.claude/CLAUDE.md` | Claude Code instructions | Same as macOS |
| `~/.config/Claude/claude_desktop_config.json` | Claude Desktop MCP config | Adds `mcpServers.slowave` entry |
| `~/.clinerules` | Cline instructions | Same as macOS |
| `~/.config/Code/User/globalStorage/.../cline_mcp_settings.json` | Cline MCP config | Same as macOS |
| `~/.config/systemd/user/slowave-worker.service` | Background worker service | Creates systemd user service; enables with `systemctl --user` |

### Windows

| File | Purpose | What Changes |
|------|---------|--------------|
| `%USERPROFILE%\.claude.json` | Claude Code MCP config | Same as macOS |
| `%USERPROFILE%\.claude\settings.json` | Claude Code hooks | Same as macOS |
| `%USERPROFILE%\.claude\CLAUDE.md` | Claude Code instructions | Same as macOS |
| `%APPDATA%\Claude\claude_desktop_config.json` | Claude Desktop MCP config | Adds `mcpServers.slowave` entry |
| `%USERPROFILE%\.clinerules` | Cline instructions | Same as macOS |
| `%APPDATA%\Code\User\globalStorage\.../cline_mcp_settings.json` | Cline MCP config | Same as macOS |
| Task Scheduler | Background worker service | Registers `SlowaveWorker` task via PowerShell |

---

## What Gets Added to Config Files

### MCP Server Entry (all clients)

```json
{
  "mcpServers": {
    "slowave": {
      "type": "http",
  "url": "/absolute/path/to/slowave-mcp-http"
    }
  }
}
```

The path is detected automatically using `which slowave-mcp-http` (or fallback search in common install locations).

### Claude Code Hooks (Claude Code only)

Two echo-based enforcement hooks are added to ensure lifecycle compliance:

**UserPromptSubmit hook** (runs before Claude responds):
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "type": "http",
  "url": "echo 'SLOWAVE MANDATORY: Before writing your first word call: (1) derive goal=3-6 word verb-noun phrase e.g. implement-oauth-login fix-auth-bug refactor-db-layer, (2) slowave_activate(query=<verbatim task>,goal=<derived goal>,scope=project:<basename(cwd)>) store retrieval_id and session_id. Produce NO output until this call succeeds.'"
          }
        ]
      }
    ]
  }
}
```

**Stop hook** (runs when Claude finishes):
```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "type": "http",
  "url": "echo 'SLOWAVE MANDATORY: Before finishing this turn call: (1) if you used memories: slowave_reinforce(retrieval_id=<id>,feedback=useful|irrelevant|stale|wrong,outcome=success|partial|failure|unknown), (2) slowave_commit(scope=project:<basename(cwd)>,outcome=success|partial|failure|unknown). Do NOT end the turn without step 2.'"
          }
        ]
      }
    ]
  }
}
```

### Lifecycle Instructions Block

Added to `CLAUDE.md` and `.clinerules` between `<!-- slowave-lifecycle-start -->` and `<!-- slowave-lifecycle-end -->` markers. The block instructs agents on the 5-verb cognitive cycle:
- Priming working memory (`slowave_activate`)
- Encoding durable facts (`slowave_remember`)
- Mid-task retrieval (`slowave_recall`)
- Strengthening useful memories (`slowave_reinforce`)
- Closing the task episode (`slowave_commit`)

See [install.md](./install.md) for the full lifecycle block text.

---

## Background Worker Service

### macOS (launchd)

**File:** `~/Library/LaunchAgents/com.slowave.worker.plist`

Runs `slowave worker --interval 300` (consolidates every 5 minutes). Loaded automatically with `launchctl`.

**Verify:** `launchctl list | grep slowave`

### Linux (systemd)

**File:** `~/.config/systemd/user/slowave-worker.service`

Runs `slowave worker --interval 300`. Enabled automatically with `systemctl --user enable --now`.

**Verify:** `systemctl --user status slowave-worker`

### Windows (Task Scheduler)

**Task Name:** `SlowaveWorker`

Created via PowerShell. Triggers at user logon, restarts on failure.

**Verify:** `Get-ScheduledTask -TaskName SlowaveWorker`

---

## Daily Database Backup

`slowave setup` also installs a daily backup job that creates a gzip-compressed
snapshot of the SQLite database. Backups use SQLite's online `.backup()` API —
safe while the worker and MCP server are running.

### macOS (launchd)

**File:** `~/Library/LaunchAgents/com.slowave.backup.plist`

Runs `slowave backup` once per day at 03:00 via `StartCalendarInterval`.

**Verify:** `launchctl list com.slowave.backup`

### Linux (systemd timer)

**Files:**
- `~/.config/systemd/user/slowave-backup.service` (oneshot)
- `~/.config/systemd/user/slowave-backup.timer` (`OnCalendar=daily`)

**Verify:** `systemctl --user status slowave-backup.timer`

### Windows (Task Scheduler)

**Task Name:** `SlowaveBackup`

Runs `slowave backup` daily at 03:00.

**Verify:** `Get-ScheduledTask -TaskName SlowaveBackup`

Backups are stored in `~/.slowave/backups/` by default. The last 7 backups are
kept (configurable via `SLOWAVE_BACKUP_KEEP` or `--keep`).

---

## What Does NOT Get Modified

| ❌ Never touched | Why |
|-----------------|-----|
| Python packages | Slowave is installed via pip/pipx — no auto-upgrades, no surprise dependencies |
| Shell profiles (`.bashrc`, `.zshrc`, etc.) | No PATH modifications |
| System-wide configs (`/etc`, `/usr/local`) | User-scoped only |
| VSCode/Cursor settings.json | Only Cline's dedicated MCP settings file (not the editor's own settings) |
| Claude Desktop Custom Instructions | Server-side, cannot be automated — requires manual paste |
| Existing file content (outside markers) | Lifecycle blocks use markers; existing content is preserved |

---

## Verification

### Before `slowave setup`

```bash
slowave doctor  # checks installation only
```

### After `slowave setup`

```bash
slowave doctor  # now shows detected clients and their config status
```

### Preview Changes First

```bash
slowave setup --dry-run
```

Shows exactly what would be modified without writing any files.

---

## Removal

```bash
slowave uninstall --dry-run  # preview what will be removed
slowave uninstall            # actually remove
```

**What gets removed (ONLY Slowave-specific entries):**
- MCP server entry named `"slowave"` from all client configs
- Lifecycle instruction blocks between `<!-- slowave-lifecycle-start/end -->` markers
- Enforcement hooks containing `"SLOWAVE MANDATORY"` (Claude Code only)
- Background worker service files/tasks

**What is PRESERVED:**
- Other MCP servers in the same config
- Other hooks (e.g., `PreToolUse`, custom hooks)
- All other configuration keys
- File structure and formatting
- The SQLite database (`~/.slowave/slowave.db`)

The uninstall command uses **safe removal logic** that:
- ✅ Validates JSON before and after changes
- ✅ Only removes entries with Slowave-specific markers
- ✅ Preserves empty JSON structures (empty `mcpServers` object stays)
- ✅ Reports errors without leaving broken configs
- ✅ Never deletes entire files

Then uninstall the package:
```bash
pipx uninstall slowave
# or: pip uninstall slowave
# or: brew uninstall slowave
```

---

## Manual Setup Alternative

If you prefer manual configuration, see **[manual_setup.md](./manual_setup.md)** for step-by-step instructions.

---

## Trust & Transparency

- ✅ **Open Source** — [github.com/mrsalty/slowave](https://github.com/mrsalty/slowave)
- ✅ **Idempotent** — safe to re-run
- ✅ **Dry-run mode** — `slowave setup --dry-run`
- ✅ **Verification** — `slowave doctor` shows state
- ✅ **Reversible** — `slowave uninstall`
- ✅ **No telemetry** — no analytics, no data collection
- ✅ **Local-first** — all data stays on your machine

---

## Questions?

- 📚 [Full install guide](./install.md)
- 🛠️ [Manual setup guide](./manual_setup.md)
- 🩺 Run `slowave doctor` to check status
- 💬 [GitHub Discussions](https://github.com/mrsalty/slowave/discussions)
