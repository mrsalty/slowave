"""OpenRouter LLM backend with strict-JSON output.

Uses OpenRouter's /api/v1/chat/completions endpoint (OpenAI-compatible).
The model is asked to return JSON; we parse and validate.

API key is read from one of (in order):
  1. cfg.api_key
  2. OPENROUTER_API_KEY environment variable
  3. raises RuntimeError

Common model identifiers (as of 2026-05):
  anthropic/claude-3.5-haiku
  anthropic/claude-3.5-sonnet
  openai/gpt-4o-mini
  openai/gpt-4o
  google/gemini-flash-1.5
  deepseek/deepseek-chat
  meta-llama/llama-3.3-70b-instruct
  qwen/qwen-2.5-72b-instruct

See https://openrouter.ai/models for the full list.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request

from slowave.llm.base import LLMBackend, LLMBackendConfig


DEFAULT_OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def _build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context that works on macOS Pythons that lack a system
    CA bundle by falling back to certifi when available."""
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


class OpenRouterBackend(LLMBackend):
    def __init__(self, cfg: LLMBackendConfig | None = None):
        super().__init__()
        self.cfg = cfg or LLMBackendConfig(
            model="anthropic/claude-3.5-haiku",
            base_url=DEFAULT_OPENROUTER_BASE,
        )
        # Resolve API key
        self.api_key = (
            getattr(self.cfg, "api_key", None)
            or os.environ.get("OPENROUTER_API_KEY")
        )
        if not self.api_key:
            raise RuntimeError(
                "OpenRouter API key not found. Set OPENROUTER_API_KEY env var "
                "or pass api_key in LLMBackendConfig."
            )
        # Normalize base_url
        if "openrouter" not in self.cfg.base_url:
            self._base_url = DEFAULT_OPENROUTER_BASE
        else:
            self._base_url = self.cfg.base_url.rstrip("/")
        # Shared SSL context across calls (cheap to build but no need to redo).
        self._ssl_context = _build_ssl_context()

    def complete_json(self, *, prompt: str, system: str | None = None) -> dict:
        # Force strict JSON output regardless of provider. Some providers
        # (notably Anthropic via OpenRouter) ignore response_format and
        # like to wrap JSON in prose. We:
        #   1. Strengthen the system prompt
        #   2. Pre-fill the assistant message with "{" so the model can only
        #      continue a JSON object.
        json_system = (
            "You are a strict JSON-only API. Output exactly one JSON object "
            "and nothing else. No preamble, no markdown code fences, no "
            "trailing prose. The first character of your reply MUST be '{' "
            "and the last MUST be '}'."
        )
        if system:
            json_system = f"{system}\n\n{json_system}"

        messages = [
            {"role": "system", "content": json_system},
            {"role": "user", "content": prompt},
            # Assistant pre-fill: the model continues from here, locking the
            # output to a JSON object. We re-attach "{" to the parsed result.
            {"role": "assistant", "content": "{"},
        ]

        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
            # OpenRouter passes this through to providers that support it
            # (OpenAI, Anthropic). Models that don't support it ignore it.
            "response_format": {"type": "json_object"},
        }
        url = f"{self._base_url}/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                # OpenRouter ranking/attribution headers (optional but encouraged)
                "HTTP-Referer": "https://github.com/yourusername/slowave",
                "X-Title": "Slowave brain-inspired memory",
            },
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self.cfg.timeout_s, context=self._ssl_context
            ) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            raise RuntimeError(
                f"OpenRouter HTTP {e.code} for model={self.cfg.model}: {err_body[:300]}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"OpenRouter request failed: {e}") from e

        try:
            outer = json.loads(body)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"OpenRouter returned non-JSON envelope: {body[:200]}"
            ) from e

        # Capture per-call token usage. OpenRouter forwards the
        # upstream provider's standard OpenAI-style ``usage`` dict.
        usage = outer.get("usage") or {}
        self.last_usage = {
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
        }

        choices = outer.get("choices") or []
        if not choices:
            raise ValueError(
                f"OpenRouter returned no choices; envelope={str(outer)[:300]}"
            )
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise ValueError(
                f"OpenRouter returned empty content; envelope={str(outer)[:300]}"
            )

        # Parse the inner JSON the model produced. Some providers wrap it in
        # markdown code fences when response_format isn't honoured.
        # We pre-filled the assistant turn with "{", so the model's reply
        # starts AFTER that "{". Re-attach it here. Some providers (OpenAI
        # honouring response_format) ignore the pre-fill and return a full
        # "{...}" themselves; that case is also handled by the parser below.
        candidates = [content]
        if not content.lstrip().startswith("{"):
            candidates.insert(0, "{" + content)
        for cand in candidates:
            try:
                return json.loads(cand)
            except json.JSONDecodeError:
                continue
        # Heavier recovery
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`").lstrip("json").strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass
            # Last resort: scan for the first '{' and try matching braces.
            start = cleaned.find("{")
            if start >= 0:
                depth = 0
                for i in range(start, len(cleaned)):
                    if cleaned[i] == "{":
                        depth += 1
                    elif cleaned[i] == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = cleaned[start:i + 1]
                            try:
                                return json.loads(candidate)
                            except json.JSONDecodeError:
                                break
            raise ValueError(
                f"OpenRouter returned non-JSON content (model={self.cfg.model}): "
                f"{content[:300]}"
            ) from e
