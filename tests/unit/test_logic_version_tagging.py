"""Tests for logic_version tagging (event-store-replay plan, point 2).

Every raw event, schema, and (newly created) prototype is stamped with the
logic_version active when it was written, so a future rebuild can scope
itself to "state produced under an old version" instead of reprocessing
everything. See private/docs/iterations/20260716_event-store-replay.md.
"""

from __future__ import annotations

import numpy as np
import pytest

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.latent.semantic_store import SemanticStore, SemanticStoreConfig
from slowave.storage.sqlite_db import SQLiteConfig, SQLiteDB
from slowave.symbolic.raw_log import RawLog
from slowave.symbolic.schema_store import SchemaStore


class _StubEncoder:
    def __init__(self, dim: int = 32):
        self._dim = dim

    def encode(self, text: str) -> np.ndarray:
        seed = int(abs(hash(text)) % (2**31))
        v = np.random.default_rng(seed).standard_normal(self._dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-12)


def _make_engine(tmp_path, name: str, dim: int = 32, current_logic_version: str = "0"):
    cfg = SlowaveConfig(
        db_path=str(tmp_path / name),
        dim=dim,
        disable_encoder=True,
        current_logic_version=current_logic_version,
    )
    eng = SlowaveEngine(cfg)
    eng.encoder = _StubEncoder(dim)
    return eng


# ---------------------------------------------------------------------------
# Store-level defaults
# ---------------------------------------------------------------------------


def test_raw_event_default_logic_version_is_zero(tmp_path):
    db = SQLiteDB(SQLiteConfig(path=str(tmp_path / "raw.db")))
    db.init_schema(SlowaveConfig.default_schema_path())
    raw_log = RawLog(db)
    raw_log.start_session(session_id="s1", agent="test")
    eid = raw_log.append(session_id="s1", type="user_message", content="hello")
    assert raw_log.get(eid).logic_version == "0"


def test_raw_event_explicit_logic_version_is_stored(tmp_path):
    db = SQLiteDB(SQLiteConfig(path=str(tmp_path / "raw.db")))
    db.init_schema(SlowaveConfig.default_schema_path())
    raw_log = RawLog(db)
    raw_log.start_session(session_id="s1", agent="test")
    eid = raw_log.append(session_id="s1", type="user_message", content="hello", logic_version="v2")
    assert raw_log.get(eid).logic_version == "v2"


def test_schema_create_default_logic_version(tmp_path):
    db = SQLiteDB(SQLiteConfig(path=str(tmp_path / "schemas.db")))
    db.init_schema(SlowaveConfig.default_schema_path())
    schemas = SchemaStore(db, dim=32)
    sid = schemas.create(content_text="a fact", embedding=None, dedupe=False)
    assert schemas.get(sid).logic_version == "0"


def test_schema_create_explicit_logic_version(tmp_path):
    db = SQLiteDB(SQLiteConfig(path=str(tmp_path / "schemas.db")))
    db.init_schema(SlowaveConfig.default_schema_path())
    schemas = SchemaStore(db, dim=32)
    sid = schemas.create(content_text="a fact", embedding=None, dedupe=False, logic_version="v2")
    assert schemas.get(sid).logic_version == "v2"


def test_prototype_create_stamps_logic_version(tmp_path):
    db = SQLiteDB(SQLiteConfig(path=str(tmp_path / "proto.db")))
    db.init_schema(SlowaveConfig.default_schema_path())
    semantic = SemanticStore(db, SemanticStoreConfig(dim=8))
    centroid = np.ones(8, dtype=np.float32) / np.sqrt(8)
    pid = semantic.upsert_prototype(
        prototype_id=None,
        centroid=centroid,
        support_count=1,
        variance=0.0,
        logic_version="v2",
    )
    assert semantic.get(pid).logic_version == "v2"


def test_prototype_update_does_not_change_logic_version(tmp_path):
    db = SQLiteDB(SQLiteConfig(path=str(tmp_path / "proto.db")))
    db.init_schema(SlowaveConfig.default_schema_path())
    semantic = SemanticStore(db, SemanticStoreConfig(dim=8))
    centroid = np.ones(8, dtype=np.float32) / np.sqrt(8)
    pid = semantic.upsert_prototype(
        prototype_id=None,
        centroid=centroid,
        support_count=1,
        variance=0.0,
        logic_version="v1",
    )
    # Update path takes no logic_version — must not overwrite the original.
    semantic.upsert_prototype(
        prototype_id=pid,
        centroid=centroid,
        support_count=2,
        variance=0.0,
    )
    assert semantic.get(pid).logic_version == "v1"


# ---------------------------------------------------------------------------
# End-to-end: SlowaveConfig.current_logic_version propagation
# ---------------------------------------------------------------------------


@pytest.fixture()
def eng_v3(tmp_path):
    engine = _make_engine(tmp_path, "engine_v3.db", current_logic_version="v3")
    yield engine
    engine.close()


def test_engine_current_logic_version_propagates_to_raw_events(eng_v3):
    sid = eng_v3.session_start(agent="test")
    event_id = eng_v3.event_append(session_id=sid, type="user_message", content="hello")
    assert eng_v3.raw_log.get(event_id).logic_version == "v3"


def test_engine_current_logic_version_propagates_to_remember_schema(eng_v3):
    result = eng_v3.remember(content="SessionReaper idle timeout defaults to 3600s", type="fact")
    assert eng_v3.schemas.get(result.schema_id).logic_version == "v3"


def test_engine_current_logic_version_propagates_to_replay_created_prototypes(eng_v3):
    rng = np.random.default_rng(7)
    emb = rng.standard_normal(32).astype(np.float32)
    emb /= np.linalg.norm(emb)
    eng_v3.episodic.add(
        event_id="seed_0", ts=1000, embedding=emb, salience=0.5, metadata={"kind": "micro"}
    )
    result = eng_v3.replay_engine.replay_all()
    assert result["prototypes_touched"] >= 1
    new_proto_id = result["touched_prototype_ids"][0]
    assert eng_v3.semantic.get(new_proto_id).logic_version == "v3"


def test_consolidator_created_schema_gets_logic_version(eng_v3):
    """Schemas created via Consolidator._consolidate_latent() (not the
    engine.remember() path) must also be stamped — Consolidator.logic_version
    is threaded in at SlowaveEngine construction."""
    sid = eng_v3.session_start(agent="test")
    rng = np.random.default_rng(42)
    for i in range(4):
        emb = rng.standard_normal(32).astype(np.float32)
        emb /= np.linalg.norm(emb)
        eng_v3.raw_log.append(
            session_id=sid, type="user_message", content=f"event content {i}", embedding=emb
        )
    eng_v3.session_end(sid)
    schemas_before = {s.id for s in eng_v3.schemas.list(limit=50)}

    eng_v3.consolidate_once()

    new_schemas = [s for s in eng_v3.schemas.list(limit=50) if s.id not in schemas_before]
    if not new_schemas:
        pytest.skip("consolidation produced no new latent schemas for this seed")
    assert all(s.logic_version == "v3" for s in new_schemas)


def test_default_engine_logic_version_is_zero(tmp_path):
    eng = _make_engine(tmp_path, "engine_default.db")
    try:
        sid = eng.session_start(agent="test")
        event_id = eng.event_append(session_id=sid, type="user_message", content="hello")
        assert eng.raw_log.get(event_id).logic_version == "0"
    finally:
        eng.close()
