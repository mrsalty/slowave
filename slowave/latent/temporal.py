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

Temporal anchor estimation (Stage 10):
-------------------------------------
Brain analogue: the lateral entorhinal cortex performs a backward
temporal search when a query contains temporal language. Rather than
parsing "last month" with a brittle rule-set, we exploit the fact that
temporal language is *already encoded* in the sentence-embedding space
— the same encoder that encodes episodes. A small static set of
temporal probe phrases (the "temporal compass") is embedded once at
init. At query time we measure cosine similarity between the query
embedding and each probe, softmax-weight the corresponding
displacements, and return the expected anchor timestamp.

This is zero-dependency, zero-regex, zero extra LLM call, and
generalises to any phrasing the encoder has seen during pre-training
(including informal / multilingual expressions). When the query
contains no temporal language the "now / today" probe dominates and
the anchor collapses to the current time — preserving the existing
default behaviour exactly.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np


# ---------------------------------------------------------------------------
# Temporal compass probes
# ---------------------------------------------------------------------------
# Each entry is (natural-language phrase, displacement_seconds from now).
# Negative = past.  Chosen to span the major retrieval bands that appear
# in LongMemEval / LoCoMo temporal questions.  The list intentionally stays
# small: adding more probes only increases precision marginally because the
# softmax already interpolates between adjacent anchors.
#
# Brain analogue: these are the discrete "temporal landmark" attractors that
# the entorhinal cortex uses to reconstruct approximate past context.  Real
# LEC cells fire at continuous rates; we discretise into ~12 landmarks and
# let the weighted mean do the interpolation.
# ---------------------------------------------------------------------------
_DAY = 86_400
_TEMPORAL_PROBES: tuple[tuple[str, int], ...] = (
    ("right now, today, at the moment",         0),
    ("yesterday, the day before",               -1 * _DAY),
    ("a few days ago, several days ago",        -4 * _DAY),
    ("last week, a week ago",                   -7 * _DAY),
    ("two weeks ago, a fortnight ago",          -14 * _DAY),
    ("last month, a month ago, recently",       -30 * _DAY),
    ("two months ago, a couple of months ago",  -60 * _DAY),
    ("three months ago, several months ago",    -90 * _DAY),
    ("six months ago, half a year ago",         -180 * _DAY),
    ("last year, a year ago",                   -365 * _DAY),
    ("two years ago",                           -730 * _DAY),
    ("a long time ago, years ago, long ago",    -3 * 365 * _DAY),
)


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


# ---------------------------------------------------------------------------
# Temporal probe / compass  (Stage 10)
# ---------------------------------------------------------------------------

class TemporalProbe:
    """Embedding-space temporal anchor estimator.

    Brain analogue: lateral entorhinal cortex backward temporal search.
    Rather than parsing natural-language time expressions with a brittle
    rule-set, we exploit the fact that temporal language is *already
    encoded* in the sentence-embedding space — the same encoder used for
    episodes.  A static set of temporal probe phrases (the "temporal
    compass") is embedded once at init.  At query time we measure cosine
    similarity between the query embedding and each probe, softmax-weight
    the corresponding time displacements, and return the expected anchor
    timestamp.

    Properties
    ----------
    - Zero new dependencies — uses the encoder already present in the engine.
    - Zero regex — generalises to any phrasing the encoder saw during
      pre-training (informal, multilingual, implicit).
    - When the query has no temporal language the "now/today" probe
      dominates and the anchor collapses to ``now_ts``, preserving the
      existing default behaviour exactly.
    - ``softmax_temperature`` controls sharpness: high T → flat weights
      (anchor ≈ centre of mass of all probes ≈ ~4 months ago); low T →
      winner-takes-all (anchor = closest probe).  Default 0.1 is gently
      peaked — a clear "last month" signal wins decisively, an ambiguous
      query spreads smoothly.

    Usage
    -----
    Build once at engine init (``encoder`` may be None to defer):

        probe = TemporalProbe(encoder.encode)

    At recall time:

        anchor_ts = probe.estimate_anchor(query_embedding, now_ts=int(time.time()))
        # returns int Unix timestamp; equals now_ts when query is atemporal
    """

    def __init__(
        self,
        encode_fn,  # callable: str -> np.ndarray[float32]
        *,
        probes: tuple[tuple[str, int], ...] = _TEMPORAL_PROBES,
        softmax_temperature: float = 0.05,
    ) -> None:
        self._encode = encode_fn
        self._displacements: list[int] = [d for _, d in probes]
        self._temperature = float(softmax_temperature)

        # Pre-compute and L2-normalise probe embeddings once.
        raw: list[np.ndarray] = []
        for phrase, _ in probes:
            v = np.asarray(encode_fn(phrase), dtype=np.float32).reshape(-1)
            n = float(np.linalg.norm(v))
            raw.append(v / n if n > 0.0 else v)
        # shape: (n_probes, dim)
        self._probe_matrix = np.stack(raw, axis=0)

    def estimate_anchor(
        self,
        query_embedding: np.ndarray,
        *,
        now_ts: int | None = None,
    ) -> int:
        """Return the estimated Unix timestamp the query is anchored to.

        Algorithm
        ---------
        1. Cosine-similarity between the (already L2-normalised) query
           embedding and each probe row  →  raw_sims  ∈ [-1, 1]^n
        2. Softmax with temperature T over raw_sims  →  weights  ∈ [0,1]^n
        3. Expected displacement  =  Σ weight_i * displacement_i
        4. anchor_ts  =  now_ts + round(expected_displacement)

        The result is an integer Unix timestamp.  When the query is
        atemporal (e.g. "what is my name?") the "now/today" probe has
        the highest similarity and the displacement is ≈ 0.
        """
        if now_ts is None:
            now_ts = int(time.time())

        q = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        qn = float(np.linalg.norm(q))
        if qn > 0.0:
            q = q / qn

        # (n_probes,) cosine similarities
        sims = self._probe_matrix @ q

        # Softmax with temperature — shift by max for numerical stability
        logits = sims / self._temperature
        logits -= logits.max()
        weights = np.exp(logits)
        weights /= weights.sum()

        # Weighted mean displacement (float seconds)
        displacement = float(np.dot(weights, np.asarray(self._displacements, dtype=np.float64)))

        return int(now_ts + round(displacement))
