"""Tests for graph weight accumulation + homeostatic normalization.

Before B-3: apply_transition_counts and apply_coactivation_counts
overwrote previous weights each replay pass.
After B-3: EMA accumulation (decay=0.5), followed by per-source L1
homeostatic normalization to prevent graph densification.
"""

from __future__ import annotations

import pytest

from slowave.latent.graph_manager import GraphConfig, GraphManager
from slowave.storage.sqlite_db import SQLiteConfig, SQLiteDB


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_graph.db"
    sdb = SQLiteDB(SQLiteConfig(path=str(db_path)))
    conn = sdb.connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prototype_edges (
            src_prototype_id INTEGER NOT NULL,
            dst_prototype_id INTEGER NOT NULL,
            w_similarity REAL NOT NULL,
            w_transition REAL NOT NULL,
            w_coactivation REAL NOT NULL,
            weight REAL NOT NULL,
            last_updated_ts INTEGER,
            PRIMARY KEY (src_prototype_id, dst_prototype_id)
        )
    """)
    conn.commit()
    return sdb


@pytest.fixture
def graph(db):
    return GraphManager(db, GraphConfig(accumulate_decay=0.5, homeostatic_enabled=True))


# ---------------------------------------------------------------------------
# Homeostatic normalization
# ---------------------------------------------------------------------------


def test_homeostatic_normalization_sums_to_target(graph):
    """After normalization, each source's edges sum to ≤ homeostatic_target."""
    graph.apply_transition_counts({(1, 2): 0.8, (1, 3): 0.6, (1, 4): 0.2})
    conn = graph.db.connect()
    rows = conn.execute(
        "SELECT weight FROM prototype_edges WHERE src_prototype_id=1 ORDER BY weight DESC"
    ).fetchall()
    total = sum(float(r["weight"]) for r in rows)
    assert total <= 1.01  # allow tiny float error


def test_homeostatic_prunes_weak_edges(graph):
    """Edges below prune_ratio * max_weight are deleted."""
    graph.apply_transition_counts({(1, 2): 1.0, (1, 3): 0.01})
    conn = graph.db.connect()
    rows = conn.execute(
        "SELECT dst_prototype_id FROM prototype_edges WHERE src_prototype_id=1"
    ).fetchall()
    dsts = {int(r["dst_prototype_id"]) for r in rows}
    assert 2 in dsts
    assert 3 not in dsts  # pruned


def test_homeostatic_no_edges_is_noop(graph):
    """Normalization on an empty graph doesn't crash."""
    graph._homeostatic_normalize()
    assert graph.edge_count() == 0


# ---------------------------------------------------------------------------
# EMA accumulation
# ---------------------------------------------------------------------------


def test_transition_accumulation_across_passes(graph):
    """Two replay passes: transition evidence builds via EMA."""
    # Disable homeostatic to test raw EMA
    object.__setattr__(graph.cfg, "homeostatic_enabled", False)

    graph.apply_transition_counts({(1, 2): 0.8})
    _ws1, wt1, _wc1 = graph._get_components(1, 2)
    # Pass 1: old=0, current=0.8 -> 0*0.5 + 0.8*0.5 = 0.4
    assert wt1 == pytest.approx(0.4, abs=0.01)

    graph.apply_transition_counts({(1, 2): 0.8})
    _ws2, wt2, _wc2 = graph._get_components(1, 2)
    # Pass 2: 0.4*0.5 + 0.8*0.5 = 0.6
    assert wt2 == pytest.approx(0.6, abs=0.01)


def test_coactivation_accumulation_across_passes(graph):
    """Two replay passes: coactivation evidence builds via EMA."""
    object.__setattr__(graph.cfg, "homeostatic_enabled", False)

    graph.apply_coactivation_counts({(1, 2): 3.0})
    _ws1, _wt1, wc1 = graph._get_components(1, 2)
    # Pass 1: 0*0.5 + 3.0*0.5 = 1.5
    assert wc1 == pytest.approx(1.5, abs=0.01)

    graph.apply_coactivation_counts({(1, 2): 5.0})
    _ws2, _wt2, wc2 = graph._get_components(1, 2)
    # Pass 2: 1.5*0.5 + 5.0*0.5 = 3.25
    assert wc2 == pytest.approx(3.25, abs=0.01)


# ---------------------------------------------------------------------------
# Similarity edges are NOT accumulated
# ---------------------------------------------------------------------------


def test_similarity_edges_still_overwrite(graph):
    """Similarity edges are recomputed fresh each pass."""
    import numpy as np

    centroids = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)
    graph.set_similarity_edges(prototype_ids=[1, 2, 3], centroids=centroids)
    ws1_old, _, _ = graph._get_components(1, 2)
    graph.set_similarity_edges(prototype_ids=[1, 2, 3], centroids=centroids)
    ws1_new, _, _ = graph._get_components(1, 2)
    assert ws1_new == pytest.approx(ws1_old, abs=0.001)
    assert ws1_new <= 0.01  # orthogonal


# ---------------------------------------------------------------------------
# accumulate_decay=0 (full replacement)
# ---------------------------------------------------------------------------


def test_accumulate_decay_zero_overwrites(graph):
    """With accumulate_decay=0, behavior matches pre-fix (full overwrite)."""
    object.__setattr__(graph.cfg, "accumulate_decay", 0.0)
    object.__setattr__(graph.cfg, "homeostatic_enabled", False)

    graph.apply_transition_counts({(1, 2): 0.8})
    _ws1, wt1, _wc1 = graph._get_components(1, 2)
    assert wt1 == pytest.approx(0.8, abs=0.01)

    graph.apply_transition_counts({(1, 2): 0.3})
    _ws2, wt2, _wc2 = graph._get_components(1, 2)
    assert wt2 == pytest.approx(0.3, abs=0.01)


# ---------------------------------------------------------------------------
# Multiple edges accumulate independently
# ---------------------------------------------------------------------------


def test_multiple_edges_accumulate_independently(graph):
    """Each edge pair accumulates independently across passes."""
    object.__setattr__(graph.cfg, "accumulate_decay", 0.5)
    object.__setattr__(graph.cfg, "homeostatic_enabled", False)

    # Use counts large enough that composite weight stays above prune_below=0.05
    # weight = 1.0*0 + 0.5*wt → wt must be > 0.1 after all passes
    graph.apply_transition_counts({(1, 2): 0.9, (1, 3): 0.4})
    graph.apply_transition_counts({(1, 2): 0.8, (2, 4): 0.6})

    # (1,2): 0*0.5+0.9*0.5=0.45; 0.45*0.5+0.8*0.5=0.225+0.4=0.625
    _ws, wt12, _wc = graph._get_components(1, 2)
    assert wt12 == pytest.approx(0.625, abs=0.01)

    # (1,3): 0*0.5+0.4*0.5=0.20 (not in pass 2 → no update)
    _ws, wt13, _wc = graph._get_components(1, 3)
    assert wt13 == pytest.approx(0.20, abs=0.01)
