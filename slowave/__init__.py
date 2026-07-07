"""Slowave: brain-inspired memory for AI agents.

Public API entry points are in `slowave.core.engine.SlowaveEngine` and
`slowave.core.config.SlowaveConfig`.  Import them explicitly to avoid
loading the full engine stack (FAISS, ONNX, sentence-transformers) on
every ``import slowave``.

    from slowave.core.engine import SlowaveEngine
    from slowave.core.config import SlowaveConfig
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("slowave")
except PackageNotFoundError:  # running from source without install
    __version__ = "0.0.0.dev"

__all__ = ["__version__"]
