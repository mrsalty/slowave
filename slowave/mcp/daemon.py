"""Daemon lifecycle management for the Slowave HTTP MCP daemon.

Handles PID file creation/cleanup and single-instance enforcement so that
``slowave serve start`` can guarantee only ONE backend process is running.

PID file location: ~/.slowave/daemon.pid  (or SLOWAVE_DAEMON_PID env var)
"""

from __future__ import annotations

import logging
import os
import signal
import sys
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


def _cleanup_stale_pid_file() -> None:
    """Remove the PID file when the stored PID no longer exists or isn't a slowave process."""
    pid_path = _pid_file_path()
    try:
        if pid_path.exists():
            pid_path.unlink()
            log.info("Removed stale PID file: %s", pid_path)
    except Exception as e:
        log.warning("Could not remove stale PID file %s: %s", pid_path, e)


def _pid_exists(pid: int) -> bool:
    """Return True if a process with *pid* is alive, cross-platform.

    On Unix this uses ``os.kill(pid, 0)``.  On Windows signal 0 is not
    supported, so we use ``ctypes.windll.kernel32.OpenProcess``.
    """
    if sys.platform != "win32":
        # Unix: signal 0 does an existence check without sending a signal.
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists, but owned by another user
        return True

    # ---------- Windows ----------
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle == 0:
        # 87 = invalid parameter (pid doesn't exist), 5 = access denied
        # (exists but we can't open it — treat as running).
        err = ctypes.get_last_error()
        if err == 87:  # ERROR_INVALID_PARAMETER
            return False
        # err 5 = ERROR_ACCESS_DENIED — process exists, treat as alive.
        return err == 5
    kernel32.CloseHandle(handle)
    return True


def _is_slowave_process(pid: int) -> bool:
    """Check whether *pid* is actually a slowave process (not a PID-reuse collision).

    On Unix uses ``ps``, on Windows uses ``tasklist /V``.
    Returns True when verification succeeds and ``slowave`` appears in the
    command line; returns True on any error so a live daemon is never falsely
    rejected.
    """
    import subprocess

    try:
        if sys.platform == "win32":
            # tasklist /V gives verbose output including the window title.
            # /FI "PID eq N" /FO CSV /NH gives CSV without header.
            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"PID eq {pid}",
                    "/V",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "slowave" in result.stdout
        else:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "args="],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return "slowave" in result.stdout
    except Exception:
        # Can't verify — err on the side of not breaking a live daemon.
        return True


def is_running() -> bool:
    """Return True if a daemon process with the stored PID is alive *and* is a slowave process."""
    pid = read_pid()
    if pid is None:
        return False

    if not _pid_exists(pid):
        _cleanup_stale_pid_file()
        return False

    # PID exists, but verify it's actually a slowave process (not a PID-reuse
    # collision from a SIGKILL'd daemon whose PID was reassigned).
    if not _is_slowave_process(pid):
        _cleanup_stale_pid_file()
        return False
    return True


def stop_daemon() -> bool:
    """Send SIGTERM (or terminate on Windows) to the running daemon.

    Returns True if a signal was sent, False if no daemon was found.
    Cleans up the stale PID file when the stored process is already gone.
    """
    pid = read_pid()
    if pid is None:
        return False
    try:
        if sys.platform == "win32":
            # Windows: use taskkill /PID to terminate the process
            import subprocess

            subprocess.run(
                ["taskkill", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
            log.info("Terminated daemon pid=%d via taskkill", pid)
        else:
            os.kill(pid, signal.SIGTERM)
            log.info("Sent SIGTERM to daemon pid=%d", pid)
        return True
    except ProcessLookupError:
        log.warning("Daemon pid=%d not found — removing stale PID file.", pid)
        _cleanup_stale_pid_file()
        return False
    except PermissionError as e:
        log.error("Cannot stop daemon pid=%d: %s", pid, e)
        return False
    except Exception as e:
        log.warning("Failed to stop daemon pid=%d: %s", pid, e)
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
