from __future__ import annotations

import os
import tempfile

import numpy as np

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.symbolic.schema_store import normalize_schema_text


def _tmp_engine() -> tuple[SlowaveEngine, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    cfg = SlowaveConfig(db_path=tmp.name, dim=8, disable_encoder=True)
    return SlowaveEngine(cfg), tmp.name


def _cleanup(path: str) -> None:
    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            os.remove(p)


def test_normalize_schema_text_is_conservative() -> None:
    assert normalize_schema_text("  User   prefers X\n") == "user prefers x"


def test_schema_create_reinforces_exact_duplicate_within_project() -> None:
    eng, path = _tmp_engine()
    try:
        emb = np.ones(8, dtype=np.float32)
        first = eng.schemas.create(
            content_text="User prefers blunt architectural feedback.",
            facets={"schema_class": "preference"},
            tags=["preference"],
            embedding=emb,
            scope_id="project:slowave",
            salience=1.4,
            supporting_episode_ids=[1],
        )
        second = eng.schemas.create(
            content_text=" user prefers blunt architectural feedback. ",
            facets={"schema_class": "preference"},
            tags=["code-review"],
            embedding=emb,
            scope_id="project:slowave",
            salience=1.4,
            supporting_episode_ids=[2],
        )

        assert second == first
        assert eng.schemas.count() == 1
        s = eng.schemas.get(first)
        assert s.supporting_episode_ids == [1, 2]
        assert s.salience > 1.4
        assert "code-review" in s.tags
    finally:
        eng.close()
        _cleanup(path)


def test_schema_create_keeps_same_text_in_different_projects_separate() -> None:
    eng, path = _tmp_engine()
    try:
        emb = np.ones(8, dtype=np.float32)
        a = eng.schemas.create(
            content_text="Use SQLite for MVPs.",
            embedding=emb,
            scope_id="project:slowave",
        )
        b = eng.schemas.create(
            content_text="Use SQLite for MVPs.",
            embedding=emb,
            scope_id="project:other",
        )
        assert a != b
        assert eng.schemas.count() == 2
    finally:
        eng.close()
        _cleanup(path)


def test_dedup_exact_archives_duplicates_and_filters_fts() -> None:
    eng, path = _tmp_engine()
    try:
        emb = np.ones(8, dtype=np.float32)
        canonical = eng.schemas.create(
            content_text="For future code reviews, user prefers blunt feedback.",
            embedding=emb,
            scope_id="project:slowave",
            salience=5.0,
            supporting_episode_ids=[1],
            dedupe=False,
        )
        duplicate = eng.schemas.create(
            content_text="For future code reviews, user prefers blunt feedback.",
            embedding=emb,
            scope_id="project:slowave",
            salience=1.4,
            supporting_episode_ids=[2],
            dedupe=False,
        )
        assert canonical != duplicate

        dry = eng.dedup_schemas_exact(dry_run=True)
        assert dry["duplicate_rows"] == 1

        applied = eng.dedup_schemas_exact(dry_run=False)
        assert applied["merged_rows"] == 1

        health = eng.schema_health()
        assert health["active_schemas"] == 1
        assert health["active_exact_duplicate_rows"] == 0
        assert eng.schemas.get(canonical).supporting_episode_ids == [1, 2]
        assert eng.schemas.get(duplicate).status == "archived"
        assert duplicate not in eng.schemas.search_fts("blunt feedback", include_inactive=False)
        assert duplicate in eng.schemas.search_fts("blunt feedback", include_inactive=True)
    finally:
        eng.close()
        _cleanup(path)