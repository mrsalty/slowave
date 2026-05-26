"""Contradiction judge.

When a new candidate claim arrives for a prototype that already has a
schema, we ask the LLM whether the new claim reinforces, refines,
contradicts, or is unrelated to the existing one.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from slowave.llm.base import LLMBackend

log = logging.getLogger(__name__)

_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "llm" / "prompts" / "judge_contradiction.txt"
)

Verdict = Literal["reinforces", "refines", "contradicts", "unrelated"]


@dataclass(frozen=True)
class JudgeResult:
    verdict: Verdict
    reasoning: str


class ContradictionJudge:
    def __init__(self, llm: LLMBackend):
        self.llm = llm
        self._template = _PROMPT_PATH.read_text(encoding="utf-8")

    def judge(
        self,
        *,
        existing_type: str,
        existing_text: str,
        new_type: str,
        new_text: str,
    ) -> JudgeResult:
        prompt = (
            self._template
            .replace("{{EXISTING_TYPE}}", existing_type)
            .replace("{{EXISTING_TEXT}}", existing_text)
            .replace("{{NEW_TYPE}}", new_type)
            .replace("{{NEW_TEXT}}", new_text)
        )
        try:
            resp = self.llm.complete_json(prompt=prompt)
        except (ValueError, RuntimeError) as e:
            log.warning("contradiction judge failed: %s", e)
            # On failure, default to reinforces (safe: no schema gets superseded by error).
            return JudgeResult(verdict="reinforces", reasoning=f"judge_error: {e}")

        v = str(resp.get("verdict", "")).lower().strip()
        r = str(resp.get("reasoning", "")).strip()
        if v not in ("reinforces", "refines", "contradicts", "unrelated"):
            v = "reinforces"
        return JudgeResult(verdict=v, reasoning=r)
