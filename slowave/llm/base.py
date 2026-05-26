"""LLMBackend abstraction.

LLM is only called at replay time (schema extraction + contradiction judging).
It is never on the recall hot path.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMBackendConfig:
    model: str = "qwen2.5:7b-instruct"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.1
    max_tokens: int = 1024
    timeout_s: float = 120.0  # per-call timeout; 7-8B models may need 2-3min on first load
    # backend selector: "auto" (default), "ollama" (local), or
    # "openrouter" (API). When "auto", the factory picks openrouter when
    # the model id contains a slash ("anthropic/claude-3.5-haiku") and
    # ollama otherwise ("qwen2.5-coder:1.5b").
    # api_key is optional; if empty, the openrouter backend reads
    # OPENROUTER_API_KEY from the environment.
    backend: str = "auto"
    api_key: str = ""


class LLMBackend(ABC):
    """Strict-JSON LLM interface. Implementations must:

    - return parsed JSON (dict) or raise on failure
    - never hallucinate beyond the prompt
    - be safe to call concurrently from a single replay job
    - track per-call token usage in the ``last_usage`` attribute (a
      dict with at least ``prompt_tokens`` and ``completion_tokens``
      keys). When the provider does not report usage, both fields
      should be 0 — never None — so downstream aggregation is safe.
    """

    # Concrete subclasses populate this after every complete_json call.
    # The reference base implementation initialises it to zeros so
    # callers that read it before any call has happened do not crash.
    def __init__(self) -> None:
        self.last_usage: dict = {"prompt_tokens": 0, "completion_tokens": 0}

    @abstractmethod
    def complete_json(self, *, prompt: str, system: str | None = None) -> dict:
        """Run a completion expecting strict JSON output. Returns parsed dict.

        Raises ValueError if the model output cannot be parsed as JSON.
        """
