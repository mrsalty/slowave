"""Regression test for a root-cause finding, not just a hypothesis.

plans/05-consolidation.md flagged Q7 as an open question: is `contradicts`
rare because most real prototypes have too few members to compute facet
axes (LatentSchemaConfig.min_members_for_facets=3)? The 2026-07-09 B1/B2
StaleMemory runs (26,250 prototypes combined, 0 contradicts observed either
way) motivated digging further.

The actual answer is stronger than "rare": `contradicts` is provably
UNREACHABLE via Consolidator._write_latent_schema, regardless of the new
schema's member count. `_write_latent_schema` reconstructs the *old*
schema's LatentSchema view with `facet_axes=np.zeros((0, dim))` — an
unconditional, always-empty placeholder — because facet axes are never
persisted anywhere retrievable (only bound lossily into a VSA hypervector
blob; see 05-consolidation.md's VSA encoding section). In
GeometricContradictionJudge.judge() (schema.py line ~538), the facet-distance
branch only activates `if old.facet_axes.size > 0 and new.facet_axes.size > 0`
— since old.facet_axes.size is always 0 on this path, facet_dist is always
exactly 0.0, which is always < contradicts_facet_dist (0.35). The
"contradicts" verdict (schema.py line ~550, `facet_dist >= contradicts_facet_dist`)
can therefore never fire here, no matter how divergent the new schema's
real facet axes are from the old schema's true (but unreconstructable)
structure.

Note this is orthogonal to the existing tests in
test_contradiction_support_gate.py, which all mock `judge.judge()` directly
to inject a "contradicts" verdict and test the downstream support/recency
gates — none of them exercise the real facet-axis comparison, so none of
them could have caught this.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from slowave.core.consolidation import Consolidator
from slowave.latent.schema import GeometricContradictionJudge, GeometricJudgeConfig, LatentSchema

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = str(REPO_ROOT / "slowave" / "storage" / "schema.sql")
DIM = 32


@pytest.fixture()
def consolidator():
    db_path = str(Path(tempfile.mkdtemp()) / "test.db")
    from slowave.storage.sqlite_db import SQLiteConfig, SQLiteDB

    db = SQLiteDB(SQLiteConfig(path=db_path))
    db.init_schema(SCHEMA_PATH)
    conn = db.connect()
    conn.execute("PRAGMA foreign_keys = OFF")

    judge = GeometricContradictionJudge(GeometricJudgeConfig())
    cons = Consolidator(
        db=db,
        semantic=MagicMock(),
        episode_text=MagicMock(),
        schemas=MagicMock(),
        encoder=None,
        latent_builder=MagicMock(),
        geometric_judge=judge,
    )
    cons.schemas.create.return_value = 42
    cons.schemas.last_create_reinforced_existing_id = None
    cons.schemas.search_embedding.return_value = []  # never hit the near-dup guard
    yield cons
    db.close()


def _same_topic_centroids(cos_target: float):
    old_centroid = np.zeros(DIM, dtype=np.float32)
    old_centroid[0] = 1.0
    orth = np.zeros(DIM, dtype=np.float32)
    orth[1] = 1.0
    new_centroid = cos_target * old_centroid + float(np.sqrt(1 - cos_target**2)) * orth
    new_centroid = (new_centroid / np.linalg.norm(new_centroid)).astype(np.float32)
    return old_centroid, new_centroid


def test_contradicts_unreachable_even_with_maximally_divergent_new_facets(consolidator):
    """cos=0.85 lands squarely in the facet-comparison band
    (same_topic_cosine=0.75 <= cos < reinforce_cosine=0.95). The new schema
    is given real, well-formed facet axes (as if built from >=3 members).
    The real (unmocked) judge is invoked end-to-end through
    _write_latent_schema. Verdict must be "refines", never "contradicts",
    because old.facet_axes is always empty on this path."""
    old_centroid, new_centroid = _same_topic_centroids(cos_target=0.85)

    new_schema = LatentSchema(
        centroid=new_centroid,
        facet_axes=np.eye(4, DIM, dtype=np.float32),  # 4 orthonormal axes
        facet_strengths=np.array([1.0, 0.5, 0.3, 0.1], dtype=np.float32),
        member_episode_ids=[1, 2, 3, 4, 5],
        central_episode_id=1,
        central_episode_text="the deployment target is now kubernetes",
        mean_ts=5000,
        ts_span_s=100,
        tags=[],
        confidence=0.9,
        support_count=5,
        facets={"source_kind": "consolidation"},
    )
    related_schema = MagicMock(
        id=7,
        content_text="the deployment target is docker swarm",
        confidence=1.0,
        facets={},
        scope_id=None,
    )

    with patch.object(consolidator, "_best_related_schema", return_value=related_schema):
        with patch.object(consolidator, "_fetch_schema_embedding", return_value=old_centroid):
            with patch.object(consolidator, "_scope_for_episodes", return_value=None):
                outcome, new_id = consolidator._write_latent_schema(
                    prototype_id=1, schema=new_schema
                )

    assert outcome == "reinforced"  # "refines" always maps to outcome "reinforced"
    assert outcome != "contradicted"
    consolidator.schemas.add_relation.assert_called_once()
    _, kwargs = consolidator.schemas.add_relation.call_args
    assert kwargs["relation"] == "refines"


def test_facet_distance_is_always_zero_for_the_old_view(consolidator):
    """Direct proof at the judge level: regardless of how divergent the new
    schema's real facet axes are, comparing against the always-empty
    old_view.facet_axes construction used by _write_latent_schema yields
    facet_distance == 0.0 every time."""
    old_centroid, new_centroid = _same_topic_centroids(cos_target=0.85)
    old_view = LatentSchema(
        centroid=old_centroid,
        facet_axes=np.zeros((0, DIM), dtype=np.float32),  # exactly what _write_latent_schema builds
        facet_strengths=np.zeros((0,), dtype=np.float32),
        member_episode_ids=[],
        central_episode_id=0,
        central_episode_text="old claim",
        mean_ts=0,
        ts_span_s=0,
        confidence=1.0,
        support_count=1,
    )
    for facet_axes in (
        np.eye(4, DIM, dtype=np.float32),  # orthonormal, maximally distinct from any "true" old axes
        -np.eye(4, DIM, dtype=np.float32),  # sign-flipped
        np.random.default_rng(0).standard_normal((4, DIM)).astype(np.float32),
    ):
        new_view = LatentSchema(
            centroid=new_centroid,
            facet_axes=facet_axes,
            facet_strengths=np.ones(4, dtype=np.float32),
            member_episode_ids=[1, 2, 3],
            central_episode_id=1,
            central_episode_text="new claim",
            mean_ts=100,
            ts_span_s=10,
            confidence=0.9,
            support_count=3,
        )
        verdict = consolidator.geometric_judge.judge(old=old_view, new=new_view)
        assert verdict.facet_distance == 0.0
        assert verdict.verdict != "contradicts"
