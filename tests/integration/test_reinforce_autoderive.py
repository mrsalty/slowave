"""Integration test: reinforce auto-derives goal/task_type from context_recall_events.

Validates Step 5 (feedback auto-derive) and Step 6 acceptance criteria:
- Record context with explicit goal=g1, task_type=tt1, scope_id=s1
- Call retrieval_feedback with minimal signature (no goal/task_type/scope_id)
- Assert context_feedback_events row carries goal='g1' and task_type='tt1'
- Also test unknown retrieval_id: writes feedback with NULLs, does not crash
"""
from __future__ import annotations

import os
import tempfile
import uuid

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


class TestReinforceAutoderive:
    def test_goal_and_task_type_auto_derived(self) -> None:
        eng, path = _tmp_engine()
        try:
            ctx_id = f"ctx_{uuid.uuid4().hex[:12]}"

            # Record context snapshot with explicit metadata
            eng.record_retrieval(
                retrieval_id=ctx_id,
                retrieval_type="context",
                scope_id="project:test",
                goal="implement test feature",
                task_type="coding",
                situation={"env": "test"},
                requirements=["req1"],
            )

            # Call feedback with only required fields — goal/task_type/scope auto-derived
            result = eng.retrieval_feedback(
                retrieval_id=ctx_id,
                feedback="useful",
                outcome="success",
            )
            assert result.get("feedback") == "useful"
            assert result.get("outcome") == "success"

            conn = eng.db.connect()
            row = conn.execute(
                "SELECT goal, task_type, scope_id FROM context_feedback_events WHERE context_id = ?",
                (ctx_id,),
            ).fetchone()
            assert row is not None
            assert row["goal"] == "implement test feature", f"expected auto-derived goal, got {row['goal']}"
            assert row["task_type"] == "coding", f"expected auto-derived task_type, got {row['task_type']}"
            assert row["scope_id"] == "project:test"
        finally:
            eng.close()
            _cleanup(path)

    def test_unknown_retrieval_id_does_not_crash(self) -> None:
        eng, path = _tmp_engine()
        try:
            unknown_id = f"ctx_{uuid.uuid4().hex[:12]}"
            result = eng.retrieval_feedback(
                retrieval_id=unknown_id,
                feedback="missing",
                outcome="unknown",
            )
            # Must not crash; fallback inserts row with NULLs
            assert result.get("feedback") == "missing"

            conn = eng.db.connect()
            row = conn.execute(
                "SELECT goal, task_type FROM context_feedback_events WHERE context_id = ?",
                (unknown_id,),
            ).fetchone()
            assert row is not None
            assert row["goal"] is None
            assert row["task_type"] is None
        finally:
            eng.close()
            _cleanup(path)
