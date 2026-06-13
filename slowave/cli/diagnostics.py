"""Diagnostic and health check utilities."""
from __future__ import annotations
import os
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from slowave.core.paths import default_db_path
from slowave.cli.output import Status, CheckResult

@dataclass
class RuntimeInfo:
    python_version: str
    python_executable: str
    db_path: str
    config_path: str
    slowave_dir: str
    version: str

def get_runtime_info(version: str) -> RuntimeInfo:
    slowave_dir = str(Path(default_db_path()).parent)
    return RuntimeInfo(
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        python_executable=sys.executable,
        db_path=str(default_db_path()),
        config_path=str(Path(slowave_dir) / "config.toml"),
        slowave_dir=slowave_dir,
        version=version,
    )

def check_python() -> CheckResult:
    vi = sys.version_info
    py_ok = (vi.major == 3) and (vi.minor >= 10)
    return CheckResult(
        label=f"Python {vi.major}.{vi.minor}.{vi.micro}",
        status=Status.OK if py_ok else Status.FAIL,
        detail="" if py_ok else "Slowave requires Python 3.10+",
    )

def check_faiss() -> CheckResult:
    try:
        import faiss
        return CheckResult(label=f"FAISS {faiss.__version__}", status=Status.OK)
    except Exception as e:
        return CheckResult(
            label="FAISS",
            status=Status.FAIL,
            detail=str(e)[:100],
            remediation="pip install faiss-cpu",
        )

def check_onnxruntime() -> CheckResult:
    try:
        import onnxruntime as _ort
        return CheckResult(label=f"ONNX Runtime {_ort.__version__}", status=Status.OK)
    except Exception as e:
        return CheckResult(
            label="ONNX Runtime",
            status=Status.FAIL,
            detail=str(e)[:100],
            remediation="pip install onnxruntime",
        )

def check_embedding_backend() -> CheckResult:
    try:
        old_warn = os.environ.get("TRANSFORMERS_NO_ADVISORY_WARNINGS")
        os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
        try:
            from slowave.symbolic.encoder import TextEncoder
            enc = TextEncoder()
            v = enc.encode("test")
            dim = v.shape[0]
            return CheckResult(label=f"Embedding backend (dim={dim})", status=Status.OK)
        finally:
            if old_warn is not None:
                os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = old_warn
            else:
                os.environ.pop("TRANSFORMERS_NO_ADVISORY_WARNINGS", None)
    except Exception as e:
        return CheckResult(
            label="Embedding backend",
            status=Status.FAIL,
            detail=str(e)[:100],
            remediation="check FAISS and ONNX Runtime installation",
        )

def check_sqlite_write() -> CheckResult:
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            con = sqlite3.connect(tmp_path)
            con.execute("CREATE TABLE t (x INTEGER)")
            con.execute("INSERT INTO t VALUES (1)")
            con.commit()
            con.close()
            return CheckResult(label="SQLite write access", status=Status.OK)
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        return CheckResult(
            label="SQLite write access",
            status=Status.FAIL,
            detail=str(e)[:100],
        )

def check_mcp_server() -> CheckResult:
    import shutil
    try:
        mcp_path = shutil.which("slowave-mcp")
        if mcp_path:
            return CheckResult(label="slowave-mcp", status=Status.OK, detail=mcp_path)
        else:
            return CheckResult(
                label="slowave-mcp",
                status=Status.FAIL,
                remediation="run: pip install slowave (or pipx install slowave)",
            )
    except Exception as e:
        return CheckResult(label="slowave-mcp", status=Status.FAIL, detail=str(e)[:100])
