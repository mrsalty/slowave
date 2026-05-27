"""Filesystem path helpers for Slowave."""
from __future__ import annotations

import os


def default_db_path() -> str:
    """Return the default local Slowave SQLite database path.

    `SLOWAVE_DB` remains an escape hatch for alternate installations/tests, but
    normal local usage should not require passing `--db` everywhere.
    """
    return os.path.expanduser(os.environ.get("SLOWAVE_DB", "~/.slowave/slowave.db"))