"""Stage 7 — intrinsic temporal context.

Brain analogue: hippocampal time cells and the lateral entorhinal
cortex's temporal context cells. Every encoded memory carries its
temporal context as an intrinsic property of the trace — not as a
separate metadata field looked up later. Recalling a memory recalls
its temporal context as part of the same activation pattern.

We approximate the brain's continuous temporal context vector with a
small **multi-scale sinusoidal embedding**. At each scale (minute,
hour, day, week, month, year, decade) we emit a (sin, cos) pair of the
timestamp's phase at that scale. The result is a deterministic,
zero-training, low-dimensional fingerprint of a moment in time.

Two timestamps that are close on *any* scale have a positive cosine
similarity in this space; two timestamps separated by all scales (e.g.
years apart and at very different times of day) have a similarity near
zero. The biological correspondence is rough but the architectural
intent is faithful: temporal proximity is a coordinate that
co-activates with semantic content, not a query filter.

Usage in retrieval (Stage 7 wiring):

    cos_total = cos(semantic_q, semantic_m)
              + α_temporal * cos(temporal_q, temporal_m)
              + α_salience * salience_m

The α coefficients are picked from the architectural argument
(temporal context is a real but secondary signal), not tuned to a
benchmark.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np


# Scales chosen to span the relevant brain-time bands:
#   minute  - intra-conversation drift
#   hour    - within-day position (morning/evening)
#   day     - day-of-week pattern
#   week    - recent vs older this month
#   month   - seasonal drift
#   year    - long-horizon
#   decade  - lifetime epoch
#
# Each scale contributes a (sin, cos) pair, so the resulting embedding
# is 2 * len(SCALES_SECONDS) dimensional. With 7 scales that's a
# 14-dimensional temporal vector — cheap to compute and store.
SCALES_SECONDS: tuple[int, ...] = (
    60,                  # minute
    60 * 60,             # hour
    24 * 60 * 60,        # day
    7 * 24 * 60 * 60,    # week
    30 * 24 * 60 * 60,   # month (approx)
    365 * 24 * 60 * 60,  # year
    10 * 365 * 24 * 60 * 60,  # decade
)


@dataclass(frozen=True)
class TemporalContextConfig:
    # Scales to use. Defaults to the 7-band scheme above.
    scales_seconds: tuple[int, ...] = SCALES_SECONDS


class TemporalContext:
    """Build deterministic sinusoidal temporal-context vectors.

    Pure function wrapper. Holds no state; instances are cheap to
    create and re-use is purely for caching the scales tuple.
    """

    def __init__(self, cfg: TemporalContextConfig | None = None):
        self.cfg = cfg or TemporalContextConfig()
        self._scales = np.asarray(self.cfg.scales_seconds, dtype=np.float64)
        # Output dimension is 2 per scale (sin + cos).
        self.dim = int(2 * len(self._scales))

    def encode(self, ts_seconds: int | float) -> np.ndarray:
        """Encode a single timestamp as a unit-norm temporal vector."""
        if ts_seconds is None:
            ts_seconds = 0
        ts = float(ts_seconds)
        phases = 2.0 * math.pi * ts / self._scales  # one phase per scale
        vec = np.empty(self.dim, dtype=np.float32)
        vec[0::2] = np.sin(phases).astype(np.float32)
        vec[1::2] = np.cos(phases).astype(np.float32)
        # Sinusoids are already bounded; the vector has a natural L2
        # norm of sqrt(n_scales). Normalise to unit length so cosine
        # similarity with another encoded ts is in [-1, 1].
        n = float(np.linalg.norm(vec))
        if n > 0:
            vec = vec / n
        return vec

    def encode_many(self, ts_seconds: np.ndarray | list[int]) -> np.ndarray:
        """Vectorised encode of an array of timestamps. Returns (N, dim)."""
        ts = np.asarray(ts_seconds, dtype=np.float64).reshape(-1)
        if ts.size == 0:
            return np.zeros((0, self.dim), dtype=np.float32)
        # (N, n_scales) phases
        phases = 2.0 * math.pi * ts[:, None] / self._scales[None, :]
        out = np.empty((ts.size, self.dim), dtype=np.float32)
        out[:, 0::2] = np.sin(phases).astype(np.float32)
        out[:, 1::2] = np.cos(phases).astype(np.float32)
        # Per-row L2 normalise
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms

    def now(self) -> np.ndarray:
        """Temporal context vector for the current moment."""
        return self.encode(int(time.time()))

    @staticmethod
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two temporal vectors."""
        if a is None or b is None:
            return 0.0
        a = np.asarray(a, dtype=np.float32).reshape(-1)
        b = np.asarray(b, dtype=np.float32).reshape(-1)
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))
