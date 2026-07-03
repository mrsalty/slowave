"""Tests for graph weight accumulation via EMA across replay passes.

Before this change, apply_transition_counts and apply_coactivation_counts
overwrote previous weights on each replay pass. Now they accumulate via
an exponential moving average: new = old * decay + current * (1-decay).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from slowave.latent.graph_manager import GraphConfig, GraphManager
from slowave.storage.sqlite_db import SQLiteConfig, SQLiteDB


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = str(REPO_ROOT / "slowave" / "storage" / "schema.sql")


@pytest.fixture()
def graph():
    """Fresh in-memory graph with accumulate_decay=0.5 (balanced)."""
    db_path = str(Path(tempfile.mkdtemp()) / "test.db")
    db = SQLiteDB(SQLiteConfig(path=db_path))
    db.init_schema(SCHEMA_PATH)
    conn = db.connect()
    conn.execute("PRAGMA foreign_keys = OFF")
    cfg = GraphConfig(accumulate_decay=0.5, prune_below=0.0)
    gm = GraphManager(db=db, cfg=cfg)
    yield gm
    db.close()


# ---------------------------------------------------------------------------
# Transition accumulation
# ---------------------------------------------------------------------------

def test_transition_accumulation_across_passes(graph):
    """Two replay passes: second pass evidence is blended with first."""
    # Pass 1: (1->2) with count 0.8
    graph.apply_transition_counts({(1, 2): 0.8})
    _ws1, wt1, _wc1 = graph._get_components(1, 2)
    assert wt1 == pytest.approx(0.4, abs=0.01)  # 0 * 0.5 + 0.8 * 0.5

    # Pass 2: same edge appears again with count 1.0
    graph.apply_transition_counts({(1, 2): 1.0, (2, 3): 0.6})
    _ws2, wt2, _wc2 = graph._get_components(1, 2)
    assert wt2 == pytest.approx(0.7, abs=0.01)  # 0.4 * 0.5 + 1.0 * 0.5

    # (2->3) is new: old=0, current=0.6 → 0*0.5 + 0.6*0.5 = 0.3
    _ws3, wt3, _wc3 = graph._get_components(2, 3)
    assert wt3 == pytest.approx(0.3, abs=0.01)


def test_transition_accumulation_converges_to_long_run_average(graph):
    """With accumulate_decay=0.9, many passes converge to the recurring rate."""
    object.__setattr__(graph.cfg, "accumulate_decay", 0.9)
    # Simulate an edge that consistently appears at rate 0.5 every pass
    for _ in range(20):
        graph.apply_transition_counts({(1, 2): 0.5})
    _ws, wt, _wc = graph._get_components(1, 2)
    # After 20 passes: steady state ~0.5 (val = val*0.9 + 0.5*0.1).
    # Initial 0, 20 iterations: 0.5*(1-0.9^20) ≈ 0.439
    assert 0.35 < wt < 0.55


# ---------------------------------------------------------------------------
# Coactivation accumulation
# ---------------------------------------------------------------------------

def test_coactivation_accumulation_across_passes(graph):
    """Two replay passes: coactivation evidence builds cumulatively."""
    # Pass 1: prototypes 1 and 2 co-occur with count 3
    graph.apply_coactivation_counts({(1, 2): 3.0})
    _ws1, _wt1, wc1 = graph._get_components(1, 2)
    assert wc1 == pytest.approx(1.5, abs=0.01)  # 0 * 0.5 + 3.0 * 0.5

    # Pass 2: same pair co-occurs again with count 5
    graph.apply_coactivation_counts({(1, 2): 5.0, (1, 3): 2.0})
    _ws2, _wt2, wc2 = graph._get_components(1, 2)
    assert wc2 == pytest.approx(3.25, abs=0.01)  # 1.5 * 0.5 + 5.0 * 0.5

    # (1->3) is new: old=0, current=2.0 → 0*0.5 + 2.0*0.5 = 1.0
    _ws3, _wt3, wc3 = graph._get_components(1, 3)
    assert wc3 == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# Similarity edges are NOT accumulated
# ---------------------------------------------------------------------------

def test_similarity_edges_still_overwrite(graph):
    """Similarity edges are recomputed fresh each pass — not accumulated."""
    centroids = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)

    # Pass 1: similarity edge (1->2) with cosine ~0
    graph.set_similarity_edges(prototype_ids=[1, 2, 3], centroids=centroids)
    ws1_old, _, _ = graph._get_components(1, 2)

    # Pass 2: same call — overwrites, not accumulates
    graph.set_similarity_edges(prototype_ids=[1, 2, 3], centroids=centroids)
    ws1_new, _, _ = graph._get_components(1, 2)

    # Similarity should be the same (overwritten, not doubled)
    assert ws1_new == pytest.approx(ws1_old, abs=0.001)
    # And it should equal the raw cosine (0.0 for orthogonal)
    assert ws1_new <= 0.01


# ---------------------------------------------------------------------------
# Zero-decay edge case (accumulate_decay=0, full replacement)
# ---------------------------------------------------------------------------

def test_accumulate_decay_zero_overwrites(graph):
    """With accumulate_decay=0, behavior matches pre-fix (full overwrite)."""
    # Frozen dataclass — use object.__setattr__ to override
    object.__setattr__(graph.cfg, "accumulate_decay", 0.0)

    graph.apply_transition_counts({(1, 2): 0.8})
    _ws1, wt1, _wc1 = graph._get_components(1, 2)
    assert wt1 == pytest.approx(0.8, abs=0.01)  # 0 * 0 + 0.8 * 1.0 = 0.8

    graph.apply_transition_counts({(1, 2): 0.3})
    _ws2, wt2, _wc2 = graph._get_components(1, 2)
    assert wt2 == pytest.approx(0.3, abs=0.01)  # 0.8 * 0 + 0.3 * 1.0 = 0.3


# ---------------------------------------------------------------------------
# Realistic replay scenario: multiple edges across multiple passes
# ---------------------------------------------------------------------------

def test_multiple_edges_accumulate_independently(graph):
    """Each edge pair accumulates independently across passes."""
    object.__setattr__(graph.cfg, "accumulate_decay", 0.7)

    # Pass 1: two edges
    graph.apply_transition_counts({(1, 2): 0.9, (1, 3): 0.1})
    # Pass 2: edge (1,2) repeats, (1,3) doesn't, new edge (2,4)
    graph.apply_transition_counts({(1, 2): 0.8, (2, 4): 0.6})

    # (1,2): 0.9*0.3=0.27; 0.27*0.7 + 0.8*0.3 = 0.189 + 0.24 = 0.429
    _ws, wt12, _wc = graph._get_components(1, 2)
    assert wt12 == pytest.approx(0.429, abs=0.01)

    # (1,3): 0.1*0.3=0.03; 0.03*0.7 + 0*0.3 = 0.021
    _ws, wt13, _wc = graph._get_components(1, 3)
    assert wt13 == pytest.approx(0.021, abs=0.01)

    # (2,4): new: 0*0.7 + 0.6*0.3 = 0.18
    _ws, wt24, _wc = graph._get_components(2, 4)
    assert wt24 == pytest.approx(0.18, abs=0.01)