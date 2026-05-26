"""LLM backend selection.

Use ``make_backend(cfg)`` to construct the right backend from an
``LLMBackendConfig``. ``cfg.backend`` selects between:

  * ``"ollama"`` (default, local) — see ``OllamaBackend``
  * ``"openrouter"`` (cloud, OpenAI-compatible) — see ``OpenRouterBackend``

Auto-detection: if ``cfg.backend`` is empty/``"auto"``, the factory
falls back to OpenRouter when the model identifier contains a "/"
(e.g. ``"anthropic/claude-3.5-haiku"``) and to Ollama otherwise.
"""
from __future__ import annotations

from slowave.llm.base import LLMBackend, LLMBackendConfig


def make_backend(cfg: LLMBackendConfig) -> LLMBackend:
    """Build the LLM backend instance described by ``cfg``."""
    backend = (cfg.backend or "auto").lower()
    if backend == "auto":
        backend = "openrouter" if "/" in cfg.model else "ollama"

    if backend == "ollama":
        from slowave.llm.ollama_backend import OllamaBackend
        return OllamaBackend(cfg)
    if backend == "openrouter":
        from slowave.llm.openrouter_backend import OpenRouterBackend
        return OpenRouterBackend(cfg)
    raise ValueError(
        f"Unknown LLM backend: {cfg.backend!r}. "
        f"Expected one of: 'ollama', 'openrouter', 'auto'."
    )


__all__ = ["LLMBackend", "LLMBackendConfig", "make_backend"]

