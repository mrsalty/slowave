from __future__ import annotations

import json
from typing import Any

import numpy as np


def to_f32(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        return x
    if x.ndim == 2:
        return x
    raise ValueError(f"Expected 1D or 2D array, got shape {x.shape}")


def pack_f32(vec: np.ndarray) -> bytes:
    vec = to_f32(vec)
    if vec.ndim != 1:
        raise ValueError("pack_f32 expects a 1D vector")
    return vec.tobytes(order="C")


def unpack_f32(blob: bytes, dim: int) -> np.ndarray:
    vec = np.frombuffer(blob, dtype=np.float32)
    if vec.size != dim:
        raise ValueError(f"Blob dim mismatch: expected {dim}, got {vec.size}")
    return vec


def dumps_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def loads_json(s: str) -> dict[str, Any]:
    obj = json.loads(s)
    if not isinstance(obj, dict):
        raise ValueError("metadata_json must decode to dict")
    return obj
