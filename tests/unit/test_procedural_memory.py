from __future__ import annotations

import os
import tempfile

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.core.scope import normalize_scope, scope_kind, scope_value


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


def test_scope_helpers() -> None:
    assert normalize_scope(scope="project:slowave") == "project:slowave"
    assert normalize_scope(scope="domain:cooking") == "domain:cooking"
    assert normalize_scope() is None
    assert scope_kind("project:slowave") == "project"
    assert scope_value("project:slowave") == "slowave"
    assert scope_kind("household") == "generic"


def test_procedure_retrieval_and_feedback() -> None:
    eng, path = _tmp_engine()
    try:
        pid = eng.remember_procedure(
            scope="project:slowave",
            goal="documentation_positioning",
            task_type="writing",
            situation={"domain": "software", "medium": "README"},
            requirements=["copy-paste Markdown", "mention local-first"],
            trigger_pattern=["README", "docs", "positioning", "local-first"],
            procedure_steps=[
                "Start from the coding assistant memory wedge.",
                "Mention local-first and no remote LLM in the core loop.",
                "Return copy-paste Markdown.",
            ],
            confidence=0.8,
            status="active",
        )

        matches = eng.retrieve_procedures(
            scope="project:slowave",
            goal="documentation_positioning",
            task_type="writing",
            situation={"domain": "software", "medium": "README"},
            requirements=["copy-paste Markdown", "mention local-first"],
            query="write README positioning docs",
            mode="default",
        )

        assert matches
        assert matches[0].procedure.id == pid
        assert matches[0].score >= eng.cfg.procedural.min_procedure_score

        before = eng.procedures.get(pid).confidence
        result = eng.retrieval_feedback(
            retrieval_id="ctx_test_proc",
            retrieval_type="context",
            feedback="useful",
            outcome="success",
            scope_id="project:slowave",
            goal="documentation_positioning",
            task_type="writing",
            situation={"domain": "software", "medium": "README"},
            requirements=["copy-paste Markdown", "mention local-first"],
            used_procedure_ids=[f"proc_{pid}"],
        )
        after = eng.procedures.get(pid).confidence

        assert result["applied"]["procedures"][0]["id"] == f"proc_{pid}"
        assert after > before
        assert eng.procedures.get(pid).success_count == 1
    finally:
        eng.close()
        _cleanup(path)


def test_procedure_can_transfer_across_related_scopes() -> None:
    eng, path = _tmp_engine()
    try:
        pid = eng.remember_procedure(
            scope="project:slowave",
            goal="oss_documentation_positioning",
            task_type="writing",
            situation={"domain": "software", "medium": "README"},
            requirements=["avoid overclaiming"],
            trigger_pattern=["README", "OSS", "positioning"],
            procedure_steps=["Start from user pain.", "State differentiator plainly."],
            confidence=0.95,
            status="active",
        )

        # Promote to stage 1 to enable cross-scope transfer
        eng.procedures.set_generalization_stage(pid, 1)

        matches = eng.retrieve_procedures(
            scope="project:other-tool",
            goal="oss_documentation_positioning",
            task_type="writing",
            situation={"domain": "software", "medium": "README"},
            requirements=["avoid overclaiming"],
            query="write OSS README positioning",
            mode="default",
        )

        assert matches
        assert matches[0].procedure.id == pid
        # Stage 1 procedures with same scope kind get cfg.stage1_cross_affinity
        assert matches[0].components["scope_affinity"] == eng.cfg.procedural.stage1_cross_affinity
    finally:
        eng.close()
        _cleanup(path)


def test_repeated_successful_feedback_promotes_candidate_procedure() -> None:
    eng, path = _tmp_engine()
    try:
        for i in range(3):
            rid = f"ctx_success_{i}"
            eng.record_retrieval(
                retrieval_id=rid,
                retrieval_type="context",
                scope_id="project:slowave",
                scope_kind="project",
                query="write README positioning",
                goal="documentation_positioning",
                task_type="writing",
                situation={"domain": "software", "medium": "README"},
                requirements=["copy-paste Markdown", "mention local-first"],
                response={"memory_ids": ["sch_1", "sch_2"], "schemas": []},
            )
            eng.retrieval_feedback(
                retrieval_id=rid,
                retrieval_type="context",
                feedback="useful",
                outcome="success",
                scope_id="project:slowave",
                goal="documentation_positioning",
                task_type="writing",
                situation={"domain": "software", "medium": "README"},
                requirements=["copy-paste Markdown", "mention local-first"],
                used_memory_ids=["sch_1", "sch_2"],
            )

        result = eng.promote_procedure_candidates_from_feedback()

        assert result["created"]
        proc = eng.procedures.get(int(result["created"][0]["procedure_id"].removeprefix("proc_")))
        assert proc.status == "candidate"
        assert proc.goal == "documentation_positioning"
        assert proc.success_count == 3
        assert any("sch_1" in step for step in proc.procedure_steps)
    finally:
        eng.close()
        _cleanup(path)
