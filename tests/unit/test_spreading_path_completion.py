"""Micro-benchmark: graph spreading retrieves C via the 2-hop path A→B→C.

Design
------
Three prototypes on orthogonal axes (dim=8):

    P_A = axis 0  (A-domain)
    P_B = axis 1  (B-domain)
    P_C = axis 2  (C-domain, the target)

Episodes:
    eps_a×10  near axis 0  →  cosine ≈ 1 with query  →  fill cosine top-10
    eps_b ×1  axis 1       →  cosine = 0 with query  →  not in cosine top-10
    eps_c ×1  axis 2       →  cosine = 0 with query  →  not in cosine top-10 (TARGET)

Graph edges (via apply_transition_counts):
    P_A → P_B  (weight ≈ 0.5 after homeostatic normalization)
    P_B → P_C  (weight ≈ 0.5)

Query: axis 0 → cosine seeds only P_A.

Spreading mechanism (spread_steps=2):
    Step 0: seed_activation = {P_A: 1.0}  (only P_A has non-zero cosine with query)
    Step 1: P_A propagates to P_B  → activation = {P_A: 0.6, P_B: 0.4}
    Step 2: P_B propagates to P_C  → activation = {P_A: 0.36, P_B: 0.48, P_C: 0.16}

    q_spread = normalize(0.36·axis0 + 0.48·axis1 + 0.16·axis2) ≈ [0.58, 0.77, 0.26, ...]
    FAISS on q_spread: eps_b ranks highest (~0.77), then eps_a* (~0.58), then eps_c (~0.26).

    eps_c has the weakest q_spread affinity among non-cosine-direct episodes.
    spread_episodic_top_k=15 (> 12 total episodes) guarantees eps_c is within budget.

With spread_steps=1: P_C is never activated, so q_spread has no axis-2 component,
    and eps_c cannot appear in the FAISS results.

With use_spreading=False: no spreading, no q_spread, no spread-projection FAISS call.

This is a plumbing test — it verifies the full chain:
    graph path wired → spreading activates P_C → projection includes axis-2 component
    → FAISS finds eps_c via that component.
"""

from __future__ import annotations

import numpy as np
import pytest

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.latent.retrieval import RetrievalConfig, RetrievalPipeline

DIM = 8


def _axis(i: int) -> np.ndarray:
    v = np.zeros(DIM, dtype=np.float32)
    v[i] = 1.0
    return v


def _make_engine(tmp_path) -> SlowaveEngine:
    return SlowaveEngine(
        SlowaveConfig(db_path=str(tmp_path / "test.db"), dim=DIM, disable_encoder=True)
    )


@pytest.fixture()
def store(tmp_path):
    """Populated latent stores with a 3-prototype graph and controlled embeddings."""
    eng = _make_engine(tmp_path)

    # Three orthogonal prototypes
    pid_a = eng.semantic.upsert_prototype(
        prototype_id=None, centroid=_axis(0), support_count=10, variance=0.1
    )
    pid_b = eng.semantic.upsert_prototype(
        prototype_id=None, centroid=_axis(1), support_count=5, variance=0.1
    )
    pid_c = eng.semantic.upsert_prototype(
        prototype_id=None, centroid=_axis(2), support_count=5, variance=0.1
    )

    # 10 A-domain episodes fill cosine top-10 (cosine ≈ 1 with query = axis 0)
    for i in range(10):
        v = _axis(0).copy()
        v[4] = 0.01 * (i + 1)  # tiny perturbation so episodes are distinct
        v = (v / np.linalg.norm(v)).astype(np.float32)
        eid = eng.episodic.add(event_id=f"a_{i}", ts=1000, embedding=v, salience=0.5, metadata={})
        eng.semantic.map_episode_to_prototype(eid, pid_a)

    # B-domain episode: cosine = 0 with query → never in cosine top-10
    eps_b = eng.episodic.add(event_id="b_0", ts=1000, embedding=_axis(1), salience=0.5, metadata={})
    eng.semantic.map_episode_to_prototype(eps_b, pid_b)

    # C-domain episode: cosine = 0 with query → never in cosine top-10 (TARGET)
    eps_c = eng.episodic.add(event_id="c_0", ts=1000, embedding=_axis(2), salience=0.5, metadata={})
    eng.semantic.map_episode_to_prototype(eps_c, pid_c)

    # Graph: P_A → P_B, P_B → P_C (via transition counts)
    eng.graph.apply_transition_counts({(pid_a, pid_b): 1.0, (pid_b, pid_c): 1.0})

    yield eng, eps_c
    eng.close()


def _pipeline(eng: SlowaveEngine, **cfg_overrides) -> RetrievalPipeline:
    """Build a RetrievalPipeline with transition/multiscale/temporal disabled.

    spread_episodic_top_k=15 exceeds the 12 total episodes in the fixture so
    eps_c (q_spread cosine ≈ 0.26, the lowest of the non-cosine-direct episodes)
    is always within the FAISS budget when spreading reaches P_C.
    """
    cfg = RetrievalConfig(
        use_transition=False,
        use_multi_scale=False,
        use_temporal=False,
        spread_episodic_top_k=15,
        **cfg_overrides,
    )
    return RetrievalPipeline(episodic=eng.episodic, semantic=eng.semantic, graph=eng.graph, cfg=cfg)


# ---------------------------------------------------------------------------


def test_2hop_finds_target(store):
    """2-hop path A→B→C surfaces eps_c via spread-projection FAISS."""
    eng, eps_c = store
    result = _pipeline(eng, use_spreading=True, spread_steps=2).retrieve(_axis(0), diagnose=True)

    graph_ids = {d.episode_id for d in result.episode_diagnostics if d.source == "graph_harvest"}
    qd = result.query_diagnostics
    assert eps_c in graph_ids, (
        f"eps_c (id={eps_c}) not found in graph harvest. "
        f"graph_ids={graph_ids}, "
        f"activated_after_spread={qd.activated_after_spread_n}, "
        f"activation_depth={qd.activation_depth}"
    )


def test_1hop_cannot_reach_target(store):
    """spread_steps=1 activates P_B but cannot reach P_C — eps_c absent."""
    eng, eps_c = store
    result = _pipeline(eng, use_spreading=True, spread_steps=1).retrieve(_axis(0), diagnose=True)

    graph_ids = {d.episode_id for d in result.episode_diagnostics if d.source == "graph_harvest"}
    qd = result.query_diagnostics
    assert eps_c not in graph_ids, (
        f"eps_c should NOT appear with spread_steps=1 (path A→B→C requires 2 hops). "
        f"activation_depth={qd.activation_depth}"
    )


def test_no_spreading_no_graph_harvest(store):
    """Spreading disabled → cosine-only, zero graph harvest, eps_c absent."""
    eng, eps_c = store
    result = _pipeline(eng, use_spreading=False).retrieve(_axis(0), diagnose=True)

    all_ids = {d.episode_id for d in result.episode_diagnostics}
    qd = result.query_diagnostics
    assert eps_c not in all_ids
    assert qd.activated_after_spread_n == 0
    assert qd.graph_harvest_n == 0


def test_activation_depth_tracks_front_growth(store):
    """Activation front: step 1 → {P_A, P_B}, step 2 → {P_A, P_B, P_C}."""
    eng, _ = store
    result = _pipeline(eng, use_spreading=True, spread_steps=2).retrieve(_axis(0), diagnose=True)

    qd = result.query_diagnostics
    assert len(qd.activation_depth) == 2, f"Expected 2 steps, got {qd.activation_depth}"
    assert (
        qd.activation_depth[0] == 2
    ), f"After step 1: expected 2 active protos, got {qd.activation_depth[0]}"
    assert (
        qd.activation_depth[1] == 3
    ), f"After step 2: expected 3 active protos, got {qd.activation_depth[1]}"
