from __future__ import annotations

import os
import tempfile

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine


def _tmp_engine() -> tuple[SlowaveEngine, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    cfg = SlowaveConfig(db_path=tmp.name, dim=8, disable_encoder=True, disable_llm=True)
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
            facets={"schema_class": "decision", "memory_layer": "workspace", "stability": "current"},
            tags=["memory", "context"],
            project="slowave",
            embedding=None,
            salience=1.0,
            dedupe=False,
        )
        eng.schemas.create(
            content_text="Cimmeria semantic context is loaded via load_schema_context().",
            facets={"schema_class": "fact", "memory_layer": "workspace", "stability": "current"},
            tags=["semantic_context"],
            project="cimmeria",
            embedding=None,
            salience=1.0,
            dedupe=False,
        )

        brief = eng.context_brief(query="continue the memory context work", project="slowave", limit=1)

        assert [item.schema.id for item in brief.items] == [slowave]
        assert "project=slowave" in brief.items[0].reason
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
