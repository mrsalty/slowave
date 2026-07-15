"""Tests for relation-graph spreading activation (2026-07-14): schema_relations
edges from an admitted schema can surface a neighbor that wasn't a direct hit,
in both context_brief() (WorkingMemoryGate.expand_via_relations) and
recall() (RetrievalService, via the same spread_relation_activation core).
"""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

from slowave.core.config import SlowaveConfig
from slowave.core.context import spread_relation_activation
from slowave.core.engine import SlowaveEngine


class _StubEncoder:
    """Deterministic hash-based encoder so recall() works without model weights."""

    def __init__(self, dim: int = 8):
        self._dim = dim

    def encode(self, text: str) -> np.ndarray:
        seed = int(abs(hash(text)) % (2**31))
        v = np.random.default_rng(seed).standard_normal(self._dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-12)


# ---------------------------------------------------------------------------
# spread_relation_activation -- pure algorithm, no DB
# ---------------------------------------------------------------------------


def test_single_hop_propagation_above_threshold():
    def fetch_relations(schema_id):
        if schema_id == 1:
            return [(2, "part_of", 0.9)]
        return []

    winners = spread_relation_activation(
        {1: 0.8}, fetch_relations=fetch_relations, min_activation=0.20
    )
    assert 2 in winners
    activation, via = winners[2]
    assert activation == pytest.approx(0.8 * 0.9 * 0.6, rel=1e-6)
    assert via == {"part_of"}


def test_below_threshold_neighbor_is_dropped():
    def fetch_relations(schema_id):
        return [(2, "part_of", 0.3)] if schema_id == 1 else []

    winners = spread_relation_activation(
        {1: 0.3}, fetch_relations=fetch_relations, min_activation=0.20
    )
    assert 2 not in winners


def test_convergent_paths_sum_before_threshold():
    """Neither seed alone clears the bar via a single 0.4-confidence edge, but
    two seeds both linking to the same neighbor sum their contributions."""

    def fetch_relations(schema_id):
        if schema_id in (1, 2):
            return [(99, "part_of", 0.6)]
        return []

    single = spread_relation_activation(
        {1: 0.5}, fetch_relations=fetch_relations, min_activation=0.35
    )
    assert 99 not in single  # 0.5*0.6*0.6 = 0.18, below 0.35

    converged = spread_relation_activation(
        {1: 0.5, 2: 0.5}, fetch_relations=fetch_relations, min_activation=0.35
    )
    assert 99 in converged
    activation, via = converged[99]
    assert activation == pytest.approx(2 * 0.5 * 0.6 * 0.6, rel=1e-6)
    assert via == {"part_of"}


def test_admitted_schemas_never_reappear_as_winners():
    def fetch_relations(schema_id):
        return [(1, "part_of", 1.0)] if schema_id == 2 else [(2, "part_of", 1.0)]

    winners = spread_relation_activation(
        {1: 1.0, 2: 1.0}, fetch_relations=fetch_relations, min_activation=0.01
    )
    assert 1 not in winners
    assert 2 not in winners


def test_cycle_is_handled_without_infinite_loop():
    """A <-> B <-> C cycle must terminate (visited set) and not double-count
    C's contribution once it's already been reached."""

    def fetch_relations(schema_id):
        edges = {
            1: [(2, "part_of", 1.0)],
            2: [(1, "part_of", 1.0), (3, "part_of", 1.0)],
            3: [(2, "part_of", 1.0), (1, "part_of", 1.0)],
        }
        return edges.get(schema_id, [])

    winners = spread_relation_activation(
        {1: 1.0}, fetch_relations=fetch_relations, min_activation=0.01
    )
    # Must terminate and return a finite result; 1 (seed) never a winner.
    assert 1 not in winners
    assert 2 in winners or 3 in winners


def test_max_extra_cap_limits_winner_count():
    def fetch_relations(schema_id):
        if schema_id == 1:
            return [(i, "part_of", 0.99) for i in range(2, 10)]
        return []

    winners = spread_relation_activation(
        {1: 1.0}, fetch_relations=fetch_relations, min_activation=0.01
    )
    assert len(winners) <= 3  # _GRAPH_MAX_EXTRA


def test_no_seeds_returns_empty():
    assert spread_relation_activation({}, fetch_relations=lambda i: [], min_activation=0.0) == {}


# ---------------------------------------------------------------------------
# Integration: context_brief() and recall() surface graph-linked neighbors
# ---------------------------------------------------------------------------


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


def test_context_brief_surfaces_part_of_neighbor_via_graph_expansion():
    eng, path = _tmp_engine()
    try:
        parent_id = eng.schemas.create(
            content_text="For meal planning, the user prefers vegetarian recipes.",
            facets={
                "schema_class": "preference",
                "topics": ["food", "meal planning"],
                "memory_layer": "profile",
                "stability": "current",
            },
            tags=["food", "meal_planning", "vegetarian"],
            embedding=None,
            salience=5.0,
            dedupe=False,
        )
        child_id = eng.schemas.create(
            content_text="The kitchen restocks olive oil every two weeks.",
            facets={"schema_class": "fact"},
            tags=["unrelated_tag"],
            embedding=None,
            salience=0.01,
            scope_id="proj:other",  # non-None so it doesn't get the scope-less "global" bonus
            dedupe=False,
        )
        eng.schemas.add_relation(
            src_schema_id=child_id, dst_schema_id=parent_id, relation="part_of", confidence=0.95
        )

        brief = eng.context_brief(query="plan vegetarian meals", topics=["food"], limit=5)
        ids = [item.schema.id for item in brief.items]

        assert parent_id in ids, "direct hit must still be admitted"
        assert child_id in ids, "part_of neighbor must surface via graph expansion"
        child_item = next(item for item in brief.items if item.schema.id == child_id)
        assert child_item.peripheral is True
        assert child_item.reason.startswith("graph:")
    finally:
        eng.close()
        _cleanup(path)


def test_context_brief_blocks_cross_scope_graph_neighbor_below_stage():
    """schema_relations is not a scope boundary -- backfill_part_of_edges
    explicitly allows cross-scope part_of pairs -- so a graph-propagated
    neighbor from a different scope must still respect cross-scope isolation
    (generalization_stage >= 2) the same way direct candidates do."""
    eng, path = _tmp_engine()
    try:
        parent_id = eng.schemas.create(
            content_text="For meal planning, the user prefers vegetarian recipes.",
            facets={
                "schema_class": "preference",
                "topics": ["food", "meal planning"],
                "memory_layer": "profile",
                "stability": "current",
            },
            tags=["food", "meal_planning", "vegetarian"],
            embedding=None,
            salience=5.0,
            scope_id="project:alpha",
            dedupe=False,
        )
        child_id = eng.schemas.create(
            content_text="The kitchen restocks olive oil every two weeks.",
            facets={"schema_class": "fact"},
            tags=["unrelated_tag"],
            embedding=None,
            salience=0.01,
            scope_id="project:beta",  # different scope, stage 0 (default)
            dedupe=False,
        )
        eng.schemas.add_relation(
            src_schema_id=child_id, dst_schema_id=parent_id, relation="part_of", confidence=0.95
        )

        brief = eng.context_brief(
            query="plan vegetarian meals", topics=["food"], scope="project:alpha", limit=5
        )
        ids = [item.schema.id for item in brief.items]
        assert parent_id in ids
        assert child_id not in ids, "stage-0 cross-scope neighbor must not leak via graph expansion"
    finally:
        eng.close()
        _cleanup(path)


def test_recall_surfaces_part_of_neighbor_via_graph_expansion():
    eng, path = _tmp_engine()
    eng.encoder = _StubEncoder(dim=8)
    try:
        parent_id = eng.schemas.create(
            content_text="For meal planning, the user prefers vegetarian recipes.",
            facets={"schema_class": "preference"},
            tags=["food", "meal_planning", "vegetarian"],
            embedding=None,
            salience=5.0,
            dedupe=False,
        )
        child_id = eng.schemas.create(
            content_text="Specifically, the user avoids mushrooms in vegetarian dishes.",
            facets={"schema_class": "fact"},
            tags=["unrelated_tag"],
            embedding=None,
            salience=0.01,
            dedupe=False,
        )
        eng.schemas.add_relation(
            src_schema_id=child_id, dst_schema_id=parent_id, relation="part_of", confidence=0.95
        )

        result = eng.recall("vegetarian meal planning recipes", top_k=5)
        ids = [s.id for s in result.schemas]
        related_ids = [s.id for s in result.related_schemas]

        assert parent_id in ids, "direct hit must still be a top_k result"
        assert child_id not in ids, (
            "graph-propagated neighbors must NOT be merged into schemas -- "
            "every benchmark script assumes len(schemas) <= top_k"
        )
        assert child_id in related_ids, "part_of neighbor must surface via related_schemas"
        assert result.schema_activations[child_id] > 0
    finally:
        eng.close()
        _cleanup(path)


def test_recall_schemas_never_exceeds_top_k_even_with_graph_winners():
    """Regression guard for the exact bug this fix addresses: benchmark
    scripts (retrieval_metrics.compute_recall_at_k_and_mrr, dmr_original_eval,
    etc.) concatenate result.schemas assuming len() <= top_k."""
    eng, path = _tmp_engine()
    eng.encoder = _StubEncoder(dim=8)
    try:
        parent_id = eng.schemas.create(
            content_text="For meal planning, the user prefers vegetarian recipes.",
            facets={"schema_class": "preference"},
            tags=["food", "meal_planning", "vegetarian"],
            embedding=None,
            salience=5.0,
            dedupe=False,
        )
        child_id = eng.schemas.create(
            content_text="Specifically, the user avoids mushrooms in vegetarian dishes.",
            facets={"schema_class": "fact"},
            tags=["unrelated_tag"],
            embedding=None,
            salience=0.01,
            dedupe=False,
        )
        eng.schemas.add_relation(
            src_schema_id=child_id, dst_schema_id=parent_id, relation="part_of", confidence=0.95
        )

        top_k = 1
        result = eng.recall("vegetarian meal planning recipes", top_k=top_k)
        assert len(result.schemas) <= top_k
    finally:
        eng.close()
        _cleanup(path)


def test_recall_blocks_cross_scope_graph_neighbor_below_stage():
    """Same cross-scope isolation guarantee as context_brief: schema_relations
    is not a scope boundary, so a graph-propagated neighbor from a different,
    stage-0 scope must not leak into related_schemas either."""
    eng, path = _tmp_engine()
    eng.encoder = _StubEncoder(dim=8)
    try:
        parent_id = eng.schemas.create(
            content_text="For meal planning, the user prefers vegetarian recipes.",
            facets={"schema_class": "preference"},
            tags=["food", "meal_planning", "vegetarian"],
            embedding=None,
            salience=5.0,
            scope_id="project:alpha",
            dedupe=False,
        )
        child_id = eng.schemas.create(
            content_text="Specifically, the user avoids mushrooms in vegetarian dishes.",
            facets={"schema_class": "fact"},
            tags=["unrelated_tag"],
            embedding=None,
            salience=0.01,
            scope_id="project:beta",  # different scope, stage 0 (default)
            dedupe=False,
        )
        eng.schemas.add_relation(
            src_schema_id=child_id, dst_schema_id=parent_id, relation="part_of", confidence=0.95
        )

        result = eng.recall("vegetarian meal planning recipes", top_k=5, scope="project:alpha")
        related_ids = [s.id for s in result.related_schemas]
        assert (
            child_id not in related_ids
        ), "stage-0 cross-scope neighbor must not leak into related_schemas"
    finally:
        eng.close()
        _cleanup(path)
