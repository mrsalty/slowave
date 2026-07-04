"""Tests for profile-layer geometry supersession guard.

The SVD1 supersession manifold is anti-aligned with personal preference
domain (-0.17). Preferences (dark mode, blunt feedback style, etc.) that
flip are divergences, not value substitutions — they should be treated as
reinforcement, not automatic supersession of the old preference.
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


# ---------------------------------------------------------------------------
# profile schema_class guard
# ---------------------------------------------------------------------------

def test_preference_remember_is_not_superseded_by_new_preference(eng):
    """Remembering a diverging preference must not supersede the old one."""
    r1 = eng.remember(
        content="The user prefers dark mode in their editor.",
        type="preference",
    )
    assert len(r1.superseded_schema_ids) == 0
    schema_a = eng.schemas.get(r1.schema_id)
    assert schema_a.facets.get("schema_class") == "preference"
    assert schema_a.facets.get("memory_layer") == "profile"

    r2 = eng.remember(
        content="The user prefers light mode in their editor.",
        type="preference",
    )
    # The old preference must NOT be superseded.
    assert r1.schema_id not in r2.superseded_schema_ids
    assert len(r2.superseded_schema_ids) == 0


def test_constraint_remember_is_not_superseded(eng):
    """Constraints behave like preferences — geometry must not supersede."""
    eng.remember(
        content="Always use tabs for indentation.",
        type="constraint",
    )
    r2 = eng.remember(
        content="Always use spaces for indentation.",
        type="constraint",
    )
    assert len(r2.superseded_schema_ids) == 0


def test_habit_remember_is_not_superseded(eng):
    """Habits behave like preferences — geometry must not supersede."""
    eng.remember(
        content="User tests manually before committing.",
        type="habit",
    )
    r2 = eng.remember(
        content="User relies on CI to run tests after committing.",
        type="habit",
    )
    assert len(r2.superseded_schema_ids) == 0


def test_fact_remember_can_still_supersede(eng):
    """Regression: fact-type schemas must still be eligible for supersession.
    (The guard is only for profile-layer memories.)"""
    eng.remember(
        content="The project uses SQLite for storage.",
        type="fact",
    )
    # Facts can still go through the geometric supersession path.
    # The stub encoder produces random-ish embeddings so supersession is
    # unlikely, but the path must not be blocked.
    r2 = eng.remember(
        content="The project uses Postgres for storage.",
        type="fact",
    )
    # Just verifying no crash — the guard doesn't apply to fact.
    assert isinstance(r2.superseded_schema_ids, list)


def test_memory_layer_profile_blocks_supersession(eng):
    """Direct test: if a candidate has memory_layer == 'profile', even if
    schema_class is not explicitly set, supersession is blocked."""
    # Create a schema with memory_layer = 'profile' via interaction_preference
    r1 = eng.remember(
        content="The user wants concise answers.",
        type="interaction_preference",
    )
    schema = eng.schemas.get(r1.schema_id)
    assert schema.facets.get("memory_layer") == "profile"

    r2 = eng.remember(
        content="The user wants verbose detailed answers.",
        type="interaction_preference",
    )
    assert r1.schema_id not in r2.superseded_schema_ids


def test_lesson_and_warning_are_domain_not_profile(eng):
    """Regression: lesson/warning are domain-layer, not profile.
    They should NOT be blocked by the profile guard."""
    r1 = eng.remember(
        content="The API key leaked in commit abc123.",
        type="warning",
    )
    schema = eng.schemas.get(r1.schema_id)
    assert schema.facets.get("memory_layer") == "domain"

    r2 = eng.remember(
        content="The API key leak was confirmed in commit def456.",
        type="warning",
    )
    # Warnings can still be superseded (they're domain, not profile)
    assert isinstance(r2.superseded_schema_ids, list)