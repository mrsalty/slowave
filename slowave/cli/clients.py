"""Client status checking for doctor command."""
from __future__ import annotations
import subprocess
from dataclasses import dataclass
from slowave.cli.output import Status

@dataclass
class ClientStatus:
    name: str
    mcp_configured: bool = False
    hooks_installed: bool = False
    lifecycle_enabled: bool = False
    running: bool = False

def get_client_statuses() -> dict[str, ClientStatus]:
    statuses = {}
    try:
        from slowave.cli.setup import (
            _claude_settings_path, _claude_json_path, _claude_desktop_config_path,
            _cline_mcp_settings_path, _claude_md_path, _clinerules_path,
            _read_json, _MARKER_START,
        )
        cc_json = _claude_json_path()
        cc_settings = _claude_settings_path()
        cc_md = _claude_md_path()
        cc_has_mcp = cc_has_hooks = cc_has_lifecycle = False
        
        if cc_json.exists():
            try:
                cfg_j = _read_json(cc_json)
                cc_has_mcp = "slowave" in cfg_j.get("mcpServers", {})
            except: pass
        if cc_settings.exists():
            try:
                cfg = _read_json(cc_settings)
                if not cc_has_mcp:
                    cc_has_mcp = "slowave" in cfg.get("mcpServers", {})
                cc_has_hooks = any(
                    "SLOWAVE MANDATORY" in str(h.get("command", ""))
                    for group in cfg.get("hooks", {}).get("UserPromptSubmit", [])
                    for h in group.get("hooks", [])
                )
            except: pass
        if cc_md.exists():
            try: cc_has_lifecycle = _MARKER_START in cc_md.read_text(encoding="utf-8", errors="ignore")
            except: pass
        
        if cc_json.exists() or cc_settings.exists() or cc_md.exists():
            statuses["claude_code"] = ClientStatus(
                name="Claude Code", mcp_configured=cc_has_mcp,
                hooks_installed=cc_has_hooks, lifecycle_enabled=cc_has_lifecycle,
            )
        
        cd_config = _claude_desktop_config_path()
        if cd_config.exists():
            cd_has_mcp = False
            try:
                cfg = _read_json(cd_config)
                cd_has_mcp = "slowave" in cfg.get("mcpServers", {})
            except: pass
            statuses["claude_desktop"] = ClientStatus(
                name="Claude Desktop", mcp_configured=cd_has_mcp,
            )
        
        cline_mcp = _cline_mcp_settings_path()
        cline_rules = _clinerules_path()
        cline_has_mcp = cline_has_lifecycle = False
        if cline_mcp.exists():
            try:
                cfg = _read_json(cline_mcp)
                cline_has_mcp = "slowave" in cfg.get("mcpServers", {})
            except: pass
        if cline_rules.exists():
            try: cline_has_lifecycle = _MARKER_START in cline_rules.read_text(encoding="utf-8", errors="ignore")
            except: pass
        if cline_mcp.exists() or cline_rules.exists():
            statuses["cline"] = ClientStatus(
                name="Cline", mcp_configured=cline_has_mcp,
                lifecycle_enabled=cline_has_lifecycle,
            )
    except ImportError: pass
    
    import platform
    system = platform.system()
    worker_running = False
    try:
        if system == "Darwin":
            result = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
            worker_running = "com.slowave.worker" in result.stdout
        elif system == "Linux":
            result = subprocess.run(["systemctl", "--user", "is-active", "slowave-worker"], capture_output=True, text=True, check=False)
            worker_running = result.returncode == 0
        elif system == "Windows":
            result = subprocess.run(["powershell", "-Command", "Get-ScheduledTask -TaskName SlowaveWorker -ErrorAction SilentlyContinue"], capture_output=True, text=True, check=False)
            worker_running = "SlowaveWorker" in result.stdout
    except: pass
    
    statuses["worker"] = ClientStatus(name="Background worker", running=worker_running)
    return statuses

def summarize_client_status(client: ClientStatus) -> tuple[Status, str]:
    if "worker" in client.name.lower():
        return (Status.OK if client.running else Status.SKIP, "running" if client.running else "not running")
    if "desktop" in client.name.lower():
        if not client.mcp_configured:
            return (Status.SKIP, "not configured")
        return (Status.WARN, "MCP configured; custom instructions missing")
    if client.mcp_configured:
        parts = ["MCP"]
        if client.hooks_installed: parts.append("hooks")
        if client.lifecycle_enabled: parts.append("lifecycle")
        return (Status.OK, ", ".join(parts))
    return (Status.SKIP, "not configured")
