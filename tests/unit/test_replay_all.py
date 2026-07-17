"""Tests for ReplayEngine.replay_all() and Consolidator.consolidate_all().

Point 1 of private/docs/iterations/20260716_event-store-replay.md: a
deterministic full-replay path that is a pure function of episodic_memories,
independent of replay_once()'s salience-weighted sampling and per-pass
prototype creation cap.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.latent.replay_engine import ReplayConfig


class _StubEncoder:
    def __init__(self, dim: int = 32):
        self._dim = dim

    def encode(self, text: str) -> np.ndarray:
        seed = int(abs(hash(text)) % (2**31))
        v = np.random.default_rng(seed).standard_normal(self._dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-12)


def _make_engine(tmp_path, name: str, dim: int = 32, replay: ReplayConfig | None = None):
    cfg = SlowaveConfig(db_path=str(tmp_path / name), dim=dim, disable_encoder=True)
    if replay is not None:
        cfg = dataclasses.replace(cfg, replay=replay)
    eng = SlowaveEngine(cfg)
    eng.encoder = _StubEncoder(dim)
    return eng


def _seed_episodes(eng: SlowaveEngine, n: int, *, dim: int = 32, cluster_spread: float = 0.02):
    """Add n orthogonal-ish clusters of episodes directly via the episodic store
    (bypassing raw_events/sessions — replay_all only reads episodic_memories)."""
    rng = np.random.default_rng(1234)
    base_dirs = rng.standard_normal((n, dim)).astype(np.float32)
    base_dirs /= np.linalg.norm(base_dirs, axis=1, keepdims=True)
    for i, base in enumerate(base_dirs):
        emb = base + rng.standard_normal(dim).astype(np.float32) * cluster_spread
        emb /= np.linalg.norm(emb)
        eng.episodic.add(
            event_id=f"seed_{i}",
            ts=1000 + i,
            embedding=emb,
            salience=0.5,
            metadata={"session_id": "seed", "kind": "micro"},
        )


def _all_prototypes(eng: SlowaveEngine):
    conn = eng.db.connect()
    ids = [int(r["id"]) for r in conn.execute("SELECT id FROM semantic_prototypes").fetchall()]
    return eng.semantic.get_many(ids)


@pytest.fixture()
def eng(tmp_path):
    engine = _make_engine(tmp_path, "test.db")
    yield engine
    engine.close()


# ---------------------------------------------------------------------------
# replay_all()
# ---------------------------------------------------------------------------


def test_replay_all_on_empty_db_does_not_crash(eng):
    result = eng.replay_engine.replay_all()
    assert result == {"replay_sampled": 0, "transition_loss": 0.0, "touched_prototype_ids": []}


def test_replay_all_processes_every_episode_not_a_sample(tmp_path):
    small_sample_cfg = ReplayConfig(sample_size=2)
    eng = _make_engine(tmp_path, "small_sample.db", replay=small_sample_cfg)
    try:
        _seed_episodes(eng, 8)
        result = eng.replay_engine.replay_all()
        assert result["replay_sampled"] == 8
    finally:
        eng.close()


def test_replay_all_bypasses_max_prototypes_per_replay_cap(tmp_path):
    capped_cfg = ReplayConfig(max_prototypes_per_replay=1, assignment_threshold=0.9)
    eng = _make_engine(tmp_path, "capped.db", replay=capped_cfg)
    try:
        # 6 well-separated clusters — replay_once would cap new-prototype
        # creation at 1; replay_all must not.
        _seed_episodes(eng, 6)
        result = eng.replay_engine.replay_all()
        assert result["prototypes_touched"] >= 2
        assert eng.semantic.count() >= 2
    finally:
        eng.close()


def test_replay_all_is_deterministic_across_independent_engines(tmp_path):
    cfg = ReplayConfig(assignment_threshold=0.9)
    eng_a = _make_engine(tmp_path, "det_a.db", replay=cfg)
    eng_b = _make_engine(tmp_path, "det_b.db", replay=cfg)
    try:
        _seed_episodes(eng_a, 10)
        _seed_episodes(eng_b, 10)

        result_a = eng_a.replay_engine.replay_all()
        result_b = eng_b.replay_engine.replay_all()

        assert result_a["prototypes_touched"] == result_b["prototypes_touched"]
        assert result_a["touched_prototype_ids"] == result_b["touched_prototype_ids"]
        assert result_a["transition_loss"] == pytest.approx(result_b["transition_loss"])

        centroids_a = sorted(tuple(np.round(p.centroid, 5)) for p in _all_prototypes(eng_a))
        centroids_b = sorted(tuple(np.round(p.centroid, 5)) for p in _all_prototypes(eng_b))
        assert centroids_a == centroids_b
    finally:
        eng_a.close()
        eng_b.close()


def test_replay_all_does_not_mutate_episodic_salience(eng):
    _seed_episodes(eng, 4)
    before = {eid: s for eid, s in eng.episodic.list_saliences()}
    eng.replay_engine.replay_all()
    after = {eid: s for eid, s in eng.episodic.list_saliences()}
    assert before == after


# ---------------------------------------------------------------------------
# consolidate_all()
# ---------------------------------------------------------------------------


def test_consolidate_all_on_empty_db_does_not_crash(eng):
    stats = eng.consolidator.consolidate_all()
    assert stats.prototypes_processed == 0


def test_consolidate_all_processes_every_prototype(eng):
    _seed_episodes(eng, 5, cluster_spread=0.0)
    eng.replay_engine.replay_all()
    n_prototypes = eng.semantic.count()
    assert n_prototypes > 0

    stats = eng.consolidator.consolidate_all()
    assert stats.prototypes_processed == n_prototypes
