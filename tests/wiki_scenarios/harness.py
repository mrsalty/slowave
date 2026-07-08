"""WikiHarness: thin wrapper around TemporalHarness for Wikipedia-based scenarios.

Follows the same pattern as tests/temporal_eval/harness.py exactly.  Only adds:
  - ingest_page(title, consolidate)  — opens a scoped session per page
  - build_hypothesis(result) -> str  — assembles result text for keyword testing
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from slowave.core.engine import RecallResult
from slowave.latent.types import QueryDiagnostics
from slowave.symbolic.encoder import TextEncoder
from tests.temporal_eval.harness import ScenarioResult, TemporalHarness, keyword_hit
from tests.wiki_scenarios.corpus import paragraphs_for


class WikiHarness(TemporalHarness):
    """TemporalHarness extended with Wikipedia page ingestion."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_query_diagnostics: QueryDiagnostics | None = None

    def query(self, text: str, *, top_k: int = 5) -> RecallResult:
        self.eng.refresh_indices()
        result = self.eng.recall(text, top_k=top_k, diagnose=True)
        self.last_query_diagnostics = result.query_diagnostics
        return result

    def ingest_page(self, title: str, *, consolidate: bool = False) -> int:
        """Load a Wikipedia page as a single scoped session.

        Each paragraph is appended as a user_message turn so the episodic
        memory sees it as a continuous stream of content.  The scope is
        ``wikiscenarios:<title>`` so pages from different domains are
        naturally separated.

        When ablation='no_consolidation', consolidation is suppressed
        regardless of the caller's consolidate argument so G/S families
        are genuinely tested without schema formation.

        Returns number of paragraphs ingested.
        """
        if self.ablation == "no_consolidation":
            consolidate = False
        paras = paragraphs_for(title)
        scope = f"wikiscenarios:{title}"
        turns = [("user", p) for p in paras]
        # Use the inherited session() method which handles timestamps correctly
        self.session(turns, consolidate=consolidate)
        return len(paras)

    @staticmethod
    def build_hypothesis(result: RecallResult, top_schemas: int = 5, top_episodes: int = 10) -> str:
        """Concatenate schema content + episode text into a single string for keyword testing.

        This is the ONLY place we read from the result object.  No DB access,
        no scope parsing, no salience reading — just text.
        """
        parts: list[str] = []
        for s in result.schemas[:top_schemas]:
            if s.content_text:
                parts.append(s.content_text)
        for ep in result.episode_texts[:top_episodes]:
            txt = ep.get("content_text", "")
            if txt:
                parts.append(txt)
        return " ".join(parts)
