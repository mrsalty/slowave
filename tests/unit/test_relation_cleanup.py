"""Regression tests for the 2026-07-14 dead-relation cleanup, plus the
2026-07-15 taxonomy update that reintroduces "relates_to" as a distinct,
actively-used relation (not a revival of the old "related_to" fallback --
that spelling stays dead).

"contradicts" and "related_to" were removed from VALID_RELATIONS: both sat at
0 edges in production (contradicts required an exact time_delta_s<=0 tie that
every call site now records as "supersedes" too; related_to was only ever
add_relation()'s own silent fallback for an invalid relation string, never
triggered by a real caller). See schema_store.py's VALID_RELATIONS comment.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from slowave.core.consolidation import Consolidator
from slowave.latent.schema import GeometricVerdict
from slowave.symbolic.schema_store import VALID_RELATIONS, SchemaStore

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = str(REPO_ROOT / "slowave" / "storage" / "schema.sql")
DIM = 8


@pytest.fixture()
def store():
    db_path = str(Path(tempfile.mkdtemp()) / "test.db")
    from slowave.storage.sqlite_db import SQLiteConfig, SQLiteDB

    db = SQLiteDB(SQLiteConfig(path=db_path))
    db.init_schema(SCHEMA_PATH)
    conn = db.connect()
    conn.execute("PRAGMA foreign_keys = OFF")
    s = SchemaStore(db, dim=DIM)
    yield s
    db.close()


def test_valid_relations_matches_current_taxonomy():
    assert "contradicts" not in VALID_RELATIONS
    assert "related_to" not in VALID_RELATIONS  # old dead fallback spelling
    assert "relates_to" in VALID_RELATIONS  # reintroduced 2026-07-15, distinct spelling
    assert set(VALID_RELATIONS) == {
        "reinforces",
        "refines",
        "supersedes",
        "part_of",
        "relates_to",
    }


def test_add_relation_raises_on_invalid_relation(store):
    emb = np.ones(DIM, dtype=np.float32) / np.sqrt(DIM)
    id_a = store.create(content_text="A", embedding=emb, dedupe=False)
    id_b = store.create(content_text="B", embedding=emb, dedupe=False)

    with pytest.raises(ValueError):
        store.add_relation(src_schema_id=id_a, dst_schema_id=id_b, relation="contradicts")
    with pytest.raises(ValueError):
        store.add_relation(src_schema_id=id_a, dst_schema_id=id_b, relation="related_to")
    # Contrast case: "relates_to" (new spelling) is a valid relation and must
    # NOT be rejected, despite looking almost identical to the dead fallback.
    store.add_relation(src_schema_id=id_a, dst_schema_id=id_b, relation="relates_to")


def test_add_relation_still_accepts_valid_relations(store):
    emb = np.ones(DIM, dtype=np.float32) / np.sqrt(DIM)
    id_a = store.create(content_text="A", embedding=emb, dedupe=False)
    id_b = store.create(content_text="B", embedding=emb, dedupe=False)

    for relation in VALID_RELATIONS:
        store.add_relation(src_schema_id=id_a, dst_schema_id=id_b, relation=relation)

    rows = (
        store.db.connect()
        .execute(
            "SELECT relation FROM schema_relations WHERE src_schema_id=? AND dst_schema_id=?",
            (id_a, id_b),
        )
        .fetchall()
    )
    assert {r["relation"] for r in rows} == set(VALID_RELATIONS)


# ---------------------------------------------------------------------------
# _link_schemas_via_prototype_centroid: regression tests for the confirmed
# production false positive (schema 153 linked to unrelated schema 154 at
# confidence 1.00). The centroid-proximity linker used to write an
# unconditional "reinforces" edge from each pair's similarity to the shared
# prototype centroid alone, without ever comparing the two schemas to EACH
# OTHER -- "both near the same reference point" does not imply "near each
# other". The fix makes it call the real geometric judge on the pair
# directly and dispatch on the judge's actual verdict.
# ---------------------------------------------------------------------------


def _consolidator_with_mocked_judge(store: SchemaStore, verdict: str) -> Consolidator:
    judge = MagicMock()
    judge.judge.return_value = GeometricVerdict(
        verdict=verdict,
        reasoning="test",
        similarity=0.9,
        facet_distance=0.0,
        time_delta_s=0,
    )
    return Consolidator(
        db=store.db,
        semantic=MagicMock(),
        episode_text=MagicMock(),
        schemas=store,
        encoder=None,
        latent_builder=MagicMock(),
        geometric_judge=judge,
    )


def _seed_centroid_pair(store: SchemaStore) -> tuple[int, int, np.ndarray]:
    """Two schemas both close enough to a shared centroid to clear the
    linker's 0.65/0.60 proximity gate."""
    rng = np.random.default_rng(0)
    centroid = rng.standard_normal(DIM).astype(np.float32)
    centroid /= np.linalg.norm(centroid)
    emb_a = centroid + rng.standard_normal(DIM).astype(np.float32) * 0.05
    emb_a /= np.linalg.norm(emb_a)
    emb_b = centroid + rng.standard_normal(DIM).astype(np.float32) * 0.05
    emb_b /= np.linalg.norm(emb_b)
    id_a = store.create(content_text="schema A", embedding=emb_a, dedupe=False)
    id_b = store.create(content_text="schema B", embedding=emb_b, dedupe=False)
    return id_a, id_b, centroid


def test_centroid_linker_calls_judge_not_unconditional_reinforces(store):
    """The judge disagrees ('relates_to') with what the old unconditional
    behavior would have written ('reinforces') -- the linker must defer to
    the judge, not the centroid-proximity gate alone. Direct regression test
    for the 153->154 production false positive."""
    id_a, id_b, centroid = _seed_centroid_pair(store)
    cons = _consolidator_with_mocked_judge(store, verdict="relates_to")

    cons._link_schemas_via_prototype_centroid(1, centroid)

    rows = (
        store.db.connect()
        .execute(
            "SELECT relation FROM schema_relations WHERE src_schema_id IN (?, ?) "
            "AND dst_schema_id IN (?, ?)",
            (id_a, id_b, id_a, id_b),
        )
        .fetchall()
    )
    assert [r["relation"] for r in rows] == ["relates_to"]


def test_centroid_linker_still_writes_reinforces_when_judge_confirms(store):
    """When the judge genuinely agrees the pair reinforces each other, the
    linker still writes 'reinforces' -- the legitimate case is preserved."""
    id_a, id_b, centroid = _seed_centroid_pair(store)
    cons = _consolidator_with_mocked_judge(store, verdict="reinforces")

    cons._link_schemas_via_prototype_centroid(1, centroid)

    rows = (
        store.db.connect()
        .execute(
            "SELECT relation FROM schema_relations WHERE src_schema_id IN (?, ?) "
            "AND dst_schema_id IN (?, ?)",
            (id_a, id_b, id_a, id_b),
        )
        .fetchall()
    )
    assert [r["relation"] for r in rows] == ["reinforces"]


@pytest.mark.parametrize("directional_verdict", ["supersedes", "refines", "part_of"])
def test_centroid_linker_skips_directional_verdicts(store, directional_verdict):
    """A directional verdict (supersedes/refines/part_of) is downgraded to
    relates_to -- this call site has no "which one is newer/more specific"
    context to responsibly assert a directional claim."""
    id_a, id_b, centroid = _seed_centroid_pair(store)
    cons = _consolidator_with_mocked_judge(store, verdict=directional_verdict)

    cons._link_schemas_via_prototype_centroid(1, centroid)

    rows = (
        store.db.connect()
        .execute(
            "SELECT relation FROM schema_relations WHERE src_schema_id IN (?, ?) "
            "AND dst_schema_id IN (?, ?)",
            (id_a, id_b, id_a, id_b),
        )
        .fetchall()
    )
    assert [r["relation"] for r in rows] == ["relates_to"]


def test_centroid_linker_writes_nothing_when_unrelated(store):
    id_a, id_b, centroid = _seed_centroid_pair(store)
    cons = _consolidator_with_mocked_judge(store, verdict="unrelated")

    cons._link_schemas_via_prototype_centroid(1, centroid)

    rows = (
        store.db.connect()
        .execute(
            "SELECT relation FROM schema_relations WHERE src_schema_id IN (?, ?) "
            "AND dst_schema_id IN (?, ?)",
            (id_a, id_b, id_a, id_b),
        )
        .fetchall()
    )
    assert rows == []


# ---------------------------------------------------------------------------
# add_relation: cycle/mutual-exclusivity guard for directional relations
# (refines, supersedes, part_of). A directional relation encodes an
# asymmetric claim -- both directions existing simultaneously for the same
# relation type is a logical contradiction (e.g. A refines B AND B refines
# A can't both be true), not two independent facts. Symmetric relations
# (relates_to, reinforces) are exempt: "A->B" and "B->A" are the same fact
# there, and the guard would otherwise reject a caller that forgot to
# canonicalize src/dst (a real gap, but a documentation responsibility --
# see add_relation's docstring -- not this guard's job to catch).
# ---------------------------------------------------------------------------


def test_add_relation_rejects_reverse_directional_edge(store):
    emb = np.ones(DIM, dtype=np.float32) / np.sqrt(DIM)
    id_a = store.create(content_text="A", embedding=emb, dedupe=False)
    id_b = store.create(content_text="B", embedding=emb, dedupe=False)

    store.add_relation(src_schema_id=id_a, dst_schema_id=id_b, relation="refines")
    with pytest.raises(ValueError):
        store.add_relation(src_schema_id=id_b, dst_schema_id=id_a, relation="refines")

    rows = (
        store.db.connect()
        .execute(
            "SELECT src_schema_id, dst_schema_id FROM schema_relations WHERE relation = 'refines'"
        )
        .fetchall()
    )
    # The rejected write must not have partially landed.
    assert [(r["src_schema_id"], r["dst_schema_id"]) for r in rows] == [(id_a, id_b)]


def test_add_relation_allows_reverse_for_different_relation_types(store):
    emb = np.ones(DIM, dtype=np.float32) / np.sqrt(DIM)
    id_a = store.create(content_text="A", embedding=emb, dedupe=False)
    id_b = store.create(content_text="B", embedding=emb, dedupe=False)

    store.add_relation(src_schema_id=id_a, dst_schema_id=id_b, relation="refines")
    # A different relation type in the reverse direction is not the same
    # kind of contradiction -- the guard is scoped per-relation-type.
    store.add_relation(src_schema_id=id_b, dst_schema_id=id_a, relation="part_of")


def test_add_relation_symmetric_relations_not_blocked_by_guard(store):
    emb = np.ones(DIM, dtype=np.float32) / np.sqrt(DIM)
    id_a = store.create(content_text="A", embedding=emb, dedupe=False)
    id_b = store.create(content_text="B", embedding=emb, dedupe=False)

    store.add_relation(src_schema_id=id_a, dst_schema_id=id_b, relation="reinforces")
    # The guard only applies to _DIRECTIONAL_RELATIONS -- a symmetric
    # relation written in the non-canonical order must not raise.
    store.add_relation(src_schema_id=id_b, dst_schema_id=id_a, relation="reinforces")


def test_add_relation_self_relation_not_blocked(store):
    emb = np.ones(DIM, dtype=np.float32) / np.sqrt(DIM)
    id_a = store.create(content_text="A", embedding=emb, dedupe=False)

    # src == dst must skip the reverse-edge check entirely rather than every
    # self-edge raising against itself (a naive "does the reverse exist"
    # check would always find itself here).
    store.add_relation(src_schema_id=id_a, dst_schema_id=id_a, relation="refines")
