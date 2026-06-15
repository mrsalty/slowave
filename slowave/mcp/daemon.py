"""Daemon lifecycle management for the Slowave HTTP MCP daemon.

Handles PID file creation/cleanup and single-instance enforcement so that
``slowave serve start`` can guarantee only ONE backend process is running.

PID file location: ~/.slowave/daemon.pid  (or SLOWAVE_DAEMON_PID env var)
"""

from __future__ import annotations

import logging
import os
import signal
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PID_FILE = Path.home() / ".slowave" / "daemon.pid"


def _pid_file_path() -> Path:
    env = os.environ.get("SLOWAVE_DAEMON_PID")
    return Path(env) if env else DEFAULT_PID_FILE


def write_pid() -> Path:
    """Write current process PID to the PID file.

    Creates ~/.slowave/ if it does not exist. Returns the PID file path.
    """
    pid_path = _pid_file_path()
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()))
    log.info("PID file written: %s (pid=%d)", pid_path, os.getpid())
    return pid_path


def remove_pid() -> None:
    """Remove the PID file if it belongs to this process."""
    pid_path = _pid_file_path()
    try:
        if pid_path.exists():
            stored = int(pid_path.read_text().strip())
            if stored == os.getpid():
                pid_path.unlink()
                log.info("PID file removed: %s", pid_path)
    except Exception as e:
        log.warning("Could not remove PID file: %s", e)


def read_pid() -> int | None:
    """Return the PID stored in the PID file, or None if not found / unreadable."""
    pid_path = _pid_file_path()
    try:
        if pid_path.exists():
            return int(pid_path.read_text().strip())
    except Exception:
        pass
    return None


def is_running() -> bool:
    """Return True if a daemon process with the stored PID is alive."""
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)  # signal 0 = existence check, no actual signal sent
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but owned by another user — treat as running
        return True


def stop_daemon() -> bool:
    """Send SIGTERM to the running daemon.

    Returns True if a signal was sent, False if no daemon was found.
    """
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        log.info("Sent SIGTERM to daemon pid=%d", pid)
        return True
    except ProcessLookupError:
        log.warning("Daemon pid=%d not found (already stopped?)", pid)
        return False
    except PermissionError as e:
        log.error("Cannot stop daemon pid=%d: %s", pid, e)
        return False


def daemon_status() -> dict:
    """Return a dict describing daemon state for `slowave serve status`."""
    pid = read_pid()
    running = is_running()
    return {
        "running": running,
        "pid": pid if running else None,
        "pid_file": str(_pid_file_path()),
    }
