"""Micro-benchmark: graph edge quality — deterministic tests for Phase 7.

Tests verify that the GraphManager's edge construction, accumulation,
normalization, pruning, and retrieval behave correctly in isolation.
All tests use in-memory SQLite — deterministic, <5s, no external data.
"""

from __future__ import annotations

import numpy as np
import pytest

from slowave.latent.graph_manager import GraphConfig, GraphManager
from slowave.storage.sqlite_db import SQLiteConfig, SQLiteDB

DIM = 32


def _make_db(tmp_path):
    db_path = tmp_path / "test.db"
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


def _make_graph(db, **kwargs) -> GraphManager:
    # Start with homeostatic disabled by default; kwargs override
    defaults = dict(accumulate_decay=0.5, homeostatic_enabled=False)
    defaults.update(kwargs)
    cfg = GraphConfig(**defaults)
    return GraphManager(db, cfg)


# ---------------------------------------------------------------------------
# Test 1: Edge rank reflects ground-truth relatedness (Spearman rho)
# ---------------------------------------------------------------------------


def test_edges_rank_by_known_relatedness(tmp_path):
    """Edges with higher ground-truth relatedness get higher fused weight."""
    db = _make_db(tmp_path)
    graph = _make_graph(db)

    graph._upsert_edge(1, 2, w_similarity=0.9, w_transition=0.0, w_coactivation=0.0)
    graph._upsert_edge(1, 3, w_similarity=0.5, w_transition=0.0, w_coactivation=0.0)
    graph._upsert_edge(1, 4, w_similarity=0.1, w_transition=0.0, w_coactivation=0.0)

    neighbors = graph.neighbors(1, top_k=3)
    ids_in_order = [n[0] for n in neighbors]
    assert ids_in_order == [2, 3, 4]
    weights = [n[1] for n in neighbors]
    assert weights[0] > weights[1] > weights[2]


# ---------------------------------------------------------------------------
# Test 2: Directional edges
# ---------------------------------------------------------------------------


def test_directional_edges_with_lambda_similarity_zero(tmp_path):
    """With lambda_similarity=0, edges are determined by transition asymmetry."""
    db = _make_db(tmp_path)
    graph = _make_graph(db, lambda_similarity=0.0, lambda_transition=1.0, lambda_coactivation=0.0)

    graph.apply_transition_counts({(1, 2): 0.9, (2, 1): 0.1})

    n1 = graph.neighbors(1, top_k=5)
    n2 = graph.neighbors(2, top_k=5)
    w12 = next((w for dst, w in n1 if dst == 2), 0.0)
    w21 = next((w for dst, w in n2 if dst == 1), 0.0)

    assert w12 > w21 * 3, f"Expected directional: w12={w12:.3f}, w21={w21:.3f}"

    denom = w12 + w21
    symmetry = 1.0 - abs(w12 - w21) / denom if denom > 0 else 1.0
    assert symmetry < 0.5, f"Expected low symmetry, got {symmetry:.3f}"


# ---------------------------------------------------------------------------
# Test 3: Homeostatic normalization respects target L1 sum
# ---------------------------------------------------------------------------


def test_homeostatic_normalization_sums_to_target(tmp_path):
    """After normalization with target=0.5, sum <= target + epsilon."""
    db = _make_db(tmp_path)
    graph = _make_graph(
        db, homeostatic_enabled=True, homeostatic_target=0.5, prune_ratio=0.01, prune_below=0.0
    )

    graph.apply_transition_counts({(1, 2): 1.0, (1, 3): 0.5, (1, 4): 0.1})

    conn = graph.db.connect()
    rows = conn.execute("SELECT weight FROM prototype_edges WHERE src_prototype_id=1").fetchall()
    total = sum(float(r["weight"]) for r in rows)
    assert total <= 0.51, f"L1 sum {total:.4f} exceeds target 0.5"


def test_homeostatic_prunes_weak_edges(tmp_path):
    """Edges below prune_ratio * max_weight are deleted."""
    db = _make_db(tmp_path)
    graph = _make_graph(
        db, homeostatic_enabled=True, homeostatic_target=0.5, prune_ratio=0.2, prune_below=0.0
    )

    graph.apply_transition_counts({(1, 2): 1.0, (1, 3): 0.1})

    conn = graph.db.connect()
    rows = conn.execute(
        "SELECT dst_prototype_id FROM prototype_edges WHERE src_prototype_id=1"
    ).fetchall()
    dsts = {int(r["dst_prototype_id"]) for r in rows}
    assert 2 in dsts, "Strong edge should survive"
    assert 3 not in dsts, "Weak edge (<20% of max) should be pruned"


# ---------------------------------------------------------------------------
# Test 4: Pruning removes edges below absolute threshold
# ---------------------------------------------------------------------------


def test_prune_edges_removes_below_threshold(tmp_path):
    """Only edges with weight >= prune_below survive absolute pruning."""
    db = _make_db(tmp_path)
    graph = _make_graph(db, lambda_similarity=1.0, homeostatic_enabled=False, prune_below=0.05)

    graph._upsert_edge(1, 2, w_similarity=0.10, w_transition=0.0, w_coactivation=0.0)
    graph._upsert_edge(1, 3, w_similarity=0.04, w_transition=0.0, w_coactivation=0.0)
    graph._upsert_edge(1, 4, w_similarity=0.02, w_transition=0.0, w_coactivation=0.0)

    graph.prune_edges()

    conn = graph.db.connect()
    rows = conn.execute(
        "SELECT dst_prototype_id FROM prototype_edges WHERE src_prototype_id=1"
    ).fetchall()
    surviving = {int(r["dst_prototype_id"]) for r in rows}

    assert 2 in surviving, "Edge with weight 0.10 should survive"
    assert 3 not in surviving, "Edge with weight 0.04 should be pruned"
    assert 4 not in surviving, "Edge with weight 0.02 should be pruned"


# ---------------------------------------------------------------------------
# Test 5: EMA accumulation convergence
# ---------------------------------------------------------------------------


def test_ema_accumulation_converges_to_count(tmp_path):
    """After repeated passes, EMA-accumulated weight approaches the input count."""
    db = _make_db(tmp_path)
    graph = _make_graph(db, accumulate_decay=0.3, homeostatic_enabled=False)
    object.__setattr__(graph.cfg, "prune_below", 0.0)

    target = 0.8
    for _ in range(10):
        graph.apply_transition_counts({(1, 2): target})

    _ws, wt, _wc = graph._get_components(1, 2)
    # w_n = target * (1 - decay^n); after 10 passes: 0.8 * (1 - 0.3^10) ~ 0.8
    assert wt == pytest.approx(target, abs=0.01), f"EMA should converge near {target}, got {wt:.4f}"


# ---------------------------------------------------------------------------
# Test 6: Edge weight decomposition
# ---------------------------------------------------------------------------


def test_weight_decomposition_fractions(tmp_path):
    """Verify fused weight = lambda1*sim + lambda2*trans + lambda3*coact."""
    db = _make_db(tmp_path)
    graph = _make_graph(
        db,
        lambda_similarity=1.0,
        lambda_transition=0.5,
        lambda_coactivation=0.3,
        homeostatic_enabled=False,
    )

    graph._upsert_edge(1, 2, w_similarity=0.8, w_transition=0.4, w_coactivation=0.2)

    ws, wt, wc = graph._get_components(1, 2)
    expected_w = 1.0 * 0.8 + 0.5 * 0.4 + 0.3 * 0.2  # = 0.8 + 0.2 + 0.06 = 1.06

    conn = graph.db.connect()
    row = conn.execute(
        "SELECT weight FROM prototype_edges WHERE src_prototype_id=1 AND dst_prototype_id=2"
    ).fetchone()
    actual_w = float(row["weight"])
    assert actual_w == pytest.approx(expected_w, abs=0.001)

    sim_frac = 1.0 * ws / actual_w  # 0.8 / 1.06 ~ 0.7547
    trans_frac = 0.5 * wt / actual_w  # 0.2 / 1.06 ~ 0.1887
    coact_frac = 0.3 * wc / actual_w  # 0.06 / 1.06 ~ 0.0566

    assert sim_frac == pytest.approx(0.7547, abs=0.01)
    assert trans_frac == pytest.approx(0.1887, abs=0.01)
    assert coact_frac == pytest.approx(0.0566, abs=0.01)


# ---------------------------------------------------------------------------
# Test 7: Coactivation top-k filter
# ---------------------------------------------------------------------------


def test_coactivation_top_k_filter(tmp_path):
    """Only top top_k_coactivation pairs per source survive."""
    db = _make_db(tmp_path)
    graph = _make_graph(db, top_k_coactivation=4, homeostatic_enabled=False, prune_below=0.0)

    counts = {
        (1, 2): 10.0,
        (1, 3): 9.0,
        (1, 4): 8.0,
        (1, 5): 7.0,
        (1, 6): 6.0,
        (1, 7): 5.0,
        (1, 8): 4.0,
        (1, 9): 3.0,
    }
    graph.apply_coactivation_counts(counts)

    conn = graph.db.connect()
    rows = conn.execute(
        "SELECT dst_prototype_id FROM prototype_edges WHERE src_prototype_id=1"
    ).fetchall()
    surviving = {int(r["dst_prototype_id"]) for r in rows}
    assert surviving == {2, 3, 4, 5}, f"Expected {{2,3,4,5}}, got {surviving}"


# ---------------------------------------------------------------------------
# Test 8: Similarity edges overwrite, don't accumulate
# ---------------------------------------------------------------------------


def test_similarity_edges_overwrite(tmp_path):
    """Two calls to set_similarity_edges overwrite, not EMA-accumulate."""
    db = _make_db(tmp_path)
    graph = _make_graph(db, homeostatic_enabled=False, prune_below=0.0)

    centroids_v1 = np.array([[1, 0, 0], [0.9, 0.1, 0], [0, 0, 1]], dtype=np.float32)
    graph.set_similarity_edges(prototype_ids=[1, 2, 3], centroids=centroids_v1)

    ws1, _, _ = graph._get_components(1, 2)
    assert ws1 > 0.5, f"Expected high similarity, got {ws1:.3f}"

    # Second call with same centroids — should be same, not doubled
    graph.set_similarity_edges(prototype_ids=[1, 2, 3], centroids=centroids_v1)
    ws2, _, _ = graph._get_components(1, 2)
    assert ws2 == pytest.approx(
        ws1, abs=0.001
    ), f"Similarity should not accumulate: {ws1:.4f} -> {ws2:.4f}"

    # Third call with different centroids — should reflect new similarity
    centroids_v2 = np.array([[1, 0, 0], [0.2, 0.8, 0], [0, 0, 1]], dtype=np.float32)
    graph.set_similarity_edges(prototype_ids=[1, 2, 3], centroids=centroids_v2)
    ws3, _, _ = graph._get_components(1, 2)
    assert ws3 < 0.5, f"Similarity should reflect v2 centroids, got {ws3:.3f}"


# ---------------------------------------------------------------------------
# Bonus: diagnose() returns valid structure
# ---------------------------------------------------------------------------


def test_diagnose_on_empty_graph(tmp_path):
    """diagnose() on empty graph returns valid empty structure."""
    db = _make_db(tmp_path)
    graph = _make_graph(db)
    diag = graph.diagnose()
    assert diag["edge_count"] == 0
    assert diag["similarity_dominance_pct"] is None


def test_diagnose_with_edges(tmp_path):
    """diagnose() computes component fractions correctly."""
    db = _make_db(tmp_path)
    graph = _make_graph(
        db,
        lambda_similarity=1.0,
        lambda_transition=0.5,
        lambda_coactivation=0.3,
        homeostatic_enabled=False,
        prune_below=0.0,
    )

    # Similarity-dominant (1<->2) and transition-dominant (3->4)
    graph._upsert_edge(1, 2, w_similarity=0.9, w_transition=0.0, w_coactivation=0.0)
    graph._upsert_edge(2, 1, w_similarity=0.9, w_transition=0.0, w_coactivation=0.0)
    graph._upsert_edge(3, 4, w_similarity=0.0, w_transition=0.8, w_coactivation=0.0)

    diag = graph.diagnose()
    assert diag["edge_count"] == 3
    assert diag["component_fractions"]["similarity"]["mean"] > 0.5
    assert diag["similarity_dominance_pct"] > 50
    assert diag["symmetry"]["median"] is not None
    assert diag["symmetry"]["median"] > 0.9
    assert diag["degree_distribution"]["n_sources"] == 3
