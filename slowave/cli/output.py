"""Professional OSS-style console output.

Provides a unified rendering layer for Slowave CLI commands with:
- Deterministic ASCII symbols by default (✓, !, ✗, -) with optional emoji
- Consistent section headers, status labels, and alignment
- NO_COLOR environment variable support
- JSON serialization for all output modes
- Actionable error/warning messages
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Optional, Literal


class Status(Enum):
    """Status indicator for checks and items."""
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class Color(Enum):
    """ANSI color codes."""
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


@dataclass
class CheckResult:
    """Result of a single diagnostic check."""
    label: str
    status: Status
    detail: str = ""
    remediation: str = ""


class ConsoleRenderer:
    """Unified output renderer for Slowave CLI."""
    
    def __init__(self, use_emoji: bool = False, use_color: bool = True):
        """Initialize renderer.
        
        Args:
            use_emoji: Use emoji symbols instead of ASCII. Defaults to False.
            use_color: Use ANSI colors. Respects NO_COLOR environment variable.
        """
        self.use_emoji = use_emoji
        # NO_COLOR env var disables color (https://no-color.org/)
        self.use_color = use_color and not os.environ.get("NO_COLOR")
        
    def _symbol(self, status: Status) -> str:
        """Get status symbol."""
        if self.use_emoji:
            symbols_emoji = {
                Status.OK: "✅",
                Status.WARN: "⚠️ ",
                Status.FAIL: "❌",
                Status.SKIP: "⏭️ ",
            }
            return symbols_emoji[status]
        else:
            symbols_ascii = {
                Status.OK: "✓",
                Status.WARN: "!",
                Status.FAIL: "✗",
                Status.SKIP: "-",
            }
            return symbols_ascii[status]
    
    def _colorize(self, text: str, color: Color) -> str:
        """Apply ANSI color if enabled."""
        if not self.use_color:
            return text
        return f"{color.value}{text}{Color.RESET.value}"
    
    def section(self, title: str) -> None:
        """Print a section header."""
        click().echo()
        click().echo(self._colorize(f"  {title}", Color.BOLD))
        click().echo(f"  {self._colorize('─' * (len(title)), Color.DIM)}")
    
    def check(
        self,
        label: str,
        status: Status,
        detail: str = "",
        remediation: str = "",
    ) -> None:
        """Print a single check result."""
        symbol = self._symbol(status)
        status_color = {
            Status.OK: Color.GREEN,
            Status.WARN: Color.YELLOW,
            Status.FAIL: Color.RED,
            Status.SKIP: Color.DIM,
        }[status]
        
        status_text = self._colorize(symbol, status_color)
        msg = f"  {status_text}  {label}"
        
        if detail:
            msg += f"\n      {self._colorize(detail, Color.DIM)}"
        if remediation:
            msg += f"\n      {remediation}"
        
        click().echo(msg)
    
    def item(self, label: str, value: Any, dim: bool = False) -> None:
        """Print a key-value item."""
        value_str = str(value)
        if dim:
            value_str = self._colorize(value_str, Color.DIM)
        click().echo(f"  {label:<25} {value_str}")
    
    def summary(self, ok: bool, message: str) -> None:
        """Print final summary."""
        click().echo()
        status = Status.OK if ok else Status.WARN
        symbol = self._symbol(status)
        status_text = self._colorize(symbol, Color.GREEN if ok else Color.YELLOW)
        click().echo(f"  {status_text}  {message}")
        click().echo()
    
    def warning(self, message: str, remediation: str = "") -> None:
        """Print a warning with optional remediation."""
        msg = f"  {self._symbol(Status.WARN)}  {message}"
        if remediation:
            msg += f"\n      {remediation}"
        click().echo(msg)
    
    def error(self, message: str, remediation: str = "") -> None:
        """Print an error with optional remediation."""
        msg = f"  {self._symbol(Status.FAIL)}  {message}"
        if remediation:
            msg += f"\n      {remediation}"
        click().echo(msg)
    
    def hint(self, message: str) -> None:
        """Print a hint/suggestion."""
        msg = self._colorize(f"💡 {message}", Color.DIM)
        click().echo(f"  {msg}")
    
    def title(self, title: str, version: str = "") -> None:
        """Print a command title."""
        click().echo()
        msg = title
        if version:
            msg += f"  {self._colorize(version, Color.DIM)}"
        click().echo(self._colorize(f"  {msg}", Color.BOLD))
    
    def json(self, data: dict[str, Any]) -> None:
        """Output data as JSON."""
        click().echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def click():
    """Lazy import click to avoid circular dependency."""
    import click as _click
    return _click


def get_renderer(use_emoji: bool = False) -> ConsoleRenderer:
    """Factory function to create a renderer.
    
    Args:
        use_emoji: Force emoji mode (default respects env var).
        
    Returns:
        ConsoleRenderer configured based on environment.
    """
    # Check for emoji preference in env or arg
    use_emoji = use_emoji or os.environ.get("SLOWAVE_EMOJI") == "1"
    return ConsoleRenderer(use_emoji=use_emoji)


def status_symbol(status: Status, use_emoji: bool = False) -> str:
    """Get status symbol for use in inline labels."""
    if use_emoji:
        return {"ok": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭️"}[status.value]
    return {"ok": "✓", "warn": "!", "fail": "✗", "skip": "-"}[status.value]
