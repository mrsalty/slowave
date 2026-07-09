"""Micro-benchmark: TemporalProbe (Stage 10 anchor estimation) — Phase 7.

TemporalProbe had zero test coverage before this file (plans/07-temporal.md
Micro-Benchmark Gap). TemporalContext (Stage 7 sinusoidal encoding) is
already covered end-to-end by test_retrieval_pipeline_plumbing.py's SP-2 —
not duplicated here.

All tests use a hand-crafted orthonormal probe/query embedding space so
cosine similarities are exact by construction. Deterministic, <5s, no
external data, no real encoder.
"""

from __future__ import annotations

import numpy as np
import pytest

from slowave.latent.temporal import TemporalContext, TemporalProbe

_DIM = 4
_NOW_TS = 1_000_000


def _axis(i: int) -> np.ndarray:
    v = np.zeros(_DIM, dtype=np.float32)
    v[i] = 1.0
    return v


# Small, fully controlled probe set: index 0 is always "now" (displacement 0),
# matching the real _TEMPORAL_PROBES convention (now-probe first).
_PROBES = (
    ("now", 0),
    ("past_near", -100),
    ("past_far", -1000),
)


class _CountingEncoder:
    """Deterministic registry-based encoder that counts calls."""

    def __init__(self) -> None:
        self._registry: dict[str, np.ndarray] = {
            "now": _axis(0),
            "past_near": _axis(1),
            "past_far": _axis(2),
        }
        self.n_calls = 0

    def encode(self, text: str) -> np.ndarray:
        self.n_calls += 1
        return self._registry[text].copy()


def _make_probe(**kwargs) -> tuple[TemporalProbe, _CountingEncoder]:
    enc = _CountingEncoder()
    probe = TemporalProbe(enc.encode, probes=_PROBES, **kwargs)
    return probe, enc


# ---------------------------------------------------------------------------
# Dead-zone gate
# ---------------------------------------------------------------------------


def test_atemporal_query_returns_now_unchanged():
    """Query identical to the 'now' probe: no past probe beats it, dead-zone
    gate fires, estimate_anchor returns now_ts unchanged (core doc Invariant 4)."""
    probe, _ = _make_probe(atemporal_margin=0.12)
    anchor = probe.estimate_anchor(_axis(0), now_ts=_NOW_TS)
    assert anchor == _NOW_TS


def test_genuine_temporal_query_shifts_anchor_past():
    """Query identical to a past probe clears the dead-zone gate and produces
    a negative displacement (anchor_ts < now_ts)."""
    probe, _ = _make_probe(atemporal_margin=0.12, softmax_temperature=0.05)
    anchor = probe.estimate_anchor(_axis(1), now_ts=_NOW_TS)
    assert anchor < _NOW_TS


def test_atemporal_margin_zero_boundary_is_not_dead_zone():
    """A tied best_past_sim - now_sim == 0 must NOT trigger the dead zone when
    atemporal_margin=0.0 — the gate condition is strict '<', so a tie counts
    as temporal, not atemporal."""
    enc = _CountingEncoder()
    # Query equidistant from "now" and "past_near": cos=0.5 to axis0, 0.5 to axis1.
    q = (_axis(0) + _axis(1)) / np.linalg.norm(_axis(0) + _axis(1))
    probe = TemporalProbe(enc.encode, probes=_PROBES, atemporal_margin=0.0)
    anchor = probe.estimate_anchor(q, now_ts=_NOW_TS)
    assert anchor != _NOW_TS


# ---------------------------------------------------------------------------
# Softmax displacement bound (core doc Invariant 5)
# ---------------------------------------------------------------------------


def test_displacement_never_exceeds_most_extreme_matched_probe():
    """Weighted-mean displacement is a convex combination of {0, -100, -1000}:
    its magnitude can never exceed the most extreme matched probe (-1000),
    regardless of temperature."""
    for temperature in (0.02, 0.05, 0.15, 0.5, 2.0):
        probe, _ = _make_probe(atemporal_margin=0.0, softmax_temperature=temperature)
        anchor = probe.estimate_anchor(_axis(2), now_ts=_NOW_TS)
        displacement = anchor - _NOW_TS
        assert -1000 <= displacement <= 0, f"T={temperature}: displacement={displacement}"


def test_sharper_temperature_moves_closer_to_dominant_probe():
    """Lower softmax_temperature concentrates weight on the best-matching
    probe, so the returned displacement should be closer to that probe's raw
    displacement than a higher temperature (which blends toward 'now')."""
    q = _axis(2)  # matches "past_far" (-1000) exactly
    sharp, _ = _make_probe(atemporal_margin=0.0, softmax_temperature=0.02)
    flat, _ = _make_probe(atemporal_margin=0.0, softmax_temperature=2.0)
    d_sharp = sharp.estimate_anchor(q, now_ts=_NOW_TS) - _NOW_TS
    d_flat = flat.estimate_anchor(q, now_ts=_NOW_TS) - _NOW_TS
    assert abs(d_sharp) > abs(d_flat)


# ---------------------------------------------------------------------------
# Determinism and embedding-call discipline
# ---------------------------------------------------------------------------


def test_estimate_anchor_is_deterministic():
    probe, _ = _make_probe(atemporal_margin=0.12, softmax_temperature=0.05)
    q = _axis(1)
    a1 = probe.estimate_anchor(q, now_ts=_NOW_TS)
    a2 = probe.estimate_anchor(q, now_ts=_NOW_TS)
    assert a1 == a2


def test_probes_embedded_once_no_reembedding_at_query_time():
    """__init__ embeds each probe exactly once; estimate_anchor() performs
    only dot products, never calls encode_fn again (core doc Invariant 6)."""
    enc = _CountingEncoder()
    probe = TemporalProbe(enc.encode, probes=_PROBES)
    assert enc.n_calls == len(_PROBES)
    for _ in range(5):
        probe.estimate_anchor(_axis(1), now_ts=_NOW_TS)
    assert enc.n_calls == len(_PROBES)


def test_query_embedding_normalized_internally():
    """A non-unit-norm query produces the same anchor as its normalized form —
    estimate_anchor() must normalize internally regardless of caller."""
    probe, _ = _make_probe(atemporal_margin=0.12, softmax_temperature=0.05)
    unit_q = _axis(1)
    scaled_q = unit_q * 37.0
    assert probe.estimate_anchor(unit_q, now_ts=_NOW_TS) == probe.estimate_anchor(
        scaled_q, now_ts=_NOW_TS
    )


def test_now_ts_defaults_to_current_time_when_omitted():
    probe, _ = _make_probe(atemporal_margin=0.12)
    anchor = probe.estimate_anchor(_axis(0))
    assert isinstance(anchor, int)


# ---------------------------------------------------------------------------
# TemporalContext sanity (not duplicating SP-2 — just the pure-function
# properties SP-2 doesn't isolate: determinism and self-similarity).
# ---------------------------------------------------------------------------


def test_temporal_context_encode_deterministic():
    tc = TemporalContext()
    v1 = tc.encode(1_700_000_000)
    v2 = tc.encode(1_700_000_000)
    np.testing.assert_array_equal(v1, v2)


def test_temporal_context_self_similarity_is_one():
    tc = TemporalContext()
    v = tc.encode(1_700_000_000)
    assert tc.cosine(v, v) == pytest.approx(1.0, abs=1e-5)


def test_temporal_context_dimension_matches_scale_count():
    tc = TemporalContext()
    assert tc.encode(0).shape == (2 * len(tc.cfg.scales_seconds),)
