"""Regression tests for SchemaStore.backfill_part_of_edges()'s scope-aware
containment threshold.

Cross-scope pairs are not blocked outright (the brain generalises schemas
across contexts once they've earned it -- see GeneralizationConfig.compute_stage
in schema_store.py), but require a higher subspace-containment score than
same-scope pairs, mirroring how reinforces already treats cross-scope evidence
as weaker (increment_cross_scope_reinforcement's half-weight discount) rather
than trusting it exactly as much as same-scope evidence.

These tests build two schemas A/B with a hand-constructed embedding/facet-axis
geometry that produces an exact, known containment score (see comments below),
so the same c_ab value can be checked against both the same-scope and
cross-scope thresholds.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

from slowave.symbolic.schema_store import SchemaStore
from slowave.utils.vec import pack_f32

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = str(REPO_ROOT / "slowave" / "storage" / "schema.sql")
DIM = 8


@pytest.fixture()
def make_store():
    stores = []

    def _make():
        db_path = str(Path(tempfile.mkdtemp()) / "test.db")
        from slowave.storage.sqlite_db import SQLiteConfig, SQLiteDB

        db = SQLiteDB(SQLiteConfig(path=db_path))
        db.init_schema(SCHEMA_PATH)
        conn = db.connect()
        conn.execute("PRAGMA foreign_keys = OFF")
        store = SchemaStore(db, dim=DIM)
        stores.append(db)
        return store

    yield _make
    for db in stores:
        db.close()


def _seed_pair(store: SchemaStore, *, containment: float, scope_a: str | None, scope_b: str | None):
    """Create an A/B schema pair with cos(A,B) ~= 0.85 (inside the [0.70, 0.92)
    comparison band) and a hand-computed c_ab (A-within-B containment) equal
    to `containment`, with c_ba ~= 0 (B is not within A) so the asymmetry
    margin is always satisfied and only the containment threshold is at
    stake in these tests.
    """
    cos_t = 0.85
    sin_t = float(np.sqrt(1 - cos_t**2))

    a_emb = np.zeros(DIM, dtype=np.float32)
    a_emb[0] = 1.0
    b_emb = np.zeros(DIM, dtype=np.float32)
    b_emb[0] = cos_t
    b_emb[1] = sin_t

    # diff_ab = a_emb - b_emb = (1-cos_t)*e0 - sin_t*e1; dn_ab is fixed by cos_t.
    dn_ab = (1 - cos_t) ** 2 + sin_t**2

    # B's single facet axis u = cos(theta)*e1 + sin(theta)*e2 is tuned so that
    # c_ab = (sin_t*cos(theta))^2 / dn_ab lands exactly on `containment`.
    max_c_ab = sin_t**2 / dn_ab  # theta=0 upper bound (~0.925 at cos_t=0.85)
    assert containment <= max_c_ab, "requested containment unreachable with this geometry"
    cos_theta = float(np.sqrt(containment / max_c_ab))
    sin_theta = float(np.sqrt(1 - cos_theta**2))

    b_axis = np.zeros((1, DIM), dtype=np.float32)
    b_axis[0, 1] = cos_theta
    b_axis[0, 2] = sin_theta

    # A's facet axes are orthogonal to the diff vector entirely -> c_ba = 0.
    a_axes = np.zeros((2, DIM), dtype=np.float32)
    a_axes[0, 3] = 1.0
    a_axes[1, 4] = 1.0

    id_a = store.create(
        content_text="schema A (broader)",
        embedding=a_emb,
        facet_axes=a_axes,
        facet_strengths=np.array([1.0, 1.0], dtype=np.float32),
        scope_id=scope_a,
        dedupe=False,
    )
    id_b = store.create(
        content_text="schema B (narrower)",
        embedding=b_emb,
        facet_axes=b_axis,
        facet_strengths=np.array([1.0], dtype=np.float32),
        scope_id=scope_b,
        dedupe=False,
    )
    return id_a, id_b


def _part_of_edge(store: SchemaStore, src: int, dst: int) -> bool:
    row = (
        store.db.connect()
        .execute(
            "SELECT 1 FROM schema_relations WHERE src_schema_id=? AND dst_schema_id=? "
            "AND relation='part_of'",
            (src, dst),
        )
        .fetchone()
    )
    return row is not None


def test_same_scope_pair_created_between_thresholds(make_store):
    """containment=0.62 clears the same-scope threshold (0.55)."""
    store = make_store()
    id_a, id_b = _seed_pair(store, containment=0.62, scope_a="proj:x", scope_b="proj:x")
    stats = store.backfill_part_of_edges()
    assert stats["created"] == 1
    assert _part_of_edge(store, id_a, id_b)


def test_cross_scope_pair_blocked_between_thresholds(make_store):
    """Same containment=0.62 clears the same-scope threshold but NOT the
    stricter cross-scope threshold (0.75) -- no edge should be created."""
    store = make_store()
    _seed_pair(store, containment=0.62, scope_a="proj:x", scope_b="proj:y")
    stats = store.backfill_part_of_edges()
    assert stats["created"] == 0


def test_cross_scope_pair_created_above_cross_scope_threshold(make_store):
    """containment=0.8 clears the stricter cross-scope threshold (0.75) --
    cross-scope part_of edges are allowed when the evidence is strong enough,
    not blocked outright."""
    store = make_store()
    id_a, id_b = _seed_pair(store, containment=0.8, scope_a="proj:x", scope_b="proj:y")
    stats = store.backfill_part_of_edges()
    assert stats["created"] == 1
    assert _part_of_edge(store, id_a, id_b)


def test_null_scope_treated_as_same_scope(make_store):
    """A None scope_id (global/unscoped schema) on either side should not
    trigger the cross-scope penalty -- only two distinct non-null scopes do."""
    store = make_store()
    id_a, id_b = _seed_pair(store, containment=0.62, scope_a=None, scope_b="proj:y")
    stats = store.backfill_part_of_edges()
    assert stats["created"] == 1
    assert _part_of_edge(store, id_a, id_b)


def test_restrict_ids_skips_pairs_with_neither_side_restricted(make_store):
    """restrict_ids must still find a valid pair when one side is in the
    restricted set, but must skip a pair where neither side is -- this is
    what turns the full O(N^2) backfill into an incremental O(new*N) pass."""
    store = make_store()
    id_a, id_b = _seed_pair(store, containment=0.62, scope_a="proj:x", scope_b="proj:x")

    # Neither id_a nor id_b is in restrict_ids -> must be skipped entirely.
    stats = store.backfill_part_of_edges(restrict_ids=[999999])
    assert stats["created"] == 0
    assert not _part_of_edge(store, id_a, id_b)

    # id_b is in restrict_ids -> the pair is now compared and created.
    stats = store.backfill_part_of_edges(restrict_ids=[id_b])
    assert stats["created"] == 1
    assert _part_of_edge(store, id_a, id_b)


def test_backfill_facet_axes_returns_ids_for_incremental_part_of_pass(make_store):
    """backfill_facet_axes must report which schema ids it just gave facet
    axes to, so ConsolidationService can feed them straight into
    backfill_part_of_edges(restrict_ids=...) as an incremental pass."""
    store = make_store()
    conn = store.db.connect()

    rng = np.random.default_rng(3)
    episode_ids = []
    for i in range(3):
        emb = rng.standard_normal(DIM).astype(np.float32)
        emb /= np.linalg.norm(emb)
        cur = conn.execute(
            "INSERT INTO episodic_memories "
            "(event_id, ts, embedding, dim, salience, last_salience_ts, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"evt-{i}", int(time.time()), pack_f32(emb), DIM, 1.0, int(time.time()), "{}"),
        )
        episode_ids.append(cur.lastrowid)
    conn.commit()

    normed = rng.standard_normal(DIM).astype(np.float32)
    normed /= np.linalg.norm(normed)
    schema_id = store.create(
        content_text="a schema with enough support to earn facet axes",
        embedding=normed,
        supporting_episode_ids=episode_ids,
        dedupe=False,
    )

    stats = store.backfill_facet_axes(min_members=3)
    assert stats["backfilled"] == 1
    assert stats["backfilled_ids"] == [schema_id]
