"""Unit tests for the geometry-only supersession/reinforce/generalize decision tree.

All tests use controlled embeddings and a mocked SupersessionManifold so they
run without a real encoder and without the `requires_model` mark. The geometry
decision logic is exercised deterministically.

Decision tree under test (engine.py remember()):
  cosine >= CROSS_SCOPE_COS_THRESHOLD (0.78), all scopes
    same scope AND cosine >= SAME_SCOPE_COS_THRESHOLD (0.85):
      dir_score >= DIRECTION_THRESHOLD (0.10) → SUPERSEDE
      dir_score in [DIR_REVIEW_BAND (0.05), 0.10) → NEEDS_REVIEW
      dir_score < DIR_REVIEW_BAND (0.05) → REINFORCE
    different scope AND cosine >= 0.78:
      dir_score < DIRECTION_THRESHOLD → CROSS-SCOPE REINFORCE + evidence
      dir_score >= DIRECTION_THRESHOLD → skip (cross-scope value divergence is valid)
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import numpy as np
import pytest

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.core.supersession_manifold import (
    CROSS_SCOPE_COS_THRESHOLD,
    DIR_REVIEW_BAND,
    DIRECTION_THRESHOLD,
    SAME_SCOPE_COS_THRESHOLD,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DIM = 32


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / (n + 1e-12)


def _make_pair(cos_target: float, dim: int = DIM) -> tuple[np.ndarray, np.ndarray]:
    """Return two unit vectors with cosine ≈ cos_target."""
    base = _unit(np.ones(dim, dtype=np.float32))
    perp = np.zeros(dim, dtype=np.float32)
    perp[0] = 1.0
    perp = _unit(perp - np.dot(perp, base) * base)
    angle = np.arccos(np.clip(cos_target, -1.0, 1.0))
    b = _unit((np.cos(angle) * base + np.sin(angle) * perp).astype(np.float32))
    return base, b


class _ControlledEncoder:
    """Returns pre-defined embeddings by text key, deterministic random otherwise."""

    def __init__(self, mapping: dict[str, np.ndarray], dim: int = DIM):
        self._map = mapping
        self._dim = dim

    def encode(self, text: str) -> np.ndarray:
        if text in self._map:
            return self._map[text].copy()
        seed = int(abs(hash(text)) % (2**31))
        v = np.random.default_rng(seed).standard_normal(self._dim).astype(np.float32)
        return _unit(v)

    def encode_many(self, texts: list[str]) -> list[np.ndarray]:
        return [self.encode(t) for t in texts]


class _MockManifold:
    """Returns a fixed direction_score for all pairs."""

    def __init__(self, score: float):
        self._score = score

    def direction_score(self, emb_new: np.ndarray, emb_old: np.ndarray) -> float:
        return self._score

    def invalidate(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db() -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    yield tmp.name
    for ext in ("", "-wal", "-shm"):
        p = tmp.name + ext
        if os.path.exists(p):
            os.remove(p)


def _eng(tmp_db: str, encoder: _ControlledEncoder, manifold: _MockManifold) -> SlowaveEngine:
    cfg = SlowaveConfig(db_path=tmp_db, dim=DIM, disable_encoder=True)
    eng = SlowaveEngine(cfg)
    eng.encoder = encoder
    # Set _manifold directly — _get_manifold() returns it when non-None
    eng._manifold = manifold
    return eng


def _remember(eng: SlowaveEngine, text: str, scope: str | None = None) -> int:
    """Convenience wrapper; returns schema_id."""
    return eng.remember(content=text, type="fact", scope=scope).schema_id


# ---------------------------------------------------------------------------
# Same-scope tests
# ---------------------------------------------------------------------------


class TestSameScopeGeometry:
    """Geometry decision tree for same-scope remember() calls."""

    def test_high_dir_score_supersedes(self, tmp_db: str) -> None:
        """cos >= 0.85 AND dir_score >= 0.10 → old schema superseded."""
        v_old, v_new = _make_pair(0.93)
        enc = _ControlledEncoder({"old": v_old, "new": v_new})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.25))

        old_id = _remember(eng, "old", scope="project:test")
        _remember(eng, "new", scope="project:test")

        assert eng.schemas.get(old_id).status == "superseded"
        eng.close()

    def test_low_dir_score_reinforces_not_supersedes(self, tmp_db: str) -> None:
        """cos >= 0.85 AND dir_score < 0.05 → reinforce, not supersede."""
        v_old, v_new = _make_pair(0.93)
        enc = _ControlledEncoder({"old": v_old, "new": v_new})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.02))

        old_id = _remember(eng, "old", scope="project:test")
        old_salience_before = eng.schemas.get(old_id).salience
        _remember(eng, "new", scope="project:test")

        old_schema = eng.schemas.get(old_id)
        assert (
            old_schema.status == "active"
        ), f"Restatement must not supersede (was {old_schema.status})"
        assert old_schema.salience > old_salience_before, "Restatement should bump salience"
        eng.close()

    def test_mid_dir_score_flags_needs_review(self, tmp_db: str) -> None:
        """cos >= 0.85 AND dir_score in [0.05, 0.10) → needs_review, no irreversible action."""
        v_old, v_new = _make_pair(0.93)
        enc = _ControlledEncoder({"old": v_old, "new": v_new})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.07))

        old_id = _remember(eng, "old", scope="project:test")
        _remember(eng, "new", scope="project:test")

        old_schema = eng.schemas.get(old_id)
        assert old_schema.status == "active", "Ambiguous dir_score must not auto-supersede"
        assert old_schema.needs_review, "Ambiguous dir_score should flag needs_review"
        eng.close()

    def test_cosine_below_extended_threshold_no_action(self, tmp_db: str) -> None:
        """cos < 0.70 (EXTENDED_SAME_SCOPE_COS_THRESHOLD) → no action at all."""
        v_old, v_new = _make_pair(0.60)
        enc = _ControlledEncoder({"old": v_old, "new": v_new})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.30))

        old_id = _remember(eng, "old", scope="project:test")
        _remember(eng, "new", scope="project:test")

        assert (
            eng.schemas.get(old_id).status == "active"
        ), "cos < EXTENDED_SAME_SCOPE_COS_THRESHOLD must not trigger any action"
        eng.close()

    def test_extended_range_high_dir_score_supersedes(self, tmp_db: str) -> None:
        """cos in [0.70, 0.85) AND dir_score >= 0.10 → supersede (Gap 3)."""
        v_old, v_new = _make_pair(0.81)
        enc = _ControlledEncoder({"old": v_old, "new": v_new})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.25))

        old_id = _remember(eng, "old", scope="project:test")
        _remember(eng, "new", scope="project:test")

        assert (
            eng.schemas.get(old_id).status == "superseded"
        ), "cos in extended range + high dir_score should supersede (Gap 3)"
        eng.close()

    def test_extended_range_low_dir_score_no_action(self, tmp_db: str) -> None:
        """cos in [0.70, 0.85) AND dir_score < 0.10 → no action (too ambiguous)."""
        v_old, v_new = _make_pair(0.81)
        enc = _ControlledEncoder({"old": v_old, "new": v_new})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.02))

        old_id = _remember(eng, "old", scope="project:test")
        salience_before = eng.schemas.get(old_id).salience
        _remember(eng, "new", scope="project:test")

        old_schema = eng.schemas.get(old_id)
        assert old_schema.status == "active", "Low dir_score in extended range must not supersede"
        assert (
            old_schema.salience == salience_before
        ), "Low dir_score in extended range must not reinforce"
        eng.close()

    def test_cosine_below_cross_scope_threshold_no_action(self, tmp_db: str) -> None:
        """cos < 0.78 → no action regardless of dir_score."""
        v_old, v_new = _make_pair(0.50)
        enc = _ControlledEncoder({"old": v_old, "new": v_new})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.50))

        old_id = _remember(eng, "old", scope="project:test")
        salience_before = eng.schemas.get(old_id).salience
        _remember(eng, "new", scope="project:test")

        old_schema = eng.schemas.get(old_id)
        assert old_schema.status == "active"
        assert old_schema.salience == salience_before, "Low cosine must trigger no action"
        eng.close()

    def test_superseded_excluded_from_default_recall(self, tmp_db: str) -> None:
        """Superseded schemas must not surface in default recall."""
        v_old, v_new = _make_pair(0.93)
        enc = _ControlledEncoder({"old": v_old, "new": v_new})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.25))

        old_id = _remember(eng, "old", scope="project:test")
        _remember(eng, "new", scope="project:test")

        result = eng.recall("old", scope="project:test")
        assert old_id not in {s.id for s in result.schemas}
        eng.close()

    def test_supersede_recorded_in_result(self, tmp_db: str) -> None:
        """RememberResult.superseded_schema_ids must list the superseded schema."""
        v_old, v_new = _make_pair(0.93)
        enc = _ControlledEncoder({"old": v_old, "new": v_new})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.25))

        old_id = _remember(eng, "old", scope="project:test")
        result = eng.remember(content="new", type="fact", scope="project:test")

        assert old_id in result.superseded_schema_ids
        eng.close()


# ---------------------------------------------------------------------------
# Cross-scope tests
# ---------------------------------------------------------------------------


class TestCrossScopeGeometry:
    """Geometry decision tree for cross-scope remember() calls."""

    def test_same_concept_different_scope_reinforces(self, tmp_db: str) -> None:
        """cos >= 0.78 AND different scope AND dir_score < 0.10 → cross-scope reinforce."""
        v_a, v_b = _make_pair(0.92)
        enc = _ControlledEncoder({"content_a": v_a, "content_b": v_b})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.03))

        id_a = _remember(eng, "content_a", scope="project:alpha")
        salience_before = eng.schemas.get(id_a).salience

        _remember(eng, "content_b", scope="project:beta")

        schema_a = eng.schemas.get(id_a)
        assert schema_a.status == "active", "Cross-scope same-concept must not supersede"
        assert schema_a.salience > salience_before, "Cross-scope same-concept should reinforce"
        eng.close()

    def test_cross_scope_reinforce_records_evidence(self, tmp_db: str) -> None:
        """Cross-scope reinforce records schema_evidence linking the beta raw event."""
        v_a, v_b = _make_pair(0.92)
        enc = _ControlledEncoder({"content_a": v_a, "content_b": v_b})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.03))

        id_a = _remember(eng, "content_a", scope="project:alpha")
        _remember(eng, "content_b", scope="project:beta")

        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM schema_evidence WHERE schema_id = ? AND raw_event_id IS NOT NULL",
            (id_a,),
        ).fetchall()
        conn.close()

        assert len(rows) > 0, "Cross-scope reinforce must add schema_evidence entry"
        eng.close()

    def test_value_divergence_cross_scope_skipped(self, tmp_db: str) -> None:
        """cos >= 0.78 AND different scope AND dir_score >= 0.10 → no action."""
        v_a, v_b = _make_pair(0.92)
        enc = _ControlledEncoder({"content_a": v_a, "content_b": v_b})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.25))

        id_a = _remember(eng, "content_a", scope="project:alpha")
        salience_before = eng.schemas.get(id_a).salience

        _remember(eng, "content_b", scope="project:beta")

        schema_a = eng.schemas.get(id_a)
        assert schema_a.status == "active", "Cross-scope value divergence must not supersede"
        assert (
            schema_a.salience == salience_before
        ), "Cross-scope value divergence must not reinforce"
        eng.close()

    def test_cross_scope_cosine_below_threshold_no_action(self, tmp_db: str) -> None:
        """cos < 0.78 cross-scope → no action even with low dir_score."""
        v_a, v_b = _make_pair(0.60)
        enc = _ControlledEncoder({"content_a": v_a, "content_b": v_b})
        eng = _eng(tmp_db, enc, _MockManifold(score=0.02))

        id_a = _remember(eng, "content_a", scope="project:alpha")
        salience_before = eng.schemas.get(id_a).salience

        _remember(eng, "content_b", scope="project:beta")

        assert (
            eng.schemas.get(id_a).salience == salience_before
        ), "Low cosine cross-scope must trigger no action"
        eng.close()


# ---------------------------------------------------------------------------
# Threshold constants sanity
# ---------------------------------------------------------------------------


class TestThresholdConstants:
    """Verify the module-level thresholds form a valid ordering."""

    def test_threshold_ordering(self) -> None:
        assert 0.0 < DIR_REVIEW_BAND < DIRECTION_THRESHOLD
        assert CROSS_SCOPE_COS_THRESHOLD < SAME_SCOPE_COS_THRESHOLD
        assert CROSS_SCOPE_COS_THRESHOLD > 0.0
        assert SAME_SCOPE_COS_THRESHOLD < 1.0
