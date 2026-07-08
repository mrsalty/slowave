"""Feedback system for closing the memory loop.

Brain-inspired feedback model:
- symbolic labels (feedback enum) are the public API
- internally converted to numeric learning signals
- signals drive memory reinforcement/suppression/review
- outcome is separate from memory-quality signal
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ============================================================================
# Feedback signal: numeric vector of learning dynamics
# ============================================================================


@dataclass(frozen=True)
class FeedbackSignal:
    """Brain-like learning signal derived from symbolic feedback label.

    Each component maps to a neuroscientific or cognitive mechanism:

    valence:
        overall positive/negative usefulness of context (-1 to +1)
        dopaminergic reward signal analogue

    context_fit:
        degree to which memory matched current cue (-1 to +1)
        activating but irrelevant memories have low context_fit

    truth_error:
        degree to which memory was factually wrong (0 to 1)
        prediction error / model violation signal

    temporal_error:
        degree to which memory is stale/outdated (0 to 1)
        temporal prediction error / world model mismatch

    missingness:
        degree to which recall failed to retrieve needed info (0 to 1)
        failed retrieval signal / information gap

    overload:
        degree to which context packet overloaded working memory (0 to 1)
        working-memory capacity failure / gating error

    salience_delta:
        absolute change to schema salience
        can be positive (reinforce) or negative (suppress)

    confidence_delta:
        absolute change to schema confidence
        used for truth/temporal errors

    review_pressure:
        urgency to flag memory for manual review (0 to 1)
        for stale/wrong memories

    outcome_reward:
        task-level reward signal (-1 to +1)
        stored separately; not applied to schema reward by default
    """

    valence: float
    context_fit: float
    truth_error: float
    temporal_error: float
    missingness: float
    overload: float
    salience_delta: float
    confidence_delta: float
    review_pressure: float
    outcome_reward: float


# ============================================================================
# Configuration for feedback behavior
# ============================================================================


@dataclass(frozen=True)
class FeedbackConfig:
    """Configuration for context feedback system.

    All knobs are exposed to enable ablation/grid search.
    """

    # Master enable
    enabled: bool = True

    # Persistence knobs
    persist_context_snapshots: bool = True
    persist_response_json: bool = True
    persist_rendered_context: bool = False  # can be large
    persist_activation_trace: bool = False  # can be very large
    max_response_json_chars: int = 20000
    max_memory_content_chars: int = 500

    # Learning knobs
    apply_learning: bool = True
    apply_positive_learning: bool = True
    apply_negative_learning: bool = True
    apply_stale_wrong_review: bool = True
    apply_outcome_to_schema_reward: bool = False
    context_feedback_weight: float = 0.5
    recall_feedback_weight: float = 1.0

    # Salience delta per label (positive reinforcement)
    useful_salience_delta: float = 0.10
    partially_useful_salience_delta: float = 0.04

    # Salience delta per label (negative reinforcement)
    # Negative reinforcement: increased penalties so wrong/stale feedback visibly suppresses ranking
    irrelevant_salience_delta: float = -0.05  # query-local only; no global damage
    stale_salience_delta: float = -0.20  # was -0.15
    wrong_salience_delta: float = -0.30  # was -0.25

    # Confidence delta per label
    useful_confidence_delta: float = 0.02
    stale_confidence_delta: float = -0.20  # was -0.15
    wrong_confidence_delta: float = -0.40  # was -0.30

    # Review thresholds
    stale_review_threshold: float = 0.7
    wrong_review_threshold: float = 1.0

    # Bounds
    min_salience: float = 0.01
    min_confidence: float = 0.0
    max_confidence: float = 1.0

    # Missing context handling
    missing_creates_memory: bool = False
    missing_replay_enabled: bool = True


# ============================================================================
# Label validation and mapping
# ============================================================================


VALID_FEEDBACK_LABELS = frozenset(
    (
        "useful",
        "partially_useful",
        "irrelevant",
        "stale",
        "wrong",
        "missing",
        "too_much_context",
    )
)

VALID_OUTCOME_LABELS = frozenset(
    (
        "success",
        "failure",
        "partial",
        "unknown",
    )
)


def normalize_feedback_label(label: str) -> str:
    """Normalize feedback label; raise if unknown."""
    normalized = str(label).strip().lower()
    if normalized not in VALID_FEEDBACK_LABELS:
        raise ValueError(
            f"Invalid feedback label: {label}. " f"Must be one of {sorted(VALID_FEEDBACK_LABELS)}"
        )
    return normalized


def normalize_outcome_label(label: str) -> str:
    """Normalize outcome label; default to 'unknown' if missing or invalid."""
    if not label:
        return "unknown"
    normalized = str(label).strip().lower()
    # Normalize common aliases so callers don't have to know the exact enum value.
    if normalized in {"failed", "fail", "task_failed"}:
        normalized = "failure"
    if normalized not in VALID_OUTCOME_LABELS:
        return "unknown"
    return normalized


def feedback_signal_for(
    feedback: str,
    outcome: str,
    cfg: FeedbackConfig,
) -> FeedbackSignal:
    """Map symbolic feedback label and outcome to numeric learning signal.

    Returns a FeedbackSignal vector representing the learning dynamics.
    """
    fb = normalize_feedback_label(feedback)
    oc = normalize_outcome_label(outcome)

    outcome_reward = {
        "success": 1.0,
        "partial": 0.3,
        "unknown": 0.0,
        "failure": -1.0,
    }.get(oc, 0.0)

    # Map feedback label to signal components
    if fb == "useful":
        return FeedbackSignal(
            valence=1.0,
            context_fit=1.0,
            truth_error=0.0,
            temporal_error=0.0,
            missingness=0.0,
            overload=0.0,
            salience_delta=cfg.useful_salience_delta,
            confidence_delta=cfg.useful_confidence_delta,
            review_pressure=0.0,
            outcome_reward=outcome_reward,
        )

    elif fb == "partially_useful":
        return FeedbackSignal(
            valence=0.4,
            context_fit=0.5,
            truth_error=0.0,
            temporal_error=0.0,
            missingness=0.0,
            overload=0.0,
            salience_delta=cfg.partially_useful_salience_delta,
            confidence_delta=0.0,
            review_pressure=0.0,
            outcome_reward=outcome_reward,
        )

    elif fb == "irrelevant":
        return FeedbackSignal(
            valence=-0.4,
            context_fit=-1.0,
            truth_error=0.0,
            temporal_error=0.0,
            missingness=0.0,
            overload=0.0,
            salience_delta=cfg.irrelevant_salience_delta,
            confidence_delta=0.0,
            review_pressure=0.0,
            outcome_reward=outcome_reward,
        )

    elif fb == "stale":
        return FeedbackSignal(
            valence=-0.6,
            context_fit=-0.3,
            truth_error=0.0,
            temporal_error=1.0,
            missingness=0.0,
            overload=0.0,
            salience_delta=cfg.stale_salience_delta,
            confidence_delta=cfg.stale_confidence_delta,
            review_pressure=cfg.stale_review_threshold,
            outcome_reward=outcome_reward,
        )

    elif fb == "wrong":
        return FeedbackSignal(
            valence=-1.0,
            context_fit=-0.5,
            truth_error=1.0,
            temporal_error=0.0,
            missingness=0.0,
            overload=0.0,
            salience_delta=cfg.wrong_salience_delta,
            confidence_delta=cfg.wrong_confidence_delta,
            review_pressure=cfg.wrong_review_threshold,
            outcome_reward=outcome_reward,
        )

    elif fb == "missing":
        return FeedbackSignal(
            valence=-0.3,
            context_fit=0.0,
            truth_error=0.0,
            temporal_error=0.0,
            missingness=1.0,
            overload=0.0,
            salience_delta=0.0,
            confidence_delta=0.0,
            review_pressure=0.0,
            outcome_reward=outcome_reward,
        )

    elif fb == "too_much_context":
        return FeedbackSignal(
            valence=-0.2,
            context_fit=-0.2,
            truth_error=0.0,
            temporal_error=0.0,
            missingness=0.0,
            overload=1.0,
            salience_delta=0.0,
            confidence_delta=0.0,
            review_pressure=0.0,
            outcome_reward=outcome_reward,
        )

    else:
        # Should not reach here after normalize_feedback_label
        raise ValueError(f"Unexpected feedback label: {fb}")
