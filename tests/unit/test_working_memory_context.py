from __future__ import annotations

import os
import tempfile

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine


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


def test_context_brief_suppresses_transcript_and_latent_summaries_by_default() -> None:
    eng, path = _tmp_engine()
    try:
        noisy = eng.schemas.create(
            content_text="User: User asked about meals.\nAssistant: Assistant gave a long meal plan.",
            facets={"schema_class": "latent", "source_kind": "assistant_summary"},
            tags=["meal", "assistant_summary"],
            embedding=None,
            salience=50.0,
            dedupe=False,
        )
        useful = eng.schemas.create(
            content_text="For meal planning, the user prefers vegetarian recipes.",
            facets={
                "schema_class": "preference",
                "scope": "meal planning",
                "topics": ["food", "meal planning"],
                "memory_layer": "profile",
                "stability": "current",
            },
            tags=["food", "meal_planning", "vegetarian"],
            embedding=None,
            salience=1.4,
            dedupe=False,
        )

        brief = eng.context_brief(query="plan vegetarian meals", topics=["food"], limit=5)

        assert [item.schema.id for item in brief.items] == [useful]
        assert noisy not in [item.schema.id for item in brief.items]
        assert brief.suppressed["class_excluded:latent"] == 1
        assert "vegetarian" in brief.rendered
    finally:
        eng.close()
        _cleanup(path)


def test_context_brief_uses_topics_without_requiring_project() -> None:
    eng, path = _tmp_engine()
    try:
        food = eng.schemas.create(
            content_text="For meal planning, the user prefers vegetarian recipes.",
            facets={
                "schema_class": "preference",
                "scope": "meal planning",
                "topics": ["food", "cooking"],
                "memory_layer": "profile",
                "stability": "current",
            },
            tags=["food", "vegetarian"],
            embedding=None,
            salience=1.0,
            dedupe=False,
        )
        eng.schemas.create(
            content_text="For code reviews, the user prefers blunt architectural feedback.",
            facets={
                "schema_class": "preference",
                "scope": "code reviews",
                "topics": ["software engineering"],
                "memory_layer": "profile",
                "stability": "current",
            },
            tags=["code_review", "architecture"],
            embedding=None,
            salience=1.0,
            dedupe=False,
        )

        brief = eng.context_brief(
            query="What should I cook this week?",
            application="chatbot",
            topics=["food", "meal planning"],
            limit=1,
        )

        assert [item.schema.id for item in brief.items] == [food]
        assert brief.items[0].activation >= 0.20
        assert "cue_overlap" in brief.items[0].reason
    finally:
        eng.close()
        _cleanup(path)


def test_context_brief_treats_project_as_one_environmental_cue() -> None:
    eng, path = _tmp_engine()
    try:
        slowave = eng.schemas.create(
            content_text="Slowave should use a working-memory gate before prompt injection.",
            facets={
                "schema_class": "decision",
                "memory_layer": "workspace",
                "stability": "current",
            },
            tags=["memory", "context"],
            scope_id="project:slowave",
            embedding=None,
            salience=1.0,
            dedupe=False,
        )
        eng.schemas.create(
            content_text="Cimmeria semantic context is loaded via load_schema_context().",
            facets={"schema_class": "fact", "memory_layer": "workspace", "stability": "current"},
            tags=["semantic_context"],
            scope_id="project:cimmeria",
            embedding=None,
            salience=1.0,
            dedupe=False,
        )

        brief = eng.context_brief(
            query="continue the memory context work", scope="project:slowave", limit=1
        )

        assert [item.schema.id for item in brief.items] == [slowave]
        assert "scope_match=project:slowave" in brief.items[0].reason
    finally:
        eng.close()
        _cleanup(path)


def test_context_brief_debug_mode_exposes_activation_trace() -> None:
    eng, path = _tmp_engine()
    try:
        noisy = eng.schemas.create(
            content_text="User: User asked about cooking. Assistant: Assistant answered.",
            facets={"schema_class": "latent", "source_kind": "assistant_summary"},
            tags=["cooking"],
            embedding=None,
            salience=1.0,
            dedupe=False,
        )

        brief = eng.context_brief(query="cooking", mode="debug", limit=3)

        assert noisy in [item.schema.id for item in brief.items]
        assert any(trace.schema_id == noisy and trace.admitted for trace in brief.activation_trace)
    finally:
        eng.close()
        _cleanup(path)


def test_explicit_remember_marks_schema_as_injectable_with_memory_layer() -> None:
    eng, path = _tmp_engine()
    try:
        eng.remember(content="The user prefers concise answers.", type="preference")
        schema = eng.schemas.list(limit=1, status="active")[0]

        assert schema.facets["source_kind"] == "explicit_remember"
        assert schema.facets["memory_layer"] == "profile"
        assert schema.facets["injectable"] is True
    finally:
        eng.close()
        _cleanup(path)

# ---------------------------------------------------------------------------
# Geometric (cosine) gate scoring tests
# ---------------------------------------------------------------------------

import numpy as np

from slowave.core.context import GatePolicy, MemoryCue, WorkingMemoryGate


def _make_unit(dim: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-12)


def _stub_schema(
    sid: int,
    text: str,
    embedding: "np.ndarray | None" = None,
    salience: float = 5.0,
    schema_class: str = "preference",
):
    """Build a minimal Schema-like object for gate tests."""
    from slowave.symbolic.schema_store import Schema
    return Schema(
        id=sid,
        prototype_id=None,
        content_text=text,
        facets={"schema_class": schema_class, "memory_layer": "profile",
                "stability": "current", "injectable": True},
        tags=[],
        scope_id=None,
        status="active",
        confidence=1.0,
        salience=salience,
        supporting_episode_ids=[],
        contradicting_episode_ids=[],
        needs_review=False,
        first_formed_ts=1000000,
        last_updated_ts=1000000,
        embedding=embedding,
    )


def test_cosine_term_admits_paraphrased_schema_with_zero_token_overlap() -> None:
    """A schema with no lexical overlap to the cue must be admitted when
    cosine similarity is high (embedding path active)."""
    dim = 8
    # Cue embedding and schema embedding pointing in the same direction.
    cue_emb = _make_unit(dim, seed=1)
    schema_emb = cue_emb.copy()  # perfect cosine = 1.0

    gate = WorkingMemoryGate()
    cue = MemoryCue(query="xyz_unmatched_tokens_only")  # no overlap with schema text
    policy = GatePolicy(min_activation=0.20)

    schema = _stub_schema(
        1,
        text="completely different words about nourishment restrictions",
        embedding=schema_emb,
        salience=1.0,
    )

    state = gate.select([schema], cue=cue, policy=policy, cue_embedding=cue_emb)

    assert len(state.items) == 1, "Schema with perfect cosine must be admitted"
    assert state.items[0].activation >= 0.40
    assert "cosine=" in state.items[0].reason


def test_cosine_term_absent_reverts_to_lexical_weight() -> None:
    """Without cue_embedding the gate behaves identically to the old lexical path."""
    gate = WorkingMemoryGate()
    cue = MemoryCue(query="meal plan vegetarian food")
    policy = GatePolicy(min_activation=0.20)

    schema = _stub_schema(
        2,
        text="The user prefers vegetarian meal planning.",
        embedding=None,  # no embedding stored
        salience=2.0,
    )

    # Without cue_embedding: should still admit via lexical overlap
    state = gate.select([schema], cue=cue, policy=policy, cue_embedding=None)
    assert len(state.items) == 1
    assert "cue_overlap=" in state.items[0].reason
    assert "cosine=" not in state.items[0].reason


def test_cosine_weight_is_reduced_to_complement_when_embedding_present() -> None:
    """When both embeddings are present, lexical overlap weight drops to 0.15
    (not 0.40).  A schema with full token overlap must still clear threshold,
    but its reason string must reflect the lower coefficient via lower activation
    compared to a cosine-only match at the same similarity level."""
    dim = 8
    cue_emb = _make_unit(dim, seed=42)
    # Orthogonal schema embedding: cosine ≈ 0
    orth = _make_unit(dim, seed=99)
    # Make sure it is truly near-orthogonal
    while abs(float(cue_emb.dot(orth))) > 0.15:
        orth = _make_unit(dim, seed=int(orth[0] * 1e6) % 10000 + 1)

    gate = WorkingMemoryGate()
    # Query that overlaps perfectly with schema text
    cue = MemoryCue(query="vegetarian meal planning preference")
    policy = GatePolicy(min_activation=0.05)  # low threshold to observe score values

    schema = _stub_schema(
        3,
        text="The user prefers vegetarian meal planning.",
        embedding=orth,  # orthogonal — cosine ≈ 0
        salience=2.0,
    )

    state_with_emb = gate.select([schema], cue=cue, policy=policy, cue_embedding=cue_emb)
    state_no_emb = gate.select([schema], cue=cue, policy=policy, cue_embedding=None)

    assert len(state_with_emb.items) == 1
    assert len(state_no_emb.items) == 1

    act_with = state_with_emb.items[0].activation
    act_without = state_no_emb.items[0].activation
    # With embedding active but orthogonal: lexical contributes 0.15x instead of 0.40x
    # => activation should be lower when embedding path is active
    assert act_with < act_without, (
        f"Embedding path (cosine≈0) should reduce lexical weight; "
        f"got act_with={act_with:.3f} >= act_without={act_without:.3f}"
    )


def test_schema_without_stored_embedding_degrades_gracefully() -> None:
    """Schemas without stored embeddings must still be scored with lexical path
    even when cue_embedding is provided."""
    dim = 8
    cue_emb = _make_unit(dim, seed=7)

    gate = WorkingMemoryGate()
    cue = MemoryCue(query="nut allergy dietary restriction")
    policy = GatePolicy(min_activation=0.10)

    schema_no_emb = _stub_schema(
        4,
        text="The user has a severe nut allergy.",
        embedding=None,  # old schema, no embedding stored
        salience=3.0,
    )

    state = gate.select([schema_no_emb], cue=cue, policy=policy, cue_embedding=cue_emb)

    # Should admit via lexical overlap ("nut", "allerg" match)
    assert len(state.items) == 1
    assert "cue_overlap=" in state.items[0].reason
    assert "cosine=" not in state.items[0].reason
