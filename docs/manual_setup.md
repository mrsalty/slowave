# Manual Setup Guide

This guide walks through manual Slowave configuration for users who prefer not to use `slowave setup`, need to troubleshoot, or want fine-grained control.

> **Recommended:** Most users should use `slowave setup` — see [install.md](./install.md). This manual approach is for troubleshooting or customization.

---

## Prerequisites

1. Install Slowave: `pipx install slowave`
2. Verify binaries are available:
   ```bash
   which slowave
   slowave serve status
   ```
3. Note the **absolute paths** — you'll need them for config files.

---

## Step 1: Find Your Client Config Files

### Claude Desktop

**macOS:**
```bash
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Linux:**
```bash
~/.config/Claude/claude_desktop_config.json
```

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

### Claude Code

All platforms (MCP goes into the user-scope registry, **not** `settings.json`):
```bash
~/.claude.json
```

Hooks (`UserPromptSubmit` + `Stop`) go into:
```bash
~/.claude/settings.json
```

### Cline (VS Code)

**macOS:**
```bash
~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json
```

**Linux:**
```bash
~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json
```

**Windows:**
```
%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json
```

### Cline (Cursor)

Replace `Code` with `Cursor` in the paths above.

### Cursor (native MCP config)

All platforms:
```bash
~/.cursor/mcp.json
```

### Windsurf

All platforms:
```bash
~/.codeium/windsurf/mcp_config.json
```

---

## Step 2: Add MCP Server Entry

Edit the appropriate config file(s) and add Slowave to the `mcpServers` section.

**Before:**
```json
{
  "mcpServers": {}
}
```

**After:**
```json
{
  "mcpServers": {
    "slowave": {
      "type": "http",
      "url": "http://127.0.0.1:8766/mcp"
    }
  }
}
```

Make sure the daemon is running: `slowave serve start`.

**Important:** The Slowave HTTP daemon must be running before clients can connect. Start it with `slowave serve start`.

---

## Step 3: Add Lifecycle Instructions

See [install.md](./install.md) for the full lifecycle block text. Add it to:

| Client | Location | Notes |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | Prepend at top; use `agent="claude-code"` |
| Cline | `~/.cline/rules/slowave.md` | Prepend at top; use `agent="cline-tui"` |
| Windsurf | `~/.codeium/windsurf/memories/global_rules.md` | Prepend at top; use `agent="windsurf"` |
| Claude Desktop | Settings → General → Instructions for Claude | Manual paste required; use `agent="claude-desktop"` |
| Cursor | Settings → Rules for AI (or `.cursorrules` in repo root) | Manual paste required; use `agent="cursor"` |

For Claude Code, Cline, and Windsurf the block must be wrapped in `<!-- slowave-lifecycle-start -->` and `<!-- slowave-lifecycle-end -->` markers (for idempotent re-injection by `slowave setup`).

---

## Step 4: (Optional) Add Enforcement Hooks (Claude Code)

See [slowave_setup.md](./slowave_setup.md) for the full JSON structure to add to `~/.claude/settings.json`.

---

## Step 5: Install Background Worker

### macOS (launchd)

1. Create `~/Library/LaunchAgents/com.slowave.worker.plist` with:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
     <dict>
       <key>Label</key><string>com.slowave.worker</string>
       <key>ProgramArguments</key>
       <array>
         <string>/absolute/path/to/slowave</string>
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
2. Load: `launchctl load ~/Library/LaunchAgents/com.slowave.worker.plist`
3. Verify: `launchctl list | grep slowave`

### Linux (systemd)

1. Create `~/.config/systemd/user/slowave-worker.service` with:
   ```ini
   [Unit]
   Description=Slowave background consolidation worker
   After=network.target

   [Service]
   ExecStart=/absolute/path/to/slowave worker --interval 300
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=default.target
   ```
2. Enable: `systemctl --user daemon-reload && systemctl --user enable --now slowave-worker`
3. Verify: `systemctl --user status slowave-worker`

### Windows (Task Scheduler)

Run in PowerShell (replace path):
```powershell
$action = New-ScheduledTaskAction -Execute 'C:\Path\To\slowave.exe' -Argument 'worker --interval 300'
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'SlowaveWorker' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Start-ScheduledTask -TaskName 'SlowaveWorker'
```

---

## Step 6: Verify and Test

```bash
slowave doctor
```

Restart your client and test:
```
Remember that my preferred test food is spaghetti.
```

Then verify:
```bash
slowave recall "what is my favourite food" --top-k 5
```

---

## Troubleshooting

### MCP Server Not Found

Ensure the daemon is running with `slowave serve start`.

### Lifecycle Not Running

Ensure lifecycle block is at the **top** of `CLAUDE.md` or `.clinerules`.

### Worker Not Running

**macOS:** `launchctl list | grep slowave`  
**Linux:** `systemctl --user status slowave-worker`  
**Windows:** `Get-ScheduledTask -TaskName SlowaveWorker`

Check logs:
- **macOS:** `/tmp/slowave-worker.log`
- **Linux:** `journalctl --user -u slowave-worker -f`
- **Windows:** Task Scheduler → History tab

---

## Manual Uninstall

1. Remove `"slowave": {...}` from all client configs
2. Delete lifecycle blocks (between markers)
3. Delete hooks mentioning `SLOWAVE MANDATORY`
4. Stop worker:
   - **macOS:** `launchctl unload ~/Library/LaunchAgents/com.slowave.worker.plist && rm ~/Library/LaunchAgents/com.slowave.worker.plist`
   - **Linux:** `systemctl --user disable --now slowave-worker && rm ~/.config/systemd/user/slowave-worker.service`
   - **Windows:** `Unregister-ScheduledTask -TaskName SlowaveWorker -Confirm:$false`
5. `pipx uninstall slowave`
6. (Optional) `rm -rf ~/.slowave`

---

## Why Automated Setup Exists

If this felt tedious, that's why `slowave setup` exists! See [slowave_setup.md](./slowave_setup.md) for transparency.

---

## Next Steps

- 📚 [Full install guide](./install.md)
- 📋 [What gets modified](./slowave_setup.md)
- 🩺 Run `slowave doctor` regularly
- 💬 [GitHub Discussions](https://github.com/mrsalty/slowave/discussions)
