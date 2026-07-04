"""Tests for B-10: scope filtering at candidate generation time.

FTS and prototype-derived schema candidates were collected unscoped,
then filtered later. Now scope filtering happens immediately after
collection, preventing cross-scope candidates from entering the
candidate pool in strict_scope mode.
"""
from __future__ import annotations

import numpy as np
import pytest

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine


class _StubEncoder:
    def __init__(self, dim: int = 32):
        self._dim = dim

    def encode(self, text: str) -> np.ndarray:
        seed = int(abs(hash(text)) % (2**31))
        v = np.random.default_rng(seed).standard_normal(self._dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-12)


def _make_engine(tmp_path, dim: int = 32) -> SlowaveEngine:
    eng = SlowaveEngine(
        SlowaveConfig(db_path=str(tmp_path / "test.db"), dim=dim, disable_encoder=True)
    )
    eng.encoder = _StubEncoder(dim)
    return eng


@pytest.fixture()
def eng(tmp_path):
    engine = _make_engine(tmp_path)
    yield engine
    engine.close()


def test_strict_scope_excludes_other_scope_schemas(eng):
    """Memories in scope A must not appear in scope B's strict_scope recall."""
    # Create schema in scope A
    r_a = eng.remember(
        content="SQLite is the database for project Alpha.",
        type="fact",
        scope="project:alpha",
    )
    # Create schema in scope B
    r_b = eng.remember(
        content="SQLite is the database for project Beta.",
        type="fact",
        scope="project:beta",
    )

    # Recall in scope A — must NOT include scope B's schema
    result = eng.recall("SQLite database", scope="project:alpha", mode="strict_scope")
    schema_ids = {s.id for s in result.schemas}
    assert r_b.schema_id not in schema_ids, "Scope B schema leaked into scope A recall"

    # Recall in scope B — must NOT include scope A's schema
    result_b = eng.recall("SQLite database", scope="project:beta", mode="strict_scope")
    schema_ids_b = {s.id for s in result_b.schemas}
    assert r_a.schema_id not in schema_ids_b, "Scope A schema leaked into scope B recall"


def test_same_scope_recall_returns_own_schema(eng):
    """Schema in scope A must be found in scope A's recall."""
    r = eng.remember(
        content="The project uses Redis for caching.",
        type="fact",
        scope="project:alpha",
    )
    result = eng.recall("Redis caching", scope="project:alpha", mode="strict_scope")
    schema_ids = {s.id for s in result.schemas}
    assert r.schema_id in schema_ids

def test_fts_candidates_are_scope_filtered(eng, tmp_path):
    """End-to-end: schema in wrong scope does not appear via FTS recall."""

    # Create a very specific term in scope alpha
    eng.remember(
        content="The flibberwocket is configured with retries=3.",
        type="fact",
        scope="project:alpha",
    )
    # Same term in scope beta
    eng.remember(
        content="The flibberwocket is configured with retries=5.",
        type="fact",
        scope="project:beta",
    )

    result = eng.recall("flibberwocket", scope="project:alpha", mode="strict_scope")
    # Should only find the alpha schema
    for s in result.schemas:
        if "retries=5" in (s.content_text or ""):
            pytest.fail("Scope beta schema leaked into alpha FTS recall")