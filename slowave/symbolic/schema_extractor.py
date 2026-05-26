"""Schema extractor: turns episode clusters into atomic typed claims."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slowave.llm.base import LLMBackend

log = logging.getLogger(__name__)

_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "llm" / "prompts" / "extract_schema.txt"
)


@dataclass(frozen=True)
class ExtractedSchema:
    claim: str
    facets: dict[str, Any]
    tags: list[str]
    confidence: float
    evidence_indices: list[int]
    evidence_quote: str | None = None


class SchemaExtractor:
    def __init__(self, llm: LLMBackend, *, min_confidence: float = 0.4):
        self.llm = llm
        self.min_confidence = min_confidence
        self._template = _PROMPT_PATH.read_text(encoding="utf-8")
        self.last_debug: dict = {}

    def extract(self, *, episode_texts: list[str]) -> list[ExtractedSchema]:
        """Return zero or more durable atomic claims from a cluster."""
        if not episode_texts:
            return []
        rendered = "\n\n".join(f"[{i + 1}] {t}" for i, t in enumerate(episode_texts))
        prompt = self._template.replace("{{EPISODES}}", rendered)
        self.last_debug = {"prompt_text": prompt, "response_json": {}, "extracted_claims": []}
        try:
            resp = self.llm.complete_json(prompt=prompt)
        except (ValueError, RuntimeError) as e:
            log.warning("schema extraction failed: %s", e)
            self.last_debug = {"prompt_text": prompt, "response_json": {"error": str(e)}, "extracted_claims": []}
            return []
        self.last_debug["response_json"] = resp

        raw_claims = resp.get("claims")
        # Tolerate old single-claim JSON while prompts/models settle, but new
        # architecture expects multi-claim output.
        if raw_claims is None and "claim" in resp:
            raw_claims = [resp]
        if not isinstance(raw_claims, list):
            return []

        out: list[ExtractedSchema] = []
        seen: set[str] = set()
        for item in raw_claims:
            if not isinstance(item, dict):
                continue
            if bool(item.get("skip", False)):
                continue
            claim = str(item.get("claim", "")).strip()
            if not claim:
                continue
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < self.min_confidence:
                continue
            raw_evidence = item.get("evidence_indices", [])
            if not isinstance(raw_evidence, list):
                raw_evidence = []
            evidence_indices = []
            for idx in raw_evidence:
                try:
                    i = int(idx)
                except (TypeError, ValueError):
                    continue
                if 1 <= i <= len(episode_texts):
                    evidence_indices.append(i)
            if not evidence_indices:
                evidence_indices = list(range(1, len(episode_texts) + 1))
            key = claim.lower()
            if key in seen:
                continue
            seen.add(key)
            facets = item.get("facets", {})
            if not isinstance(facets, dict):
                facets = {}
            tags = item.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            evidence_quote_raw = item.get("evidence_quote")
            evidence_quote = None
            if evidence_quote_raw is not None:
                evidence_quote = str(evidence_quote_raw).strip()[:500] or None
            out.append(
                ExtractedSchema(
                    claim=claim,
                    facets=facets,
                    tags=[str(t) for t in tags],
                    confidence=max(0.0, min(1.0, confidence)),
                    evidence_indices=list(dict.fromkeys(evidence_indices)),
                    evidence_quote=evidence_quote,
                )
            )
        self.last_debug["extracted_claims"] = [
            {
                "claim": x.claim,
                "facets": x.facets,
                "tags": x.tags,
                "confidence": x.confidence,
                "evidence_indices": x.evidence_indices,
                "evidence_quote": x.evidence_quote,
            }
            for x in out
        ]
        return out