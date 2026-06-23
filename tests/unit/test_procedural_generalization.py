"""Level-1 tests for procedural memory generalization (v4 §5)."""

from __future__ import annotations

import ast
import os
import tempfile

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine


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


def test_scope_affinity_stage0_blocked() -> None:
    """Stage 0 procedure: cross-scope affinity == 0.0 (scope-locked)."""
    eng, path = _tmp_engine()
    try:
        # Create a stage 0 procedure (default)
        proc_id = eng.remember_procedure(
            goal="test",
            scope="project:scope1",
            procedure_steps=["step1"],
            confidence=0.8,
            status="active",
        )

        # Score it from a different scope
        proc = eng.procedures.get(proc_id)
        affinity = eng.procedures._scope_affinity("project:scope2", proc)

        # Stage 0 procedures have zero cross-scope affinity
        assert affinity == 0.0, f"Expected 0.0, got {affinity}"

    finally:
        eng.close()
        _cleanup(path)


def test_scope_affinity_stage3_fires() -> None:
    """Stage 3 procedure: cross-scope affinity == 1.0 (universal)."""
    eng, path = _tmp_engine()
    try:
        # Create a stage 0 procedure
        proc_id = eng.remember_procedure(
            goal="test",
            scope="project:scope1",
            procedure_steps=["step1"],
            confidence=0.8,
            status="active",
        )

        # Manually promote it to stage 3
        eng.procedures.set_generalization_stage(proc_id, 3)
        
        # Score it from a different scope
        proc = eng.procedures.get(proc_id)
        affinity = eng.procedures._scope_affinity("project:scope2", proc)

        # Stage 3 procedures have universal (1.0) cross-scope affinity
        assert affinity == 1.0, f"Expected 1.0, got {affinity}"

    finally:
        eng.close()
        _cleanup(path)


def test_set_generalization_stage() -> None:
    """Test that set_generalization_stage updates the DB correctly."""
    eng, path = _tmp_engine()
    try:
        proc_id = eng.remember_procedure(
            goal="test",
            scope="project:scope1",
            procedure_steps=["step1"],
            confidence=0.8,
            status="active",
        )

        # Initially stage 0
        proc = eng.procedures.get(proc_id)
        assert proc.generalization_stage == 0

        # Set to stage 1
        eng.procedures.set_generalization_stage(proc_id, 1)
        
        # Verify DB was updated
        proc = eng.procedures.get(proc_id)
        assert proc.generalization_stage == 1

        # Query directly
        conn = eng.db.connect()
        row = conn.execute(
            "SELECT generalization_stage FROM procedural_memories WHERE id = ?",
            (proc_id,),
        ).fetchone()
        assert int(row["generalization_stage"]) == 1

    finally:
        eng.close()
        _cleanup(path)


def test_encode_never_in_procedural() -> None:
    """Verify slowave/core/procedural.py never calls encode() or imports numpy."""
    procedural_path = "/Users/matteo/repos/personal/slowave/slowave/core/procedural.py"
    
    with open(procedural_path) as f:
        tree = ast.parse(f.read())
    
    # Check for encode() calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "encode":
                    raise AssertionError(f"Found encode() call in {procedural_path}")
    
    # Check for numpy imports
    source = open(procedural_path).read()
    assert "import numpy" not in source, "Found 'import numpy' in " + procedural_path
    assert "from numpy" not in source, "Found 'from numpy' in " + procedural_path
