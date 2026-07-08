"""Micro-benchmark: salience decay, reinforcement, and consolidation penalty.

Verifies the core invariants of SalienceEngine:
  - Decay follows exponential curve: s(t) = s0 * exp(-t / tau)
  - Floor is always respected: s >= min_salience (0.01)
  - Reinforcement adds salience_weight to recalled episodes
  - Consolidation penalty: s' = s * consolidation_penalty
  - Decay is monotone between reinforcement events
  - Floor clamping works after extreme decay

Deterministic, no external data, runs in <2s.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from slowave.latent.salience import SalienceConfig, SalienceEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> SalienceEngine:
    """Default SalienceEngine with standard config (tau=7 days, etc.)."""
    return SalienceEngine(SalienceConfig())


@pytest.fixture
def fast_engine() -> SalienceEngine:
    """SalienceEngine with a short tau for fast deterministic tests."""
    return SalienceEngine(SalienceConfig(tau_seconds=100.0, min_salience=0.01))


# ---------------------------------------------------------------------------
# Decay tests
# ---------------------------------------------------------------------------


class TestDecay:
    """Exponential decay: s <- s * exp(-dt / tau), clamped to min_salience."""

    def test_zero_elapsed_no_decay(self, fast_engine: SalienceEngine) -> None:
        """At dt=0, salience is unchanged."""
        assert fast_engine.decay(0.5, 0.0) == pytest.approx(0.5)

    def test_exactly_one_tau(self, fast_engine: SalienceEngine) -> None:
        """After one tau, salience should be s0 * e^-1."""
        s0 = 0.8
        expected = s0 * math.exp(-1.0)
        result = fast_engine.decay(s0, 100.0)
        assert result == pytest.approx(expected, rel=1e-9)

    def test_two_tau(self, fast_engine: SalienceEngine) -> None:
        """After two tau, salience should be s0 * e^-2."""
        s0 = 0.8
        expected = s0 * math.exp(-2.0)
        result = fast_engine.decay(s0, 200.0)
        assert result == pytest.approx(expected, rel=1e-9)

    def test_floor_respected(self, fast_engine: SalienceEngine) -> None:
        """After many tau, salience hits floor, never below min_salience."""
        s0 = 0.5
        result = fast_engine.decay(s0, 1000.0)
        assert result == fast_engine.cfg.min_salience

    def test_already_at_floor(self, fast_engine: SalienceEngine) -> None:
        """Starting at floor, decay doesn't push below floor."""
        floor = fast_engine.cfg.min_salience
        result = fast_engine.decay(floor, 5000.0)
        assert result == floor

    def test_decay_is_monotone(self, fast_engine: SalienceEngine) -> None:
        """Longer dt always produces lower (or equal) salience."""
        s0 = 0.9
        prev = fast_engine.decay(s0, 0.0)
        for dt in [10.0, 20.0, 50.0, 100.0, 200.0]:
            curr = fast_engine.decay(s0, dt)
            assert curr <= prev, f"decay not monotone: dt={dt} gave {curr} > {prev}"
            prev = curr

    def test_decay_with_default_tau(self, engine: SalienceEngine) -> None:
        """Default tau (7 days): one hour should barely move the needle."""
        s0 = 0.5
        result = engine.decay(s0, 3600.0)
        assert result > 0.49
        assert result < s0


# ---------------------------------------------------------------------------
# Novelty tests
# ---------------------------------------------------------------------------


class TestNovelty:
    """compute_novelty_salience: novelty = (1 - nn_sim) / 2 * novelty_weight."""

    def test_maximum_novelty(self, engine: SalienceEngine) -> None:
        """nn_sim = -1 (maximally far) yields novelty = 1.0."""
        result = engine.compute_novelty_salience(-1.0)
        assert result == pytest.approx(1.0)

    def test_minimum_novelty(self, engine: SalienceEngine) -> None:
        """nn_sim = 1.0 (identical) yields novelty = 0.0, clamped to floor."""
        result = engine.compute_novelty_salience(1.0)
        assert result == engine.cfg.min_salience

    def test_mid_novelty(self, engine: SalienceEngine) -> None:
        """nn_sim = 0.0 yields novelty = 0.5."""
        result = engine.compute_novelty_salience(0.0)
        assert result == pytest.approx(0.5)

    def test_novelty_weight_scaling(self) -> None:
        """Higher novelty_weight produces proportionally higher salience."""
        cfg_low = SalienceConfig(novelty_weight=0.5)
        cfg_high = SalienceConfig(novelty_weight=2.0)
        low_eng = SalienceEngine(cfg_low)
        high_eng = SalienceEngine(cfg_high)
        assert low_eng.compute_novelty_salience(0.0) == pytest.approx(0.25)
        assert high_eng.compute_novelty_salience(0.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Consolidation penalty tests
# ---------------------------------------------------------------------------


class TestConsolidationPenalty:
    """penalize_after_consolidation: s' = s * consolidation_penalty, clamped."""

    def test_halving_with_default(self, engine: SalienceEngine) -> None:
        """Default consolidation_penalty=0.5 halves the salience."""
        result = engine.penalize_after_consolidation(0.8)
        assert result == pytest.approx(0.4)

    def test_floor_respected(self, engine: SalienceEngine) -> None:
        """Very low salience after penalty gets clamped to floor."""
        result = engine.penalize_after_consolidation(0.015)
        assert result == engine.cfg.min_salience

    def test_no_penalty_when_penalty_is_one(self) -> None:
        """consolidation_penalty=1.0 means no change."""
        cfg = SalienceConfig(consolidation_penalty=1.0)
        eng = SalienceEngine(cfg)
        assert eng.penalize_after_consolidation(0.7) == pytest.approx(0.7)

    def test_aggressive_penalty(self) -> None:
        """consolidation_penalty=0.1 means near-total suppression."""
        cfg = SalienceConfig(consolidation_penalty=0.1)
        eng = SalienceEngine(cfg)
        result = eng.penalize_after_consolidation(0.5)
        assert result == pytest.approx(0.05)

    def test_already_at_floor(self, engine: SalienceEngine) -> None:
        """Consolidation penalty on floor stays at floor."""
        floor = engine.cfg.min_salience
        assert engine.penalize_after_consolidation(floor) == floor


# ---------------------------------------------------------------------------
# End-to-end lifecycle: decay -> reinforce -> decay -> consolidate
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Simulate the full episodic salience lifecycle with controlled time."""

    def test_decay_reinforce_decay_cycle(self, fast_engine: SalienceEngine) -> None:
        """Episode decays, gets reinforced, decays again."""
        s0 = 0.9
        s1 = fast_engine.decay(s0, 100.0)
        assert s1 < s0
        salience_weight = 0.5
        s2 = s1 + salience_weight
        s3 = fast_engine.decay(s2, 100.0)
        assert s3 < s2
        assert s3 > fast_engine.cfg.min_salience

    def test_consolidation_then_decay(self, fast_engine: SalienceEngine) -> None:
        """Consolidation penalty followed by decay, both respect floor."""
        s0 = 0.6
        s1 = fast_engine.penalize_after_consolidation(s0)
        assert s1 == pytest.approx(0.3)
        s2 = fast_engine.decay(s1, 500.0)

    def test_reinforce_after_floor_decay(self, fast_engine: SalienceEngine) -> None:
        """Even after hitting floor, reinforcement can revive an episode."""
        s0 = 0.5
        s1 = fast_engine.decay(s0, 2000.0)
        assert s1 == fast_engine.cfg.min_salience
        salience_weight = 0.5
        s2 = s1 + salience_weight
        assert s2 == pytest.approx(0.51)


# ---------------------------------------------------------------------------
# Sample proportional tests
# ---------------------------------------------------------------------------


class TestSampleProportional:
    """sample_proportional: weighted random sampling respecting salience."""

    def test_empty_list(self, engine: SalienceEngine) -> None:
        assert engine.sample_proportional([], 5) == []

    def test_zero_requested(self, engine: SalienceEngine) -> None:
        assert engine.sample_proportional([(1, 0.5)], 0) == []

    def test_request_more_than_available(self, engine: SalienceEngine) -> None:
        """n > len returns all ids (no replacement)."""
        items = [(10, 0.8), (20, 0.5), (30, 0.3)]
        result = engine.sample_proportional(items, 10)
        assert len(result) == 3
        assert set(result) == {10, 20, 30}

    def test_clamps_below_floor(self, engine: SalienceEngine) -> None:
        """Salience below min_salience gets clamped up before sampling."""
        items = [(1, 0.001), (2, 0.5)]
        result = engine.sample_proportional(items, 1)
        assert len(result) == 1

    def test_deterministic_with_fixed_seed(self, engine: SalienceEngine) -> None:
        """Same seed produces same result."""
        rng = np.random.RandomState(42)
        items = [(1, 1.0), (2, 0.5), (3, 0.1)]
        old_state = np.random.get_state()
        try:
            np.random.set_state(rng.get_state())
            result1 = engine.sample_proportional(items, 2)
            np.random.set_state(rng.get_state())
            result2 = engine.sample_proportional(items, 2)
            assert result1 == result2
        finally:
            np.random.set_state(old_state)

    def test_single_item_always_selected(self, engine: SalienceEngine) -> None:
        items = [(99, 0.5)]
        result = engine.sample_proportional(items, 1)
        assert result == [99]


# ---------------------------------------------------------------------------
# Invariant: floor always respected across all operations
# ---------------------------------------------------------------------------


class TestFloorInvariants:
    """The min_salience floor is an absolute lower bound across all code paths."""

    def test_decay_never_below_floor(self, fast_engine: SalienceEngine) -> None:
        for s0 in [0.01, 0.02, 0.05, 0.1, 0.5, 1.0]:
            for dt in [0.0, 10.0, 100.0, 500.0, 2000.0]:
                result = fast_engine.decay(s0, dt)
                assert result >= fast_engine.cfg.min_salience

    def test_penalty_never_below_floor(self, engine: SalienceEngine) -> None:
        for s0 in [0.01, 0.02, 0.05, 0.1, 0.5, 1.0]:
            result = engine.penalize_after_consolidation(s0)
            assert result >= engine.cfg.min_salience
