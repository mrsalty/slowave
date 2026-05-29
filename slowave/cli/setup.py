"""slowave setup — one-command post-install wiring.

Automates:
  1. Locating the slowave-mcp binary (absolute path).
  2. Patching MCP client configs (Claude Code, Claude Desktop, Cline).
  3. Injecting lifecycle instructions (CLAUDE.md, .clinerules) and
     UserPromptSubmit/Stop hooks into ~/.claude/settings.json.
  4. Installing the background worker as a user service
     (launchd on macOS, systemd on Linux, Task Scheduler on Windows).
  5. Running `slowave doctor` to verify the result.

All steps are idempotent — re-running is always safe.
"""

from __future__ import annotations

import importlib.resources
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import click

# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------

SYSTEM = platform.system()  # "Darwin", "Linux", "Windows"


def _home() -> Path:
    return Path.home()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _claude_settings_path() -> Path:
    return _home() / ".claude" / "settings.json"


def _claude_md_path() -> Path:
    return _home() / ".claude" / "CLAUDE.md"


def _clinerules_path() -> Path:
    return _home() / ".clinerules"


def _claude_desktop_config_path() -> Path:
    if SYSTEM == "Darwin":
        return _home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif SYSTEM == "Windows":
        appdata = os.environ.get("APPDATA", str(_home() / "AppData" / "Roaming"))
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", str(_home() / ".config"))
        return Path(xdg) / "Claude" / "claude_desktop_config.json"


def _cline_mcp_settings_path() -> Path:
    """VS Code / Cursor Cline MCP settings — best-effort detection."""
    if SYSTEM == "Darwin":
        candidates = [
            _home() / "Library/Application Support/Code/User/globalStorage"
            "/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
            _home() / "Library/Application Support/Cursor/User/globalStorage"
            "/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
        ]
    elif SYSTEM == "Windows":
        appdata = os.environ.get("APPDATA", str(_home() / "AppData" / "Roaming"))
        candidates = [
            Path(appdata) / "Code/User/globalStorage"
            "/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
            Path(appdata) / "Cursor/User/globalStorage"
            "/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
        ]
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", str(_home() / ".config"))
        candidates = [
            Path(xdg) / "Code/User/globalStorage"
            "/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
            Path(xdg) / "Cursor/User/globalStorage"
            "/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
        ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0] if candidates else _home() / "cline_mcp_settings.json"


# ---------------------------------------------------------------------------
# Skill file location
# ---------------------------------------------------------------------------

_SKILL_GITHUB_URL = (
    "https://github.com/mrsalty/slowave/raw/main"
    "/integrations/claude-desktop/slowave.skill"
)


def _find_skill_file() -> str | None:
    """Return the absolute path to the bundled slowave.skill, or None."""
    # 1. Installed package data (pip / pipx / brew)
    try:
        ref = importlib.resources.files("slowave") / "data" / "slowave.skill"
        with importlib.resources.as_file(ref) as p:
            if p.exists():
                return str(p)
    except Exception:
        pass
    # 2. Relative to this file (source / editable install)
    candidate = Path(__file__).parent.parent / "data" / "slowave.skill"
    if candidate.exists():
        return str(candidate)
    # 3. Common repo layout: repo-root/integrations/claude-desktop/slowave.skill
    repo_root = Path(__file__).parent.parent.parent
    candidate2 = repo_root / "integrations" / "claude-desktop" / "slowave.skill"
    if candidate2.exists():
        return str(candidate2)
    return None


def _skills_plugin_base() -> Path | None:
    """Return the skills-plugin base directory for Claude Desktop, or None."""
    if SYSTEM == "Darwin":
        base = _home() / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions" / "skills-plugin"
    elif SYSTEM == "Windows":
        appdata = os.environ.get("APPDATA", str(_home() / "AppData" / "Roaming"))
        base = Path(appdata) / "Claude" / "local-agent-mode-sessions" / "skills-plugin"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", str(_home() / ".config"))
        base = Path(xdg) / "Claude" / "local-agent-mode-sessions" / "skills-plugin"
    return base if base.exists() else None


def _install_claude_desktop_skill(skill_path: str, dry_run: bool = False) -> tuple[bool, str]:
    """
    Install the Slowave skill into Claude Desktop's skills-plugin directory.

    Returns (success, message).

    The Skills filesystem layout is:
      {base}/{session_uuid}/{account_uuid}/skills/{skill_name}/SKILL.md
      {base}/{session_uuid}/{account_uuid}/manifest.json

    This is internal Claude Desktop storage — format may change between app
    versions. We operate best-effort and never modify files we don't own.
    """
    base = _skills_plugin_base()
    if base is None:
        return False, "Claude Desktop skills-plugin directory not found (Claude Desktop not installed or never opened)"

    # Find all account directories by scanning session_uuid/account_uuid pairs.
    account_dirs: list[Path] = []
    for session_dir in base.iterdir():
        if not session_dir.is_dir():
            continue
        for account_dir in session_dir.iterdir():
            if account_dir.is_dir() and (account_dir / "manifest.json").exists():
                account_dirs.append(account_dir)

    if not account_dirs:
        return False, "No Claude Desktop skill accounts found — open Claude Desktop at least once first"

    # Extract SKILL.md from the .skill zip
    try:
        with zipfile.ZipFile(skill_path) as zf:
            names = zf.namelist()
            # The zip contains slowave/SKILL.md
            skill_md_entry = next((n for n in names if n.endswith("SKILL.md")), None)
            if not skill_md_entry:
                return False, f"Invalid .skill file: no SKILL.md found inside {skill_path}"
            skill_md_content = zf.read(skill_md_entry).decode("utf-8")
    except Exception as exc:
        return False, f"Could not read skill file {skill_path}: {exc}"

    installed_count = 0
    for account_dir in account_dirs:
        skill_dir = account_dir / "skills" / "slowave"
        skill_md_path = skill_dir / "SKILL.md"
        manifest_path = account_dir / "manifest.json"

        # Check if already up-to-date
        if skill_md_path.exists() and skill_md_path.read_text(encoding="utf-8") == skill_md_content:
            installed_count += 1
            continue

        if dry_run:
            installed_count += 1
            continue

        # Write SKILL.md
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md_path.write_text(skill_md_content, encoding="utf-8")

        # Update manifest.json
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {"skills": []}

        skills: list[dict] = manifest.setdefault("skills", [])
        existing = next((s for s in skills if s.get("skillId") == "slowave"), None)
        entry = {
            "skillId": "slowave",
            "name": "slowave",
            "description": (
                "Use Slowave MCP tools as long-term memory for every task/session. "
                "Start a session, log events during work, load context, remember durable facts, and end the session."
            ),
            "creatorType": "user",
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "enabled": True,
        }
        if existing:
            existing.update(entry)
        else:
            skills.append(entry)
        manifest["lastUpdated"] = int(time.time() * 1000)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        installed_count += 1

    if installed_count == 0:
        return False, "No skill account directories found"
    verb = "Would install" if dry_run else "Installed"
    return True, f"{verb} Slowave skill into {installed_count} Claude Desktop account(s)"


# ---------------------------------------------------------------------------
# MCP binary detection
# ---------------------------------------------------------------------------

def _find_mcp_binary() -> str | None:
    found = shutil.which("slowave-mcp")
    if found:
        # Keep the stable symlink path (e.g. /opt/homebrew/bin/slowave-mcp) rather
        # than resolving it to a versioned Cellar path that breaks on brew upgrade.
        return str(Path(found).absolute())
    extras: list[Path] = [
        _home() / ".local" / "bin" / "slowave-mcp",
        _home() / ".local" / "pipx" / "venvs" / "slowave" / "bin" / "slowave-mcp",
        Path("/opt/homebrew/bin/slowave-mcp"),
        Path("/usr/local/bin/slowave-mcp"),
    ]
    if SYSTEM == "Windows":
        extras += [
            _home() / "AppData" / "Local" / "Programs" / "Python" / "Scripts" / "slowave-mcp.exe",
            _home() / "AppData" / "Roaming" / "Python" / "Scripts" / "slowave-mcp.exe",
        ]
    for p in extras:
        if p.exists():
            return str(p.absolute())
    return None


def _find_slowave_binary() -> str:
    found = shutil.which("slowave")
    if found:
        # Same: keep the stable symlink, don't resolve into a versioned path.
        return str(Path(found).absolute())
    mcp = _find_mcp_binary() or ""
    # e.g. /opt/homebrew/bin/slowave-mcp -> /opt/homebrew/bin/slowave
    candidate = mcp.replace("-mcp.exe", ".exe").replace("-mcp", "")
    if candidate and Path(candidate).exists():
        return candidate
    return "slowave"  # fallback — will be resolved at runtime


# ---------------------------------------------------------------------------
# JSON config helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            click.echo(
                click.style(
                    f"  ✗  {path} contains invalid JSON and cannot be patched safely.\n"
                    f"     Fix the file first, then re-run slowave setup.\n"
                    f"     Error: {exc}",
                    fg="red",
                )
            )
            sys.exit(1)
    return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _patch_mcp_servers(config: dict[str, Any], mcp_path: str) -> tuple[dict[str, Any], bool]:
    servers = config.setdefault("mcpServers", {})
    want = {"command": mcp_path}
    if servers.get("slowave") == want:
        return config, False
    servers["slowave"] = want
    return config, True


# ---------------------------------------------------------------------------
# CLAUDE.md / .clinerules injection
# ---------------------------------------------------------------------------

_MARKER_START = "<!-- slowave-lifecycle-start -->"
_MARKER_END = "<!-- slowave-lifecycle-end -->"

_LIFECYCLE_BLOCK_TEMPLATE = """\
<!-- slowave-lifecycle-start -->
## MANDATORY FIRST ACTION — Slowave memory

> Do not respond to the user until steps 1-3 complete.
> Do not end the session without steps 4-5.

**Session open (run before first response):**
1. `slowave_session_start(agent="{agent}", project="<basename(cwd)>")` → store `session_id`
2. `slowave_event(session_id, "user_message", "<verbatim user request>")`
3. `slowave_context(query="<task>", project="<basename(cwd)>", application="{agent}", limit=8)`

**During work:** call `slowave_event(session_id, type, content)` for every meaningful
user/assistant message, tool call/result, decision, error, discovery.
Event content = 1-3 self-contained sentences (reason + result). Never vague notes like "ran command".

**Session close (run before last response):**
4. `slowave_event(session_id, "task_complete" | "task_failed", "<1-3 sentence outcome>")`
5. `slowave_session_end(session_id)`

Use `slowave_remember(content, type, project)` for durable facts, preferences, decisions, constraints, warnings, lessons.
Use `slowave_context` for default priming. Use `slowave_recall` only when broad history/evidence is explicitly needed.

Anti-patterns to avoid:
- Starting/ending a session without any `slowave_event` calls.
- Batching all events at the end instead of logging during work.
- Forgetting or changing the returned `session_id`.
<!-- slowave-lifecycle-end -->"""


def _lifecycle_block(agent: str) -> str:
    return _LIFECYCLE_BLOCK_TEMPLATE.format(agent=agent)


def _inject_block(path: Path, block: str) -> bool:
    """Inject block between markers. Idempotent — replaces existing block. Returns True if changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""

    if _MARKER_START in existing and _MARKER_END in existing:
        start = existing.index(_MARKER_START)
        end = existing.index(_MARKER_END) + len(_MARKER_END)
        new_content = existing[:start] + block + existing[end:]
        if new_content == existing:
            return False
        path.write_text(new_content, encoding="utf-8")
        return True

    # Prepend
    sep = "\n\n" if existing.strip() else ""
    path.write_text(block + sep + existing, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Claude Code hooks
# ---------------------------------------------------------------------------

_HOOKS_MARKER = "SLOWAVE MANDATORY"

_USER_PROMPT_CMD = (
    "echo 'SLOWAVE MANDATORY: Before writing your first word call: "
    "(1) slowave_session_start(agent=\"claude-code\", project=basename(cwd)) store session_id, "
    "(2) slowave_event(session_id,\"user_message\",verbatim request), "
    "(3) slowave_context(query=task,project=basename(cwd),application=\"claude-code\"). "
    "Produce NO output until these three calls succeed.'"
)

_STOP_CMD = (
    "echo 'SLOWAVE MANDATORY: Before finishing this turn call: "
    "(1) slowave_event(session_id,\"task_complete\" or \"task_failed\",1-3 sentence outcome), "
    "(2) slowave_session_end(session_id). "
    "Do NOT end the turn without these two calls.'"
)


def _hooks_present(config: dict[str, Any], event: str) -> bool:
    for group in config.get("hooks", {}).get(event, []):
        for h in group.get("hooks", []):
            if _HOOKS_MARKER in h.get("command", ""):
                return True
    return False


def _patch_claude_code_hooks(config: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Inject UserPromptSubmit + Stop hooks. Idempotent."""
    changed = False
    hooks = config.setdefault("hooks", {})
    for event, cmd in [("UserPromptSubmit", _USER_PROMPT_CMD), ("Stop", _STOP_CMD)]:
        if not _hooks_present(config, event):
            hooks.setdefault(event, []).append(
                {"matcher": "", "hooks": [{"type": "command", "command": cmd}]}
            )
            changed = True
    return config, changed


# ---------------------------------------------------------------------------
# Worker service templates
# ---------------------------------------------------------------------------

_LAUNCHD_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>com.slowave.worker</string>
    <key>ProgramArguments</key>
    <array>
      <string>{bin}</string>
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
"""

_SYSTEMD_SERVICE = """\
[Unit]
Description=Slowave background consolidation worker
After=network.target

[Service]
ExecStart={bin} worker --interval 300
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
"""


def _install_worker_macos(slowave_bin: str) -> tuple[str, bool]:
    plist_dir = _home() / "Library" / "LaunchAgents"
    plist_path = plist_dir / "com.slowave.worker.plist"
    content = _LAUNCHD_PLIST.format(bin=slowave_bin)
    if plist_path.exists() and plist_path.read_text(encoding="utf-8") == content:
        return str(plist_path), False
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(content, encoding="utf-8")
    try:
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, check=False)
        subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, check=False)
    except FileNotFoundError:
        pass
    return str(plist_path), True


def _install_worker_linux(slowave_bin: str) -> tuple[str, bool]:
    xdg = os.environ.get("XDG_CONFIG_HOME", str(_home() / ".config"))
    svc_dir = Path(xdg) / "systemd" / "user"
    svc_path = svc_dir / "slowave-worker.service"
    content = _SYSTEMD_SERVICE.format(bin=slowave_bin)
    if svc_path.exists() and svc_path.read_text(encoding="utf-8") == content:
        return str(svc_path), False
    svc_dir.mkdir(parents=True, exist_ok=True)
    svc_path.write_text(content, encoding="utf-8")
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=False)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "slowave-worker"],
            capture_output=True, check=False,
        )
    except FileNotFoundError:
        pass
    return str(svc_path), True


def _install_worker_windows(slowave_bin: str) -> tuple[str, bool]:
    task_name = "SlowaveWorker"
    ps = (
        f"$a=New-ScheduledTaskAction -Execute '{slowave_bin}' -Argument 'worker --interval 300';"
        f"$t=New-ScheduledTaskTrigger -AtLogOn;"
        f"$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -RestartCount 3 "
        f"-RestartInterval (New-TimeSpan -Minutes 1);"
        f"$p=New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited;"
        f"Register-ScheduledTask -TaskName '{task_name}' -Action $a -Trigger $t -Settings $s "
        f"-Principal $p -Force;"
        f"Start-ScheduledTask -TaskName '{task_name}'"
    )
    try:
        subprocess.run(["powershell", "-NonInteractive", "-Command", ps],
                       capture_output=True, check=False)
    except FileNotFoundError:
        pass
    return task_name, True


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _ok(msg: str) -> None:
    click.echo(click.style(f"  ✓  {msg}", fg="green"))


def _skip(msg: str) -> None:
    click.echo(click.style(f"  –  {msg}", fg="bright_black"))


def _warn(msg: str) -> None:
    click.echo(click.style(f"  ⚠  {msg}", fg="yellow"))


def _err(msg: str) -> None:
    click.echo(click.style(f"  ✗  {msg}", fg="red"))


def _section(title: str) -> None:
    click.echo(f"\n{click.style(title, bold=True)}")


# ---------------------------------------------------------------------------
# `slowave setup` Click command
# ---------------------------------------------------------------------------

@click.command("setup")
@click.option(
    "--client",
    type=click.Choice(["claude-code", "claude-desktop", "cline", "all"], case_sensitive=False),
    default="all", show_default=True,
    help="Which client(s) to configure.",
)
@click.option("--worker/--no-worker", default=True, show_default=True,
              help="Install the background worker as a system service.")
@click.option("--hooks/--no-hooks", "install_hooks", default=True, show_default=True,
              help="Inject UserPromptSubmit + Stop hooks (Claude Code only).")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing any files.")
def setup_cmd(client: str, worker: bool, install_hooks: bool, dry_run: bool) -> None:
    """One-command post-install wiring for Claude Code, Claude Desktop, and Cline.

    Automates MCP config, lifecycle instruction injection, enforcement hooks,
    and the background worker service. All steps are idempotent.

    \b
    Examples:
      slowave setup                       # wire everything
      slowave setup --client claude-code  # Claude Code only
      slowave setup --no-worker           # skip service install
      slowave setup --dry-run             # preview without writing
    """
    click.echo(click.style("\nSlowave setup", bold=True))
    if dry_run:
        click.echo(click.style("  [DRY RUN — no files will be changed]\n", fg="yellow"))

    do_cc = client in ("claude-code", "all")
    do_cd = client in ("claude-desktop", "all")
    do_cl = client in ("cline", "all")

    # 1. Binaries
    _section("1. Locating binaries")
    mcp_path = _find_mcp_binary()
    if not mcp_path:
        _err("slowave-mcp not found. Install first:  pipx install slowave")
        sys.exit(1)
    _ok(f"slowave-mcp: {mcp_path}")
    slowave_bin = _find_slowave_binary()
    _ok(f"slowave:     {slowave_bin}")

    # 2. Claude Code
    if do_cc:
        _section("2. Claude Code")
        settings_path = _claude_settings_path()
        cfg = _read_json(settings_path)
        cfg, changed = _patch_mcp_servers(cfg, mcp_path)
        if changed:
            if not dry_run:
                _write_json(settings_path, cfg)
            _ok(f"MCP server added → {settings_path}")
        else:
            _skip(f"MCP server already present")

        if install_hooks:
            cfg, changed = _patch_claude_code_hooks(cfg)
            if changed:
                if not dry_run:
                    _write_json(settings_path, cfg)
                _ok(f"Hooks injected (UserPromptSubmit + Stop) → {settings_path}")
            else:
                _skip("Slowave hooks already present")
        else:
            _skip("Hooks skipped (--no-hooks)")

        claude_md = _claude_md_path()
        if dry_run:
            _ok(f"Would inject lifecycle block → {claude_md}")
        else:
            changed = _inject_block(claude_md, _lifecycle_block("claude-code"))
            _ok(f"Lifecycle block injected → {claude_md}") if changed else _skip("Lifecycle block already present")

    # 3. Claude Desktop
    if do_cd:
        _section("3. Claude Desktop")
        desktop_path = _claude_desktop_config_path()
        if not desktop_path.parent.exists():
            _warn(f"Config dir not found: {desktop_path.parent}  (Claude Desktop installed?)")
        else:
            cfg_d = _read_json(desktop_path)
            cfg_d, changed = _patch_mcp_servers(cfg_d, mcp_path)
            if changed:
                if not dry_run:
                    _write_json(desktop_path, cfg_d)
                _ok(f"MCP server added → {desktop_path}")
            else:
                _skip("MCP server already present")
        # Skill install — attempt filesystem injection, but Claude Desktop resets this
        # directory on launch so the manual upload is the only persistent path.
        skill_file = _find_skill_file()
        if skill_file:
            if not dry_run:
                _install_claude_desktop_skill(skill_file, dry_run=False)
            skill_hint = f"     File: {skill_file}"
        else:
            skill_hint = f"     Download: {_SKILL_GITHUB_URL}"
        click.echo(click.style(
            "\n  ⚠  REQUIRED — upload the Slowave Skill in Claude Desktop.\n"
            "     Claude Desktop resets its skills directory on each launch,\n"
            "     so the Skill must be uploaded manually once via the UI.\n"
            "\n"
            f"{skill_hint}\n"
            "\n"
            "     Steps: Settings → Connectors → Customize → Skills → Create → Upload\n"
            "     Then restart Claude Desktop.",
            fg="yellow",
        ))

    # 4. Cline
    if do_cl:
        _section("4. Cline")
        cline_path = _cline_mcp_settings_path()
        if not cline_path.parent.exists():
            _warn(f"Cline settings not found: {cline_path.parent}  (Cline/Cursor installed?)")
        else:
            cfg_c = _read_json(cline_path)
            cfg_c, changed = _patch_mcp_servers(cfg_c, mcp_path)
            if changed:
                if not dry_run:
                    _write_json(cline_path, cfg_c)
                _ok(f"MCP server added → {cline_path}")
            else:
                _skip("MCP server already present")
        clinerules = _clinerules_path()
        if dry_run:
            _ok(f"Would inject lifecycle block → {clinerules}")
        else:
            changed = _inject_block(clinerules, _lifecycle_block("cline-tui"))
            _ok(f"Lifecycle block injected → {clinerules}") if changed else _skip("Lifecycle block already present")

    # 5. Worker service
    _section("5. Background worker service")
    if worker:
        if dry_run:
            if SYSTEM == "Darwin":
                _ok("Would install launchd service → ~/Library/LaunchAgents/com.slowave.worker.plist")
            elif SYSTEM == "Linux":
                _ok("Would install systemd service → ~/.config/systemd/user/slowave-worker.service")
            elif SYSTEM == "Windows":
                _ok("Would register Task Scheduler task: SlowaveWorker")
            else:
                _warn(f"Unknown platform '{SYSTEM}' — run manually: slowave worker --interval 300")
        else:
            if SYSTEM == "Darwin":
                path, changed = _install_worker_macos(slowave_bin)
                if changed:
                    _ok(f"launchd service installed → {path}")
                else:
                    _skip(f"launchd service already up-to-date")
            elif SYSTEM == "Linux":
                path, changed = _install_worker_linux(slowave_bin)
                if changed:
                    _ok(f"systemd service installed → {path}")
                    _ok("Verify:  systemctl --user status slowave-worker")
                else:
                    _skip("systemd service already up-to-date")
            elif SYSTEM == "Windows":
                task, _ = _install_worker_windows(slowave_bin)
                _ok(f"Task Scheduler task registered: {task}")
                _ok("Verify:  Get-ScheduledTask -TaskName SlowaveWorker")
            else:
                _warn(f"Unknown platform '{SYSTEM}'. Run manually: slowave worker --interval 300")
    else:
        _skip("Skipped (--no-worker). Run manually: slowave worker --interval 300")

    # 6. Doctor
    _section("6. Verification")
    if dry_run:
        _skip("Dry-run — skipping doctor check.")
    else:
        click.echo()
        try:
            subprocess.run([sys.executable, "-m", "slowave", "doctor"], check=False)
        except Exception as exc:
            _warn(f"Could not run slowave doctor: {exc}")

    click.echo()
    click.echo(click.style("Setup complete.", bold=True))
    if not dry_run and do_cc:
        click.echo(
            "\n  Restart Claude Code, then verify:\n"
            '  "Remember that my preferred temporary food is spaghetti."\n'
            '  slowave recall "what is my favourite food" --top-k 5'
        )
