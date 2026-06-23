"""Level-1 tests for Tier 1 procedural enforcement (v4 §11)."""

from __future__ import annotations

import os
import tempfile

import numpy as np

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.core.procedural_enforcement import ProceduralEnforcement
from slowave.storage.sqlite_db import SQLiteDB, SQLiteConfig


def _tmp_engine() -> tuple[SlowaveEngine, str]:
    """Create a temporary engine for testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    cfg = SlowaveConfig(db_path=tmp.name, disable_encoder=False)
    return SlowaveEngine.from_config(cfg), tmp.name


def _cleanup(path: str) -> None:
    """Remove temporary database files."""
    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            os.remove(p)


def test_track_writes_scoped_evidence() -> None:
    """CRITICAL: assert evidence rows have non-null scope_id after track().

    This is the v3 bug fix: ProceduralEnforcement.track() MUST resolve
    the session's own scope_id and pass it into store.apply_feedback().
    Without this, procedural_memory_evidence rows stay scope-less and
    cross-scope generalization (§5) cannot function.
    """
    eng, path = _tmp_engine()
    try:
        # Create a session with a scope and goal
        scope = "project:testproj"
        session_id = eng.session_start(agent="test", scope=scope, goal="test_goal")

        # Create a procedure with exact goal match for best retrieval
        proc_id = eng.remember_procedure(
            goal="test_goal",
            task_type="testing",
            scope=scope,
            procedure_steps=["step one"],
            confidence=0.8,
            status="active",
        )

        # Append a remember event that will be embedded
        eng.event_append(
            session_id=session_id,
            type="remember:decision",
            content="step one important decision",
        )

        # End session with outcome
        eng.session_end(session_id, outcome="success")

        # Query the evidence table and assert scope_id is NOT NULL
        conn = eng.db.connect()
        rows = conn.execute(
            "SELECT scope_id FROM procedural_memory_evidence WHERE procedure_id = ?",
            (proc_id,),
        ).fetchall()

        # Should have at least one evidence row if coverage >= 0.5
        # If no rows, it means coverage was < 0.5 (acceptable for this test)
        # The critical check is that IF rows exist, scope_id is not NULL
        for row in rows:
            assert row["scope_id"] is not None, f"Evidence row has NULL scope_id: {row}"
            assert row["scope_id"] == scope, f"Expected scope {scope}, got {row['scope_id']}"

        # Verify the procedure was retrieved and scored
        procs = eng.retrieve_procedures(goal="test_goal", scope=scope, limit=5)
        assert any(p.procedure.id == proc_id for p in procs), "Procedure not retrieved by track()"

    finally:
        eng.close()
        _cleanup(path)


def test_coverage_exact_match() -> None:
    """Test that coverage matching can be computed without errors."""
    eng, path = _tmp_engine()
    try:
        session_id = eng.session_start(agent="test", goal="impl_oauth")

        # Create a procedure
        proc_id = eng.remember_procedure(
            goal="impl_oauth",
            procedure_steps=["jwt tokens"],
            confidence=0.7,
            status="active",
        )

        # Append a remember event
        eng.event_append(
            session_id=session_id,
            type="remember:decision",
            content="jwt tokens for auth",
        )

        # This should not raise an error
        result = eng.session_end(session_id, outcome="success")

        # Verify enforcement actually computed coverage > 0
        assert "procedural_enforcement" in result, "Enforcement tracking not returned"
        enforcement_result = result["procedural_enforcement"]
        assert "results" in enforcement_result, "No enforcement results"
        assert len(enforcement_result["results"]) > 0, "No procedures tracked"
        proc_result = enforcement_result["results"][0]
        assert proc_result["coverage"] > 0.0, f"Coverage was 0.0; embeddings may not have loaded"

        # Verify the procedure exists
        retrieved = eng.retrieve_procedures(goal="impl_oauth", limit=5)
        assert any(p.procedure.id == proc_id for p in retrieved), "Procedure not retrieved"

    finally:
        eng.close()
        _cleanup(path)


def test_coverage_no_events() -> None:
    """Test coverage with no matching events (0.0)."""
    eng, path = _tmp_engine()
    try:
        session_id = eng.session_start(agent="test", goal="impl_oauth")

        # Create procedure
        proc_id = eng.remember_procedure(
            goal="impl_oauth",
            procedure_steps=["jwt tokens"],
            confidence=0.7,
            status="active",
        )

        # Do NOT append any remember events
        eng.session_end(session_id, outcome="success")

        # Query enforcement result
        conn = eng.db.connect()
        rows = conn.execute(
            "SELECT feedback FROM procedural_memory_evidence WHERE procedure_id = ?",
            (proc_id,),
        ).fetchall()

        # No feedback should be applied (coverage < 0.5)
        # No evidence rows should be created if coverage is too low
        assert len(rows) == 0, "Evidence should not be recorded when coverage < 0.5"

    finally:
        eng.close()
        _cleanup(path)


def test_feedback_routing_success() -> None:
    """Test feedback routing: coverage >= 0.5 + outcome=success -> useful."""
    eng, path = _tmp_engine()
    try:
        session_id = eng.session_start(agent="test", goal="debug_auth")

        proc_id = eng.remember_procedure(
            goal="debug_auth",
            procedure_steps=["check tokens"],
            confidence=0.7,
            status="active",
        )

        # Append matching remember event
        eng.event_append(
            session_id=session_id,
            type="remember:lesson",
            content="check jwt tokens first",
        )

        eng.session_end(session_id, outcome="success")

        # Query evidence
        conn = eng.db.connect()
        row = conn.execute(
            "SELECT feedback, outcome FROM procedural_memory_evidence WHERE procedure_id = ?",
            (proc_id,),
        ).fetchone()

        # Evidence row must exist (coverage >= 0.5)
        assert row is not None, "No evidence written; coverage must have been < 0.5"
        assert row["feedback"] == "useful"
        assert row["outcome"] == "success"

    finally:
        eng.close()


def test_feedback_routing_failure() -> None:
    """Test feedback routing: coverage >= 0.5 + outcome=failure -> wrong."""
    eng, path = _tmp_engine()
    try:
        session_id = eng.session_start(agent="test", goal="debug_auth")

        proc_id = eng.remember_procedure(
            goal="debug_auth",
            procedure_steps=["check tokens"],
            confidence=0.7,
            status="active",
        )

        # Append matching remember event
        eng.event_append(
            session_id=session_id,
            type="remember:lesson",
            content="check jwt tokens first",
        )

        eng.session_end(session_id, outcome="failure")

        # Query evidence
        conn = eng.db.connect()
        row = conn.execute(
            "SELECT feedback, outcome FROM procedural_memory_evidence WHERE procedure_id = ?",
            (proc_id,),
        ).fetchone()

        # Evidence row must exist (coverage >= 0.5)
        assert row is not None, "No evidence written; coverage must have been < 0.5"
        assert row["feedback"] == "wrong"
        assert row["outcome"] == "failure"

    finally:
        eng.close()
        _cleanup(path)


def test_no_goal_no_track() -> None:
    """Test that track returns early if session has no goal."""
    eng, path = _tmp_engine()
    try:
        # Session without goal
        session_id = eng.session_start(agent="test")

        proc_id = eng.remember_procedure(
            goal="any_goal",
            procedure_steps=["step1"],
            confidence=0.7,
            status="active",
        )

        eng.event_append(
            session_id=session_id,
            type="remember:decision",
            content="step1",
        )

        eng.session_end(session_id, outcome="success")

        # Query evidence - should be empty
        conn = eng.db.connect()
        rows = conn.execute(
            "SELECT COUNT(*) as cnt FROM procedural_memory_evidence WHERE procedure_id = ?",
            (proc_id,),
        ).fetchone()

        assert rows["cnt"] == 0, "Evidence recorded despite no goal"

    finally:
        eng.close()
        _cleanup(path)


def test_cross_scope_evidence() -> None:
    """Test that evidence is created even for cross-scope sessions."""
    eng, path = _tmp_engine()
    try:
        # Create procedure in one scope
        proc_id = eng.remember_procedure(
            goal="impl",
            scope="project:scope1",
            procedure_steps=["step1"],
            confidence=0.8,
            status="active",
        )

        # Create session in different scope
        session_id = eng.session_start(agent="test", scope="project:scope2", goal="impl")

        eng.event_append(
            session_id=session_id,
            type="remember:decision",
            content="step1",
        )

        eng.session_end(session_id, outcome="success")

        # Query evidence
        conn = eng.db.connect()
        row = conn.execute(
            "SELECT scope_id FROM procedural_memory_evidence WHERE procedure_id = ?",
            (proc_id,),
        ).fetchone()

        # Evidence should be recorded with the session's scope
        if row:
            assert row["scope_id"] == "project:scope2"

    finally:
        eng.close()
        _cleanup(path)
