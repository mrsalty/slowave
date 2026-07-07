"""Unit tests for TransitionModel.predict — previously untested.

Covers the three bugs identified in the Opus review:
  1. kwarg typo: search(..., k=1) -> search(..., top_k=1)
  2. wrong SQL column names: dst/src -> dst_prototype_id/src_prototype_id
  3. TransitionModel auto-instantiation in engine (tested via engine fixture)

Each test creates real in-memory SQLite stores so the full code path
(FAISS search + SQL edge query) executes without mocking.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.latent.graph_manager import GraphConfig, GraphManager
from slowave.latent.semantic_store import SemanticStore, SemanticStoreConfig
from slowave.latent.transition_model import TransitionModel, TransitionModelConfig
from slowave.storage.sqlite_db import SQLiteConfig, SQLiteDB

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = str(REPO_ROOT / "slowave" / "storage" / "schema.sql")


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = SQLiteDB(SQLiteConfig(path=path))
    db.init_schema(SCHEMA_PATH)
    yield db
    db.close()
    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            os.remove(p)


@pytest.fixture
def stores(tmp_db):
    dim = 8
    semantic = SemanticStore(tmp_db, SemanticStoreConfig(dim=dim))
    graph = GraphManager(tmp_db, GraphConfig())
    return tmp_db, semantic, graph, dim


def _rand_unit(dim: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


class TestFindNearestPrototype:
    """Bug 1: _find_nearest_prototype used k=1 (invalid kwarg), should be top_k=1."""

    def test_returns_valid_id_when_prototypes_exist(self, stores):
        db, semantic, graph, dim = stores
        # Add one prototype
        centroid = _rand_unit(dim, seed=1)
        pid = semantic.upsert_prototype(
            prototype_id=None, centroid=centroid, support_count=1, variance=0.0
        )
        semantic.reset_faiss_from_db()

        cfg = TransitionModelConfig(dim=dim)
        tm = TransitionModel(cfg, graph=graph, semantic=semantic)
        tm.trained_steps = 1  # bypass trained_steps guard

        # Query close to the centroid
        result = tm._find_nearest_prototype(centroid.reshape(1, -1))
        assert result == pid, f"expected prototype id {pid}, got {result}"

    def test_returns_none_when_no_prototypes(self, stores):
        db, semantic, graph, dim = stores
        # Empty semantic store
        cfg = TransitionModelConfig(dim=dim)
        tm = TransitionModel(cfg, graph=graph, semantic=semantic)
        tm.trained_steps = 1

        result = tm._find_nearest_prototype(_rand_unit(dim).reshape(1, -1))
        assert result is None


class TestGetSuccessorPrototypes:
    """Bug 2: SQL used dst/src column names; correct names are dst_prototype_id/src_prototype_id."""

    def test_returns_successors_with_correct_column_names(self, stores):
        db, semantic, graph, dim = stores
        # Create two prototypes
        c1 = _rand_unit(dim, seed=10)
        c2 = _rand_unit(dim, seed=20)
        p1 = semantic.upsert_prototype(
            prototype_id=None, centroid=c1, support_count=2, variance=0.0
        )
        p2 = semantic.upsert_prototype(
            prototype_id=None, centroid=c2, support_count=2, variance=0.0
        )
        semantic.reset_faiss_from_db()

        # Manually insert an edge with w_transition > 0 using the CORRECT column names
        import time

        conn = db.connect()
        conn.execute(
            "INSERT INTO prototype_edges "
            "(src_prototype_id, dst_prototype_id, w_similarity, w_transition, w_coactivation, weight, last_updated_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p1, p2, 0.5, 0.8, 0.3, 0.6, int(time.time())),
        )
        conn.commit()

        cfg = TransitionModelConfig(dim=dim)
        tm = TransitionModel(cfg, graph=graph, semantic=semantic)
        tm.trained_steps = 1

        successors = tm._get_successor_prototypes(p1)
        assert len(successors) == 1
        assert successors[0][0] == p2
        assert abs(successors[0][1] - 0.8) < 1e-6

    def test_returns_empty_when_no_edges(self, stores):
        db, semantic, graph, dim = stores
        c1 = _rand_unit(dim, seed=10)
        p1 = semantic.upsert_prototype(
            prototype_id=None, centroid=c1, support_count=1, variance=0.0
        )
        semantic.reset_faiss_from_db()

        cfg = TransitionModelConfig(dim=dim)
        tm = TransitionModel(cfg, graph=graph, semantic=semantic)
        tm.trained_steps = 1

        result = tm._get_successor_prototypes(p1)
        assert result == []

    def test_filters_zero_weight_edges(self, stores):
        """Edges with w_transition == 0 should not be returned."""
        db, semantic, graph, dim = stores
        c1 = _rand_unit(dim, seed=10)
        c2 = _rand_unit(dim, seed=20)
        p1 = semantic.upsert_prototype(
            prototype_id=None, centroid=c1, support_count=1, variance=0.0
        )
        p2 = semantic.upsert_prototype(
            prototype_id=None, centroid=c2, support_count=1, variance=0.0
        )
        semantic.reset_faiss_from_db()

        import time

        conn = db.connect()
        conn.execute(
            "INSERT INTO prototype_edges "
            "(src_prototype_id, dst_prototype_id, w_similarity, w_transition, w_coactivation, weight, last_updated_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p1, p2, 0.5, 0.0, 0.3, 0.4, int(time.time())),  # w_transition == 0
        )
        conn.commit()

        cfg = TransitionModelConfig(dim=dim)
        tm = TransitionModel(cfg, graph=graph, semantic=semantic)
        tm.trained_steps = 1

        result = tm._get_successor_prototypes(p1)
        assert result == []


class TestPredict:
    """End-to-end predict() test: confirms non-zero output when stores are populated."""

    def test_predict_returns_zeros_before_training(self, stores):
        db, semantic, graph, dim = stores
        cfg = TransitionModelConfig(dim=dim)
        tm = TransitionModel(cfg, graph=graph, semantic=semantic)
        # trained_steps == 0 by default
        e = _rand_unit(dim).reshape(1, -1)
        result = tm.predict(e)
        assert result.shape == (1, dim)
        assert np.allclose(result, 0.0)

    def test_predict_returns_zeros_without_stores(self):
        cfg = TransitionModelConfig(dim=8)
        tm = TransitionModel(cfg, graph=None, semantic=None)
        tm.trained_steps = 5
        e = _rand_unit(8).reshape(1, -1)
        result = tm.predict(e)
        assert np.allclose(result, 0.0)

    def test_predict_nonzero_after_edge_insertion(self, stores):
        """Full end-to-end: with populated prototype + edge, predict() returns non-zero."""
        db, semantic, graph, dim = stores
        c1 = _rand_unit(dim, seed=1)
        c2 = _rand_unit(dim, seed=2)
        p1 = semantic.upsert_prototype(
            prototype_id=None, centroid=c1, support_count=3, variance=0.0
        )
        p2 = semantic.upsert_prototype(
            prototype_id=None, centroid=c2, support_count=3, variance=0.0
        )
        semantic.reset_faiss_from_db()

        import time

        conn = db.connect()
        conn.execute(
            "INSERT INTO prototype_edges "
            "(src_prototype_id, dst_prototype_id, w_similarity, w_transition, w_coactivation, weight, last_updated_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p1, p2, 0.4, 1.0, 0.2, 0.7, int(time.time())),
        )
        conn.commit()

        cfg = TransitionModelConfig(dim=dim)
        tm = TransitionModel(cfg, graph=graph, semantic=semantic)
        tm.trained_steps = 1  # simulate one consolidation pass

        # Query near prototype p1; expected prediction ≈ centroid of p2
        result = tm.predict(c1.reshape(1, -1))
        assert result.shape == (1, dim)
        assert not np.allclose(result, 0.0), "predict() should return non-zero when edges exist"
        # Result should be close to c2 (only successor)
        result_norm = result.reshape(-1) / (np.linalg.norm(result) + 1e-12)
        sim = float(result_norm.dot(c2))
        assert sim > 0.9, f"prediction should align with successor centroid c2, got cos={sim:.3f}"


class TestEngineAutoInstantiatesTransitionModel:
    """Bug 3: engine.py used to leave transition_model=None by default."""

    def test_engine_has_transition_model_without_explicit_config(self):
        """SlowaveEngine must always create a TransitionModel, even with default config."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            cfg = SlowaveConfig(db_path=db_path, disable_encoder=True)
            eng = SlowaveEngine(cfg)
            assert (
                eng.transition_model is not None
            ), "transition_model should never be None — Stage 3 is always-on"
            assert (
                eng.retrieval.transition_model is not None
            ), "RetrievalPipeline must receive the transition_model"
            eng.close()
        finally:
            for ext in ("", "-wal", "-shm"):
                p = db_path + ext
                if os.path.exists(p):
                    os.remove(p)

    def test_engine_transition_model_has_stores_attached(self):
        """The transition model's graph and semantic stores must be live references."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            cfg = SlowaveConfig(db_path=db_path, disable_encoder=True)
            eng = SlowaveEngine(cfg)
            tm = eng.transition_model
            assert tm._graph is eng.graph
            assert tm._semantic is eng.semantic
            eng.close()
        finally:
            for ext in ("", "-wal", "-shm"):
                p = db_path + ext
                if os.path.exists(p):
                    os.remove(p)
