"""slowave setup — one-command post-install wiring.

Automates:
  1. Locating the slowave-mcp binary (absolute path).
  2. Patching MCP client configs (Claude Code, Claude Desktop, Cline).
     Claude Code MCP entry goes into ~/.claude.json (user-scope registry).
  3. Injecting lifecycle instructions (CLAUDE.md, .clinerules) and
     UserPromptSubmit/Stop hooks into ~/.claude/settings.json (hooks only).
  4. Installing the background worker as a user service
     (launchd on macOS, systemd on Linux, Task Scheduler on Windows).
  5. Running `slowave doctor` to verify the result.

All steps are idempotent — re-running is always safe.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import click

# ---------------------------------------------------------------------------
# Change tracking for summary
# ---------------------------------------------------------------------------

class ChangeType(str, Enum):
    """Types of changes that can be tracked."""
    MCP_CONFIG = "mcp_config"
    LIFECYCLE_BLOCK = "lifecycle_block"
    HOOKS = "hooks"
    WORKER_SERVICE = "worker_service"
    MANUAL_STEP = "manual_step"


class ChangeStatus(str, Enum):
    """Status of a change."""
    NEW = "new"
    UPDATE = "update"
    SKIP = "skip"  # Already present, no change needed


@dataclass
class Change:
    """Represents a single change to be applied."""
    change_type: ChangeType
    client: str  # e.g., "claude-code", "claude-desktop", etc.
    status: ChangeStatus
    path: str  # File path or service name
    description: str  # Human-readable description
    details: dict[str, Any] | None = None  # Extra context


class Summary:
    """Collects and formats changes for display."""
    
    def __init__(self):
        self.changes: list[Change] = []
        self.binaries: dict[str, str] = {}  # name -> path
        self.manual_steps: list[str] = []
    
    def add_binary(self, name: str, path: str) -> None:
        """Record a binary location."""
        self.binaries[name] = path
    
    def add_change(self, change: Change) -> None:
        """Add a change to the summary."""
        self.changes.append(change)
    
    def add_manual_step(self, step: str) -> None:
        """Add a manual step required after setup."""
        self.manual_steps.append(step)
    
    def _group_changes(self) -> dict[ChangeType, list[Change]]:
        """Group changes by type."""
        grouped: dict[ChangeType, list[Change]] = {}
        for change_type in ChangeType:
            grouped[change_type] = [c for c in self.changes if c.change_type == change_type]
        return grouped
    
    def format(self) -> str:
        """Format summary as a human-readable string."""
        lines: list[str] = []
        
        # Header
        lines.append(click.style("\n" + "━" * 70, fg="cyan"))
        lines.append(click.style("SUMMARY: Changes to be applied", bold=True, fg="cyan"))
        lines.append(click.style("━" * 70, fg="cyan"))
        lines.append("")
        
        # Binaries
        if self.binaries:
            lines.append(click.style("📦 Binaries", bold=True))
            for name, path in self.binaries.items():
                lines.append(f"  ✓ {name}: {path}")
            lines.append("")
        
        # Group by change type
        grouped = self._group_changes()
        
        # MCP Configs
        if grouped[ChangeType.MCP_CONFIG]:
            configs = grouped[ChangeType.MCP_CONFIG]
            lines.append(click.style(f"🔌 MCP Configurations ({len(configs)} file{'s' if len(configs) != 1 else ''})", bold=True))
            for change in configs:
                status_label = f"({change.status.value.upper()})"
                lines.append(f"  ✓ {change.client} → {change.path} {click.style(status_label, fg='bright_black')}")
            lines.append("")
        
        # Lifecycle Blocks
        if grouped[ChangeType.LIFECYCLE_BLOCK]:
            blocks = grouped[ChangeType.LIFECYCLE_BLOCK]
            lines.append(click.style(f"📝 Lifecycle Blocks ({len(blocks)} file{'s' if len(blocks) != 1 else ''})", bold=True))
            for change in blocks:
                status_label = f"({change.status.value.upper()})"
                lines.append(f"  ✓ {change.client} → {change.path} {click.style(status_label, fg='bright_black')}")
            lines.append("")
        
        # Hooks
        if grouped[ChangeType.HOOKS]:
            hooks = grouped[ChangeType.HOOKS]
            lines.append(click.style("🔐 Lifecycle Hooks", bold=True))
            for change in hooks:
                status_label = f"({change.status.value.upper()})"
                lines.append(f"  ✓ {change.description} {click.style(status_label, fg='bright_black')}")
            lines.append("")
        
        # Worker Service
        if grouped[ChangeType.WORKER_SERVICE]:
            services = grouped[ChangeType.WORKER_SERVICE]
            lines.append(click.style("⚙️  Background Worker Service", bold=True))
            for change in services:
                status_label = f"({change.status.value.upper()})"
                lines.append(f"  ✓ {change.description} → {change.path} {click.style(status_label, fg='bright_black')}")
            lines.append("")
        
        # Manual Steps
        if self.manual_steps:
            lines.append(click.style(f"⚠️  Manual Steps Required ({len(self.manual_steps)})", bold=True))
            for step in self.manual_steps:
                lines.append(f"  ⚠ {step}")
            lines.append("")
        
        lines.append(click.style("━" * 70, fg="cyan"))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------

SYSTEM = platform.system()  # "Darwin", "Linux", "Windows"


def _home() -> Path:
    return Path.home()


def _setup_sentinel_path() -> Path:
    return _home() / ".slowave" / ".setup_done"


def is_setup_done() -> bool:
    return _setup_sentinel_path().exists()


def mark_setup_done() -> None:
    sentinel = _setup_sentinel_path()
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.touch()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _claude_settings_path() -> Path:
    """~/.claude/settings.json — hooks, permissions, env only (NOT mcpServers)."""
    return _home() / ".claude" / "settings.json"


def _claude_json_path() -> Path:
    """~/.claude.json — where Claude Code stores MCP server configs (user scope)."""
    return _home() / ".claude.json"


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


def _cursor_mcp_config_path() -> Path:
    """Cursor native MCP config — ~/.cursor/mcp.json (all platforms)."""
    return _home() / ".cursor" / "mcp.json"


def _cursor_rules_path() -> Path:
    """Cursor global rules file — ~/.cursor/rules (all platforms)."""
    return _home() / ".cursor" / "rules"


def _windsurf_mcp_config_path() -> Path:
    """Windsurf/Devin Desktop MCP config — ~/.codeium/windsurf/mcp_config.json (all platforms)."""
    return _home() / ".codeium" / "windsurf" / "mcp_config.json"


def _windsurf_global_rules_path() -> Path:
    """Windsurf global rules — ~/.codeium/windsurf/memories/global_rules.md (all platforms).

    This file is always-on: injected into every Cascade conversation.
    It is fully injectable programmatically (no manual step required).
    """
    return _home() / ".codeium" / "windsurf" / "memories" / "global_rules.md"


def _cline_mcp_settings_path() -> Path:
    """VS Code / Cursor / TUI Cline MCP settings — best-effort detection."""
    if SYSTEM == "Darwin":
        candidates = [
            _home() / ".cline/data/settings/cline_mcp_settings.json",  # Cline TUI
            _home() / "Library/Application Support/Code/User/globalStorage"
            "/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
            _home() / "Library/Application Support/Cursor/User/globalStorage"
            "/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
        ]
    elif SYSTEM == "Windows":
        appdata = os.environ.get("APPDATA", str(_home() / "AppData" / "Roaming"))
        candidates = [
            _home() / ".cline/data/settings/cline_mcp_settings.json",  # Cline TUI
            Path(appdata) / "Code/User/globalStorage"
            "/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
            Path(appdata) / "Cursor/User/globalStorage"
            "/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
        ]
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", str(_home() / ".config"))
        candidates = [
            _home() / ".cline/data/settings/cline_mcp_settings.json",  # Cline TUI
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
# ClientSpec — single source of truth for every supported client
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClientSpec:
    """Describes one AI client that Slowave can configure.

    All setup, cleanup, summary-preview, and backup-cleanup code iterates
    ``_clients()`` so that adding a new client is a one-line change here.
    Adding a new enforcement mechanism to an existing client is also a
    one-field change: set ``hooks_config_path`` and ``hooks_patch_fn``.

    Fields
    ------
    key         CLI ``--client`` value, e.g. ``"claude-code"``
    label       Human-readable display name

    mcp_path    Callable[[], Path] — the JSON file where mcpServers lives.

    lifecycle_path
                Callable[[], Path] | None — the markdown/rules file to
                auto-inject the lifecycle block into.
                None means injection is manual (see manual_note).
    lifecycle_agent
                Agent-name token passed to ``_lifecycle_block()``.
    manual_lifecycle
                True when lifecycle instructions must be added manually
                (e.g. Claude Desktop custom-instructions, Cursor rules).
    manual_note Human-readable guidance printed after setup for manual steps.

    hooks_config_path
                Callable[[], Path] | None — config file that receives
                enforcement hooks (e.g. ``~/.claude/settings.json``).
                None = this client has no scriptable enforcement mechanism.
    hooks_patch_fn
                Callable[(dict, str), tuple[dict, bool]] | None —
                function that applies/updates enforcement hooks in a config
                dict.  Signature: ``fn(config) -> (new_config, changed)``.
                Must be None when hooks_config_path is None.
    hooks_cleanup_fn
                Callable[(dict), tuple[dict, bool]] | None —
                function that removes Slowave enforcement hooks from a
                config dict.  Signature: ``fn(config) -> (new_config, changed)``.

    require_dir_exists
                When True, skip MCP patching silently if the config file's
                parent directory doesn't exist (client probably not installed).
    restart_note
                Short string shown at the end of setup reminding the user
                what to restart, e.g. ``"Restart Claude Code"``.
    """
    key: str
    label: str
    mcp_path: Any                  # Callable[[], Path]
    lifecycle_path: Any            # Callable[[], Path] | None
    lifecycle_agent: str
    manual_lifecycle: bool = False
    manual_note: str = ""
    hooks_config_path: Any = None  # Callable[[], Path] | None
    hooks_patch_fn: Any = None     # Callable[(dict), (dict, bool)] | None
    hooks_cleanup_fn: Any = None   # Callable[(dict), (dict, bool)] | None
    require_dir_exists: bool = False
    restart_note: str = ""


def _clients() -> list[ClientSpec]:
    """Return the list of all supported client specs for the current platform.

    This is the **single definition** of what clients exist.  Setup, cleanup,
    dry-run preview, backup-dir derivation, and docs all derive from here.
    """
    return [
        ClientSpec(
            key="claude-code",
            label="Claude Code",
            mcp_path=_claude_json_path,
            lifecycle_path=_claude_md_path,
            lifecycle_agent="claude-code",
            # Enforcement: UserPromptSubmit + Stop hooks in settings.json
            hooks_config_path=_claude_settings_path,
            hooks_patch_fn=_patch_claude_code_hooks,
            hooks_cleanup_fn=_remove_claude_code_hooks,
            restart_note="Restart Claude Code to apply changes.",
        ),
        ClientSpec(
            key="claude-desktop",
            label="Claude Desktop",
            mcp_path=_claude_desktop_config_path,
            lifecycle_path=None,
            lifecycle_agent="claude-desktop",
            manual_lifecycle=True,
            manual_note=(
                "Claude Desktop: add Slowave lifecycle block to Custom Instructions.\n"
                "     Settings → General → Instructions for Claude\n"
                "     https://github.com/mrsalty/slowave/blob/main/integrations/claude-desktop/README.md"
            ),
            # No scriptable enforcement: Custom Instructions field is server-side.
            restart_note="Restart Claude Desktop to apply changes.",
        ),
        ClientSpec(
            key="cline",
            label="Cline",
            mcp_path=_cline_mcp_settings_path,
            lifecycle_path=_clinerules_path,
            lifecycle_agent="cline-tui",
            require_dir_exists=False,  # create dir if absent — Cline TUI picks it up on first start
            # No enforcement hooks yet — lifecycle relies on .clinerules instructions.
            # When Cline adds a hook/trigger surface, add hooks_config_path + hooks_patch_fn here.
            restart_note="Reload Cline (or restart VS Code / Cursor) to apply changes.",
        ),
        ClientSpec(
            key="cursor",
            label="Cursor",
            mcp_path=_cursor_mcp_config_path,
            lifecycle_path=None,
            lifecycle_agent="cursor",
            manual_lifecycle=True,
            manual_note=(
                "Cursor: add Slowave lifecycle block to Rules for AI.\n"
                "     Settings → Rules for AI  (or add a .cursorrules file at repo root)\n"
                "     https://github.com/mrsalty/slowave/blob/main/integrations/cursor/README.md"
            ),
            require_dir_exists=True,
            # No scriptable enforcement: Rules for AI is manual.
            restart_note="Restart Cursor to apply changes.",
        ),
        ClientSpec(
            key="windsurf",
            label="Windsurf",
            mcp_path=_windsurf_mcp_config_path,
            lifecycle_path=_windsurf_global_rules_path,
            lifecycle_agent="windsurf",
            require_dir_exists=True,
            # No enforcement hooks yet — lifecycle relies on global_rules.md instructions.
            # When Windsurf adds a hook surface, add hooks_config_path + hooks_patch_fn here.
            restart_note="Restart Windsurf to apply changes.",
        ),
    ]


def _clients_for(client_arg: str) -> list[ClientSpec]:
    """Return the subset of clients selected by the --client flag."""
    if client_arg == "all":
        return _clients()
    return [c for c in _clients() if c.key == client_arg]


def _all_mcp_paths() -> list[Path]:
    """All MCP config file paths across all clients (for backup cleanup)."""
    return [c.mcp_path() for c in _clients()]


def _all_lifecycle_paths() -> list[Path]:
    """All lifecycle-block file paths across all clients that support auto-injection."""
    return [c.lifecycle_path() for c in _clients() if c.lifecycle_path is not None]


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
        local_appdata = os.environ.get("LOCALAPPDATA", str(_home() / "AppData" / "Local"))
        appdata = os.environ.get("APPDATA", str(_home() / "AppData" / "Roaming"))
        # pip install on Windows puts scripts in a version-specific subdirectory, e.g.
        # %LOCALAPPDATA%\Programs\Python\Python312\Scripts\slowave-mcp.exe
        # Glob for any Python* subdirectory rather than hardcoding versions.
        python_base = Path(local_appdata) / "Programs" / "Python"
        versioned_scripts = sorted(python_base.glob("Python*/Scripts/slowave-mcp.exe"), reverse=True)
        extras += [
            # pip install --user (%APPDATA%\Python\PythonXY\Scripts\)
            *sorted((Path(appdata) / "Python").glob("Python*/Scripts/slowave-mcp.exe"), reverse=True),
            # pip install (system Python installer, version-specific)
            *versioned_scripts,
            # pipx on Windows (%LOCALAPPDATA%\pipx\venvs\)
            Path(local_appdata) / "pipx" / "venvs" / "slowave" / "Scripts" / "slowave-mcp.exe",
            Path(local_appdata) / "pipx" / "venvs" / "slowave" / "Scripts" / "slowave-mcp",
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

def _backup_file(path: Path) -> Path | None:
    """Create a timestamped backup of *path* before overwriting it.

    Only one backup is kept per file: any older ``<name>.bak.*`` siblings
    are removed before the new backup is written, so re-running setup never
    accumulates stale copies.

    Returns the backup path if a backup was created, or None if the file
    did not exist (nothing to back up).  The backup sits next to the
    original:  ``<name>.bak.<YYYYMMDD_HHMMSS>``
    """
    if not path.exists():
        return None
    # Remove any previous backups for this file so we keep exactly one.
    for old in path.parent.glob(f"{path.name}.bak.*"):
        try:
            old.unlink()
        except OSError:
            pass
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.bak.{ts}")
    shutil.copy2(path, backup)
    return backup


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
    bak = _backup_file(path)
    if bak:
        click.echo(click.style(f"  ↩  backup → {bak}", fg="cyan"))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _patch_mcp_servers(config: dict[str, Any], mcp_path: str) -> tuple[dict[str, Any], bool]:
    """Patch mcpServers in a config dict. Uses type:stdio format (current Claude Code standard).
    Also accepts the legacy {command} format as up-to-date to avoid spurious re-writes.
    """
    servers = config.setdefault("mcpServers", {})
    want = {"type": "stdio", "command": mcp_path}
    existing = servers.get("slowave", {})
    # Up-to-date if it already matches the new format, or the old {command}-only format
    if existing == want or existing == {"command": mcp_path}:
        # Upgrade legacy format silently
        if existing == {"command": mcp_path}:
            servers["slowave"] = want
            return config, True
        return config, False
    servers["slowave"] = want
    return config, True


def _remove_mcp_servers_from_settings(config: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Remove mcpServers from settings.json (it was written there by old Slowave versions
    but Claude Code ignores it — MCP config belongs in ~/.claude.json).
    """
    if "mcpServers" not in config:
        return config, False
    mcp = config.get("mcpServers", {})
    if "slowave" not in mcp:
        return config, False
    del mcp["slowave"]
    if not mcp:
        del config["mcpServers"]
    return config, True


# ---------------------------------------------------------------------------
# CLAUDE.md / .clinerules injection
# ---------------------------------------------------------------------------

_MARKER_START = "<!-- slowave-lifecycle-start"   # prefix match — covers v1 and v2
_MARKER_END = "<!-- slowave-lifecycle-end"     # prefix match — covers v1 and v2

_LIFECYCLE_BLOCK_TEMPLATE = """\
<!-- slowave-lifecycle-start v2 -->
## MANDATORY — Slowave memory (5-verb cognitive cycle)

> Do not respond to the user until step 1 (and the cold start gate below, if triggered) completes.
> Do not end the task without step 5. Run step 4 after using retrieved memories — feedback is NOT auto-fired; skipping means slowave cannot learn.

**Task start (run before first response):**
1. Derive `goal` = a 3–6 word verb-noun phrase (e.g. `"implement oauth login"`, `"fix auth null pointer"`, `"refactor database layer"`). Use consistent phrasing — same goal string across sessions enables procedure learning.
   Then: `slowave_activate(query="<verbatim task>", goal="<derived goal>", scope="project:<basename(cwd)>")` → store `retrieval_id` and `session_id`

   **Cold start gate — if the response contains `cold_start: true`:**
   - Check for `README.md` then `CLAUDE.md` in the project root (stop at the first one found).
   - Read it. For each fact, ask: would this be useful in any future interaction within this scope?
     Can it be inferred as durable and critical — something a future session could not assume without it?
     If yes to both, call `slowave_remember(content, type, scope)` — one call per fact, not one call per group.
     Exhaust the document before moving on.
   - If neither file exists, apply the same questions to what is visible from the current request.
   - Only after you have no more qualifying facts to store, respond to the user.
   - Do NOT scan the full codebase — only the designated knowledge files above.

**During work:**
2. `slowave_remember(content, type, scope="project:<basename(cwd)>")` — for any durable fact, decision, lesson, constraint. Session is inferred automatically; no session_id needed.
3. `slowave_recall(query)` — only when you need specific history not surfaced by activate. Store the returned `retrieval_id`.

**Task close (run before last response):**
4. If you used memories from activate or recall: `slowave_reinforce(retrieval_id=<id>, feedback="useful|partially_useful|irrelevant|stale|wrong|missing|too_much_context", outcome="success|partial|failure|unknown", used_memory_ids=[...])`. Do not invent feedback; only rate memories you actually used.
5. `slowave_commit(scope="project:<basename(cwd)>", outcome="success|partial|failure")` — closes session, forms episodes.

Anti-patterns to avoid:
- Skipping `slowave_activate` at task start.
- Calling `slowave_remember` without `scope` (memories become unscopeable).
- Skipping the cold start gate when `cold_start: true` (memory store stays empty forever).
- Skipping `slowave_reinforce` after using memories (learning loop broken).
- Skipping `slowave_commit` (session stays open until idle reaper fires, no outcome recorded).
- Using old tools: `slowave_context`, `slowave_session_start/end`, `slowave_event`, `slowave_retrieval_feedback`, `slowave_context_feedback` — these are deleted.
<!-- slowave-lifecycle-end v2 -->"""


def _lifecycle_block(agent: str) -> str:
    return _LIFECYCLE_BLOCK_TEMPLATE.format(agent=agent)


# Heading used by legacy (pre-marker) slowave setup to write lifecycle instructions.
# Present as un-markered content in files written by slowave ≤0.4.x.
_LEGACY_SECTION_HEADING = "## Slowave memory"


def _strip_legacy_slowave_section(content: str) -> str:
    """Remove the legacy un-markered '## Slowave memory' block written by old setup versions.

    Old setup (pre-marker) wrote a plain markdown section starting with
    '## Slowave memory' that is not wrapped in HTML comment markers.  When
    users upgrade and run 'slowave setup' the new marker-based block is
    prepended, but the old section survives below it causing Claude to read
    two contradictory sets of instructions.  This helper strips that tail
    section so the file stays clean after cleanup + setup.

    Only removes content that is recognisably slowave-generated (contains the
    heading '## Slowave memory').  Unrelated user content is left untouched.
    Returns the cleaned string (may equal the input if nothing was found).
    """
    if _LEGACY_SECTION_HEADING not in content:
        return content

    lines = content.splitlines(keepends=True)
    result: list[str] = []
    in_legacy = False
    for line in lines:
        stripped = line.strip()
        if not in_legacy and stripped == _LEGACY_SECTION_HEADING:
            in_legacy = True
            # Drop any blank lines immediately before this heading that we
            # already buffered.
            while result and result[-1].strip() == "":
                result.pop()
            continue
        if in_legacy:
            # End of section = next heading of the same or higher level, or EOF.
            if stripped.startswith("## ") and stripped != _LEGACY_SECTION_HEADING:
                in_legacy = False
                result.append(line)
            # otherwise: keep skipping legacy lines
        else:
            result.append(line)
    return "".join(result)


def _inject_block(path: Path, block: str) -> bool:
    """Inject block between markers. Idempotent — replaces existing block. Returns True if changed.

    Also strips any legacy un-markered '## Slowave memory' section written by
    old setup versions (≤0.4.x) so that Claude never reads two conflicting
    sets of lifecycle instructions after an upgrade.

    A timestamped backup is created before any write (see _backup_file).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""

    if _MARKER_START in existing and _MARKER_END in existing:
        start = existing.index(_MARKER_START)
        end_marker_pos = existing.index(_MARKER_END)
        # Advance past the full marker line (handles versioned suffixes like " v2 -->")
        end_of_line = existing.find("\n", end_marker_pos)
        end = end_of_line + 1 if end_of_line != -1 else len(existing)
        before = existing[:start]
        after = _strip_legacy_slowave_section(existing[end:])
        new_content = before + block + after
        if new_content == existing:
            return False
        bak = _backup_file(path)
        if bak:
            click.echo(click.style(f"  ↩  backup → {bak}", fg="cyan"))
        path.write_text(new_content, encoding="utf-8")
        return True

    # No markers yet — strip any legacy section before prepending.
    rest = _strip_legacy_slowave_section(existing)
    sep = "\n\n" if rest.strip() else ""
    new_content = block + sep + rest
    if new_content == existing:
        return False
    bak = _backup_file(path)
    if bak:
        click.echo(click.style(f"  ↩  backup → {bak}", fg="cyan"))
    path.write_text(new_content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Claude Code hooks
# ---------------------------------------------------------------------------

_HOOKS_MARKER = "SLOWAVE MANDATORY"

_USER_PROMPT_CMD = (
    "echo 'SLOWAVE MANDATORY: Before writing your first word call: "
    "(1) derive goal=3-6 word verb-noun phrase e.g. implement-oauth-login fix-auth-bug refactor-db-layer, "
    "(2) slowave_activate(query=<verbatim task>,goal=<derived goal>,scope=project:<basename(cwd)>) "
    "store retrieval_id and session_id. "
    "Produce NO output until this call succeeds.'"
)

_STOP_CMD = (
    "echo 'SLOWAVE MANDATORY: Before finishing this turn call: "
    "(1) if you used memories: slowave_reinforce(retrieval_id=<id>,feedback=useful|irrelevant|stale|wrong,outcome=success|partial|failure|unknown), "
    "(2) slowave_commit(scope=project:<basename(cwd)>,outcome=success|partial|failure|unknown). "
    "Do NOT end the turn without step 2.'"
)


def _hooks_up_to_date(config: dict[str, Any], event: str, cmd: str) -> bool:
    """Return True iff a Slowave hook for *event* already has exactly *cmd* as its command.

    Checks for exact command text rather than mere marker presence so that
    updated hook commands are applied on re-run.
    """
    for group in config.get("hooks", {}).get(event, []):
        for h in group.get("hooks", []):
            if _HOOKS_MARKER in h.get("command", ""):
                return h.get("command", "") == cmd
    return False


def _patch_claude_code_hooks(config: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Inject or update UserPromptSubmit + Stop hooks.

    Always writes the current command text.  If a stale Slowave hook already
    exists (marker present but command differs), it is replaced in-place.
    If no Slowave hook exists yet, a new group is appended.
    """
    changed = False
    hooks = config.setdefault("hooks", {})
    for event, cmd in [("UserPromptSubmit", _USER_PROMPT_CMD), ("Stop", _STOP_CMD)]:
        if _hooks_up_to_date(config, event, cmd):
            continue  # already correct — skip
        # Remove any stale Slowave hook group for this event, then re-add.
        if event in hooks:
            hooks[event] = [
                g for g in hooks[event]
                if not any(_HOOKS_MARKER in h.get("command", "") for h in g.get("hooks", []))
            ]
        hooks.setdefault(event, []).append(
            {"matcher": "", "hooks": [{"type": "command", "command": cmd}]}
        )
        changed = True
    return config, changed


def _remove_claude_code_hooks(config: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Remove all Slowave enforcement hooks from a Claude Code settings dict.

    Used by cleanup.  Removes every hook group whose command contains
    ``_HOOKS_MARKER`` from the ``UserPromptSubmit`` and ``Stop`` events.
    """
    changed = False
    for event in ["UserPromptSubmit", "Stop"]:
        before = config.get("hooks", {}).get(event, [])
        after = [
            g for g in before
            if not any(_HOOKS_MARKER in h.get("command", "") for h in g.get("hooks", []))
        ]
        if after != before:
            config.setdefault("hooks", {})[event] = after
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


def _find_pythonw() -> str | None:
    """Return the path to pythonw.exe (no-console Python launcher) on Windows.

    pythonw.exe lives in the same directory as python.exe and is shipped with
    every Python Windows installer.  Using it instead of slowave.EXE for the
    Task Scheduler action prevents a visible console window from opening.
    """
    import os as _os
    py_dir = _os.path.dirname(sys.executable)
    candidate = _os.path.join(py_dir, "pythonw.exe")
    if Path(candidate).exists():
        return candidate
    return None


def _install_worker_windows(slowave_bin: str) -> tuple[str, bool]:
    """Register SlowaveWorker in Task Scheduler.

    Uses ``pythonw.exe -m slowave worker`` so the worker runs without opening a
    visible console window.  Falls back to ``slowave_bin`` if pythonw.exe is not
    found (rare custom installs without the no-console launcher).
    """
    task_name = "SlowaveWorker"

    # Prefer pythonw.exe to avoid a visible console window on logon/start.
    pythonw = _find_pythonw()
    if pythonw:
        execute = pythonw
        argument = "-m slowave worker --interval 300"
    else:
        execute = slowave_bin
        argument = "worker --interval 300"

    # Check if a compatible task already exists (idempotency).
    # Accept either the new pythonw form or the old slowave.EXE form so that
    # re-runs on machines with an existing registration don't re-register.
    already_registered = False
    try:
        check = subprocess.run(
            ["powershell", "-NonInteractive", "-Command",
             f"$t = Get-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue; "
             f"if ($t) {{ $t.Actions[0].Execute + '|' + $t.Actions[0].Arguments }}"],
            capture_output=True, text=True, check=False,
        )
        existing = check.stdout.strip()
        if existing:
            existing_exe, _, existing_args = existing.partition("|")
            existing_exe = existing_exe.strip().lower()
            existing_args = existing_args.strip().lower()
            # Up-to-date if already using pythonw (new) or the same old slowave.EXE
            new_form = pythonw and existing_exe == pythonw.lower() and "slowave worker" in existing_args
            old_form = existing_exe == slowave_bin.lower()
            already_registered = bool(new_form or old_form)
    except FileNotFoundError:
        pass

    if already_registered:
        return task_name, False

    ps = (
        f"$a=New-ScheduledTaskAction -Execute '{execute}' -Argument '{argument}';"
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


def _build_summary(client: str, worker: bool, install_hooks: bool,
                   mcp_path: str, slowave_bin: str) -> Summary:
    """Build a summary of changes without modifying any files."""
    summary = Summary()
    summary.add_binary("slowave-mcp", mcp_path)
    summary.add_binary("slowave", slowave_bin)

    for spec in _clients_for(client):
        mcp_file = spec.mcp_path()
        if not spec.require_dir_exists or mcp_file.parent.exists():
            cfg = _read_json(mcp_file)
            _, changed_mcp = _patch_mcp_servers(cfg, mcp_path)
            summary.add_change(Change(
                change_type=ChangeType.MCP_CONFIG,
                client=spec.label,
                status=ChangeStatus.UPDATE if changed_mcp else ChangeStatus.SKIP,
                path=str(mcp_file),
                description="MCP server configuration",
            ))
        if spec.hooks_config_path is not None and spec.hooks_patch_fn is not None and install_hooks:
            hooks_file = spec.hooks_config_path()
            _, changed_hooks = spec.hooks_patch_fn(_read_json(hooks_file))
            summary.add_change(Change(
                change_type=ChangeType.HOOKS,
                client=spec.label,
                status=ChangeStatus.UPDATE if changed_hooks else ChangeStatus.SKIP,
                path=str(hooks_file),
                description="Enforcement hooks",
            ))
        if spec.lifecycle_path is not None:
            lc_file = spec.lifecycle_path()
            existing = lc_file.read_text(encoding="utf-8") if lc_file.exists() else ""
            needs_update = _MARKER_START not in existing or _MARKER_END not in existing
            summary.add_change(Change(
                change_type=ChangeType.LIFECYCLE_BLOCK,
                client=spec.label,
                status=ChangeStatus.UPDATE if needs_update else ChangeStatus.SKIP,
                path=str(lc_file),
                description="Lifecycle instruction block",
            ))
        elif spec.manual_lifecycle and spec.manual_note:
            summary.add_manual_step(spec.manual_note)

    # Worker service
    if worker:
        if SYSTEM == "Darwin":
            plist_dir = _home() / "Library" / "LaunchAgents"
            plist_path = plist_dir / "com.slowave.worker.plist"
            plist_content = _LAUNCHD_PLIST.format(bin=slowave_bin)
            changed = not (plist_path.exists() and plist_path.read_text(encoding="utf-8") == plist_content)
            status = ChangeStatus.UPDATE if changed else ChangeStatus.SKIP
            summary.add_change(Change(
                change_type=ChangeType.WORKER_SERVICE,
                client="macOS",
                status=status,
                path=str(plist_path),
                description="launchd service"
            ))
        elif SYSTEM == "Linux":
            xdg = os.environ.get("XDG_CONFIG_HOME", str(_home() / ".config"))
            svc_path = Path(xdg) / "systemd" / "user" / "slowave-worker.service"
            svc_content = _SYSTEMD_SERVICE.format(bin=slowave_bin)
            changed = not (svc_path.exists() and svc_path.read_text(encoding="utf-8") == svc_content)
            status = ChangeStatus.UPDATE if changed else ChangeStatus.SKIP
            summary.add_change(Change(
                change_type=ChangeType.WORKER_SERVICE,
                client="Linux",
                status=status,
                path=str(svc_path),
                description="systemd service"
            ))
        elif SYSTEM == "Windows":
            # Check if the task already exists with the current binary
            task_exists = False
            try:
                check = subprocess.run(
                    ["powershell", "-NonInteractive", "-Command",
                     f"$t = Get-ScheduledTask -TaskName 'SlowaveWorker' -ErrorAction SilentlyContinue; "
                     f"if ($t) {{ $t.Actions[0].Execute }}"],
                    capture_output=True, text=True, check=False,
                )
                existing_exe = check.stdout.strip()
                task_exists = bool(existing_exe and existing_exe.lower() == slowave_bin.lower())
            except FileNotFoundError:
                pass
            status = ChangeStatus.SKIP if task_exists else ChangeStatus.UPDATE
            summary.add_change(Change(
                change_type=ChangeType.WORKER_SERVICE,
                client="Windows",
                status=status,
                path="Task Scheduler",
                description="SlowaveWorker task"
            ))

    return summary


def _ask_confirmation() -> bool:
    """Ask user for confirmation to proceed. Returns True if confirmed.

    Auto-confirms in non-interactive contexts (Homebrew hooks, CI, pipes).
    """
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return True
    try:
        return click.confirm("\nProceed with these changes?", default=False)
    except click.Abort:
        return False


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
    type=click.Choice(["claude-code", "claude-desktop", "cline", "cursor", "windsurf", "all"], case_sensitive=False),
    default="all", show_default=True,
    help="Which client(s) to configure.",
)
@click.option("--worker/--no-worker", default=True, show_default=True,
              help="Install the background worker as a system service.")
@click.option("--hooks/--no-hooks", "install_hooks", default=True, show_default=True,
              help="Inject UserPromptSubmit + Stop hooks (Claude Code only).")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing any files.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
def setup_cmd(client: str, worker: bool, install_hooks: bool, dry_run: bool, as_json: bool = False) -> None:
    """One-command post-install wiring for Claude Code, Claude Desktop, Cline, Cursor, and Windsurf.

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

    # 1. Binaries
    _section("1. Locating binaries")
    mcp_path = _find_mcp_binary()
    if not mcp_path:
        _err("slowave-mcp not found. Install first:  pipx install slowave")
        sys.exit(1)
    _ok(f"slowave-mcp: {mcp_path}")
    slowave_bin = _find_slowave_binary()
    _ok(f"slowave:     {slowave_bin}")

    # Build and display summary
    summary = _build_summary(client, worker, install_hooks, mcp_path, slowave_bin)
    click.echo(summary.format())
    
    # Confirm unless dry-run
    if not dry_run:
        if not _ask_confirmation():
            click.echo(click.style("\nSetup cancelled.", fg="yellow"))
            sys.exit(0)

    # 2-6. Clients (data-driven — add new clients in _clients() only)
    for i, spec in enumerate(_clients_for(client), start=2):
        _section(f"{i}. {spec.label}")
        mcp_file = spec.mcp_path()

        # Skip if the config directory doesn't exist and client marks require_dir_exists
        if spec.require_dir_exists and not mcp_file.parent.exists():
            _warn(f"{spec.label} config dir not found: {mcp_file.parent}  ({spec.label} installed?)")
        else:
            cfg = _read_json(mcp_file)
            cfg, changed = _patch_mcp_servers(cfg, mcp_path)
            if changed:
                if dry_run:
                    _ok(f"Would add MCP server → {mcp_file}")
                else:
                    _write_json(mcp_file, cfg)
                    _ok(f"MCP server added → {mcp_file}")
            else:
                _skip(f"MCP server already present in {mcp_file}")

        # Claude Code ≤0.4.2 migration: remove stale mcpServers from settings.json
        if spec.key == "claude-code":
            settings_path = _claude_settings_path()
            cfg_settings = _read_json(settings_path)
            cfg_settings, cleaned = _remove_mcp_servers_from_settings(cfg_settings)
            if cleaned:
                if dry_run:
                    _ok(f"Would remove stale mcpServers from {settings_path} (moved to ~/.claude.json)")
                else:
                    _write_json(settings_path, cfg_settings)
                    _ok(f"Removed stale mcpServers from settings.json (moved to ~/.claude.json)")

        # Enforcement hooks — data-driven via spec.hooks_patch_fn
        if spec.hooks_config_path is not None and spec.hooks_patch_fn is not None:
            hooks_file = spec.hooks_config_path()
            cfg_hooks = _read_json(hooks_file)
            # Re-use the already-loaded settings dict for Claude Code (avoid double-read)
            if spec.key == "claude-code":
                cfg_hooks = cfg_settings
            if install_hooks:
                cfg_hooks, changed = spec.hooks_patch_fn(cfg_hooks)
                if changed:
                    if dry_run:
                        _ok(f"Would update enforcement hooks → {hooks_file}")
                    else:
                        _write_json(hooks_file, cfg_hooks)
                        _ok(f"Enforcement hooks updated → {hooks_file}")
                else:
                    _skip(f"Enforcement hooks already up-to-date in {hooks_file}")
            else:
                _skip(f"Enforcement hooks skipped (--no-hooks) for {spec.label}")

        # Lifecycle block — auto-inject or print manual instruction
        if spec.lifecycle_path is not None:
            lc_file = spec.lifecycle_path()
            if dry_run:
                _ok(f"Would inject lifecycle block → {lc_file}")
            else:
                changed = _inject_block(lc_file, _lifecycle_block(spec.lifecycle_agent))
                if changed:
                    _ok(f"Lifecycle block injected → {lc_file}")
                else:
                    _skip("Lifecycle block already present")
        elif spec.manual_lifecycle and spec.manual_note:
            _warn(f"REQUIRED — {spec.manual_note}")

    # Worker service
    _section("7. Background worker service")
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

    # 7. Doctor
    _section("8. Verification")
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
    if not dry_run:
        mark_setup_done()
