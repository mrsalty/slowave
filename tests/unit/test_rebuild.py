"""Tests for RebuildService — auto-migration of derived memory state on a
logic_version bump. See slowave/core/services/rebuild.py and
private/docs/iterations/20260716_event-store-replay.md.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from slowave.core.config import SlowaveConfig
from slowave.core.consolidation import Consolidator
from slowave.core.engine import SlowaveEngine
from slowave.core.services.rebuild import RebuildService
from slowave.storage.sqlite_db import SQLiteConfig, SQLiteDB


def _make_engine(tmp_path, name: str, dim: int = 32, current_logic_version: str = "0"):
    cfg = SlowaveConfig(
        db_path=str(tmp_path / name),
        dim=dim,
        disable_encoder=True,
        current_logic_version=current_logic_version,
    )
    return SlowaveEngine(cfg)


def _seed_session(eng: SlowaveEngine, *, n_events: int = 4, seed: int = 42) -> str:
    """Populate a real session of raw_events (not the episodic.add() shortcut)
    so form_episodes() has something to do — explicit embeddings, no encoder
    needed."""
    sid = eng.session_start(agent="test")
    rng = np.random.default_rng(seed)
    for i in range(n_events):
        emb = rng.standard_normal(eng.cfg.dim).astype(np.float32)
        emb /= np.linalg.norm(emb)
        eng.raw_log.append(
            session_id=sid, type="user_message", content=f"event content {i}", embedding=emb
        )
    eng.session_end(sid)
    return sid


def _rebuild_stub_db(tmp_path, name: str) -> tuple[SQLiteDB, SlowaveConfig]:
    """A bare SQLiteDB + SlowaveConfig for needs_rebuild()/try_claim() tests
    that don't need a full engine."""
    cfg = SlowaveConfig(db_path=str(tmp_path / name), dim=8, disable_encoder=True)
    db = SQLiteDB(SQLiteConfig(path=cfg.db_path))
    db.init_schema(SlowaveConfig.default_schema_path())
    return db, cfg


# ---------------------------------------------------------------------------
# needs_rebuild()
# ---------------------------------------------------------------------------


def test_needs_rebuild_false_when_no_raw_events(tmp_path):
    db, cfg = _rebuild_stub_db(tmp_path, "empty.db")
    assert RebuildService.needs_rebuild(db, cfg) is False


def test_needs_rebuild_false_when_all_events_already_match_current_version(tmp_path):
    """Regression guard: a DB that has always been ingested under the
    current version (the overwhelmingly common case — no version bump has
    ever happened) must never look like it needs a rebuild just because no
    replay_checkpoints row exists yet (only a rebuild ever writes one).
    Getting this wrong wipes perfectly current derived state on literally
    every second engine construction against any populated DB."""
    db, cfg = _rebuild_stub_db(tmp_path, "events.db")
    conn = db.connect()
    conn.execute("INSERT INTO sessions (id, agent, started_ts) VALUES ('s1', 'test', 1000)")
    conn.execute(
        "INSERT INTO raw_events (session_id, ts, type, content, logic_version) "
        "VALUES ('s1', 1000, 'user_message', 'hi', ?)",
        (cfg.current_logic_version,),
    )
    conn.commit()
    assert RebuildService.needs_rebuild(db, cfg) is False


def test_needs_rebuild_true_when_events_are_tagged_with_an_older_version(tmp_path):
    db, cfg = _rebuild_stub_db(tmp_path, "stale_events.db")
    cfg = dataclasses.replace(cfg, current_logic_version="v2")
    conn = db.connect()
    conn.execute("INSERT INTO sessions (id, agent, started_ts) VALUES ('s1', 'test', 1000)")
    conn.execute(
        "INSERT INTO raw_events (session_id, ts, type, content, logic_version) "
        "VALUES ('s1', 1000, 'user_message', 'hi', '0')"
    )
    conn.commit()
    assert RebuildService.needs_rebuild(db, cfg) is True


def test_needs_rebuild_false_when_already_migrated_to_current_version(tmp_path):
    db, cfg = _rebuild_stub_db(tmp_path, "already_migrated.db")
    cfg = dataclasses.replace(cfg, current_logic_version="v2")
    conn = db.connect()
    conn.execute("INSERT INTO sessions (id, agent, started_ts) VALUES ('s1', 'test', 1000)")
    conn.execute(
        "INSERT INTO raw_events (session_id, ts, type, content, logic_version) "
        "VALUES ('s1', 1000, 'user_message', 'hi', '0')"
    )
    conn.execute(
        "INSERT INTO replay_checkpoints "
        "(created_ts, logic_version, last_event_id, last_episode_id, episode_count, "
        " prototype_count, schema_count) VALUES (1000, 'v2', 1, 0, 0, 0, 0)"
    )
    conn.commit()
    assert RebuildService.needs_rebuild(db, cfg) is False


# ---------------------------------------------------------------------------
# try_claim()
# ---------------------------------------------------------------------------


def test_try_claim_first_call_wins(tmp_path):
    db, cfg = _rebuild_stub_db(tmp_path, "claim.db")
    assert RebuildService.try_claim(db, cfg, now=1000) is True


def test_try_claim_second_call_loses_when_not_stale(tmp_path):
    db, cfg = _rebuild_stub_db(tmp_path, "claim_race.db")
    assert RebuildService.try_claim(db, cfg, now=1000) is True
    # Immediately after — no time has passed, so the claim isn't stale.
    assert RebuildService.try_claim(db, cfg, now=1001) is False


def test_try_claim_records_description(tmp_path):
    db, cfg = _rebuild_stub_db(tmp_path, "claim_desc.db")
    cfg = dataclasses.replace(cfg, current_logic_version_description="fixes prototype drift")
    RebuildService.try_claim(db, cfg, now=1000)
    row = (
        db.connect()
        .execute(
            "SELECT description FROM logic_versions WHERE version = ?", (cfg.current_logic_version,)
        )
        .fetchone()
    )
    assert row["description"] == "fixes prototype drift"


def test_try_claim_reclaims_a_stale_claim(tmp_path):
    db, cfg = _rebuild_stub_db(tmp_path, "stale_claim.db")
    assert RebuildService.try_claim(db, cfg, now=1000) is True
    # Far enough in the future that the first claim is stale.
    later = 1000 + 10_000
    assert RebuildService.try_claim(db, cfg, now=later) is True


def test_try_claim_does_not_reclaim_a_fresh_claim(tmp_path):
    db, cfg = _rebuild_stub_db(tmp_path, "fresh_claim.db")
    assert RebuildService.try_claim(db, cfg, now=1000) is True
    # A few seconds later — not stale yet.
    assert RebuildService.try_claim(db, cfg, now=1005) is False


def test_try_claim_gives_up_after_max_attempts(tmp_path):
    db, cfg = _rebuild_stub_db(tmp_path, "exhausted_claim.db")
    now = 1000
    assert RebuildService.try_claim(db, cfg, now=now) is True
    # Repeatedly "reclaim" a stale-but-never-completed migration until the
    # attempt cap is hit; the final attempt must be refused rather than
    # retried forever.
    for _ in range(10):
        now += 10_000
        won = RebuildService.try_claim(db, cfg, now=now)
    conn = db.connect()
    row = conn.execute(
        "SELECT claim_attempts FROM logic_versions WHERE version = ?",
        (cfg.current_logic_version,),
    ).fetchone()
    # Matches RebuildService._MAX_CLAIM_ATTEMPTS — capped, not incremented forever.
    assert row["claim_attempts"] == 5
    assert won is False


# ---------------------------------------------------------------------------
# run() — end-to-end
# ---------------------------------------------------------------------------


def test_run_on_empty_db_produces_zero_stats(tmp_path):
    eng = _make_engine(tmp_path, "run_empty.db")
    try:
        stats = RebuildService.run(eng.db, eng.cfg)
        assert stats.sessions_processed == 0
        assert stats.episodes_formed == 0
        assert stats.episode_count == 0
    finally:
        eng.close()


def test_run_processes_sessions_and_writes_checkpoint(tmp_path):
    eng = _make_engine(tmp_path, "run_basic.db")
    try:
        _seed_session(eng, n_events=6)
        stats = RebuildService.run(eng.db, eng.cfg)
        assert stats.sessions_processed == 1
        assert stats.episodes_formed > 0
        assert stats.episode_count == stats.episodes_formed

        conn = eng.db.connect()
        row = conn.execute(
            "SELECT * FROM replay_checkpoints WHERE logic_version = ?",
            (eng.cfg.current_logic_version,),
        ).fetchone()
        assert row is not None
        assert row["episode_count"] == stats.episode_count
    finally:
        eng.close()


def test_run_is_deterministic_across_independent_engines(tmp_path):
    eng_a = _make_engine(tmp_path, "det_a.db")
    eng_b = _make_engine(tmp_path, "det_b.db")
    try:
        _seed_session(eng_a, n_events=8, seed=7)
        _seed_session(eng_b, n_events=8, seed=7)

        stats_a = RebuildService.run(eng_a.db, eng_a.cfg)
        stats_b = RebuildService.run(eng_b.db, eng_b.cfg)

        assert stats_a.episode_count == stats_b.episode_count
        assert stats_a.prototype_count == stats_b.prototype_count
        assert stats_a.schema_count == stats_b.schema_count

        centroids_a = sorted(
            tuple(np.round(row["centroid_arr"], 5)) for row in _prototype_centroids(eng_a)
        )
        centroids_b = sorted(
            tuple(np.round(row["centroid_arr"], 5)) for row in _prototype_centroids(eng_b)
        )
        assert centroids_a == centroids_b
    finally:
        eng_a.close()
        eng_b.close()


def _prototype_centroids(eng: SlowaveEngine):
    from slowave.utils.vec import unpack_f32

    conn = eng.db.connect()
    rows = conn.execute("SELECT centroid, dim FROM semantic_prototypes").fetchall()
    return [{"centroid_arr": unpack_f32(r["centroid"], int(r["dim"]))} for r in rows]


def test_run_wipes_and_rebuilds_derived_tables_idempotently(tmp_path):
    """Calling run() twice in a row must not duplicate episodes/schemas —
    each call wipes derived state and rebuilds fresh from raw_events."""
    eng = _make_engine(tmp_path, "run_idempotent.db")
    try:
        _seed_session(eng, n_events=5)
        stats_first = RebuildService.run(eng.db, eng.cfg)
        stats_second = RebuildService.run(eng.db, eng.cfg)
        assert stats_first.episode_count == stats_second.episode_count
        assert stats_first.prototype_count == stats_second.prototype_count
    finally:
        eng.close()


# ---------------------------------------------------------------------------
# on_start callback
# ---------------------------------------------------------------------------


def test_run_invokes_on_start_exactly_once(tmp_path):
    eng = _make_engine(tmp_path, "on_start.db")
    try:
        _seed_session(eng)
        calls = []
        RebuildService.run(eng.db, eng.cfg, on_start=lambda: calls.append(1))
        assert len(calls) == 1
    finally:
        eng.close()


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------


def test_run_failure_propagates_and_leaves_claim_unresolved(tmp_path, monkeypatch):
    eng = _make_engine(tmp_path, "run_failure.db", current_logic_version="v9")
    try:
        _seed_session(eng)
        RebuildService.try_claim(eng.db, eng.cfg)

        def _boom(self, *args, **kwargs):
            raise RuntimeError("simulated consolidation failure")

        monkeypatch.setattr(Consolidator, "consolidate_all", _boom)

        with pytest.raises(RuntimeError):
            RebuildService.run(eng.db, eng.cfg)

        row = (
            eng.db.connect()
            .execute("SELECT replayed_from_scratch FROM logic_versions WHERE version = ?", ("v9",))
            .fetchone()
        )
        assert row["replayed_from_scratch"] == 0
    finally:
        eng.close()


def test_engine_startup_survives_a_migration_failure(tmp_path, monkeypatch):
    """A bug in a new logic version's rebuild must never prevent the engine
    from starting — the broad except in SlowaveEngine.__init__ must catch it."""
    cfg = SlowaveConfig(
        db_path=str(tmp_path / "resilient.db"),
        dim=16,
        disable_encoder=True,
        current_logic_version="0",
    )
    eng = SlowaveEngine(cfg)
    _seed_session(eng)
    eng.close()

    def _boom(self, *args, **kwargs):
        raise RuntimeError("simulated rebuild failure")

    monkeypatch.setattr(Consolidator, "consolidate_all", _boom)

    cfg_v2 = dataclasses.replace(cfg, current_logic_version="v2")
    # Must not raise, even though the migration this triggers will fail internally.
    eng2 = SlowaveEngine(cfg_v2)
    try:
        assert eng2.stats()["episodes"] >= 0  # engine is usable
    finally:
        eng2.close()
