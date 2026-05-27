"""Slowave: brain-inspired memory for AI agents.

Public API entry points are in `slowave.core.engine.SlowaveEngine` and
`slowave.core.config.SlowaveConfig`.
"""
from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine

__all__ = ["SlowaveEngine", "SlowaveConfig"]
__version__ = "0.1.3"
