"""Regression tests for the 2026-07-14 dead-relation cleanup.

"contradicts" and "related_to" were removed from VALID_RELATIONS: both sat at
0 edges in production (contradicts required an exact time_delta_s<=0 tie that
every call site now records as "supersedes" too; related_to was only ever
add_relation()'s own silent fallback for an invalid relation string, never
triggered by a real caller). See schema_store.py's VALID_RELATIONS comment.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

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


def test_valid_relations_no_longer_includes_dead_types():
    assert "contradicts" not in VALID_RELATIONS
    assert "related_to" not in VALID_RELATIONS
    assert set(VALID_RELATIONS) == {"reinforces", "refines", "supersedes", "part_of"}


def test_add_relation_raises_on_invalid_relation(store):
    emb = np.ones(DIM, dtype=np.float32) / np.sqrt(DIM)
    id_a = store.create(content_text="A", embedding=emb, dedupe=False)
    id_b = store.create(content_text="B", embedding=emb, dedupe=False)

    with pytest.raises(ValueError):
        store.add_relation(src_schema_id=id_a, dst_schema_id=id_b, relation="contradicts")
    with pytest.raises(ValueError):
        store.add_relation(src_schema_id=id_a, dst_schema_id=id_b, relation="related_to")


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
