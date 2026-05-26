"""Ollama LLM backend with strict-JSON output.

Uses Ollama's /api/chat endpoint with format="json". The model is asked to
return JSON; we parse and validate.
"""
from __future__ import annotations

import json

import urllib.request
import urllib.error

from slowave.llm.base import LLMBackend, LLMBackendConfig


class OllamaBackend(LLMBackend):
    def __init__(self, cfg: LLMBackendConfig | None = None):
        super().__init__()
        self.cfg = cfg or LLMBackendConfig()

    def complete_json(self, *, prompt: str, system: str | None = None) -> dict:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": self.cfg.temperature,
                "num_predict": self.cfg.max_tokens,
            },
        }
        url = f"{self.cfg.base_url.rstrip('/')}/api/chat"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_s) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama request failed: {e}") from e

        try:
            outer = json.loads(body)
        except json.JSONDecodeError as e:
            raise ValueError(f"Ollama returned non-JSON envelope: {body[:200]}") from e

        # Capture per-call token usage. Ollama's /api/chat returns
        # ``prompt_eval_count`` (input tokens evaluated) and
        # ``eval_count`` (output tokens generated). Both are integer
        # totals for this single call.
        self.last_usage = {
            "prompt_tokens": int(outer.get("prompt_eval_count", 0) or 0),
            "completion_tokens": int(outer.get("eval_count", 0) or 0),
        }

        content = outer.get("message", {}).get("content", "")
        if not content:
            raise ValueError(f"Ollama returned empty content; envelope={outer}")

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            # Try to recover: strip code fences if model wrapped output.
            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`").lstrip("json").strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                raise ValueError(
                    f"Ollama returned non-JSON content: {content[:200]}"
                ) from e
