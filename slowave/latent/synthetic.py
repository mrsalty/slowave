"""Synthetic event generator for testing the latent substrate.

Produces deterministic random events (with numpy embeddings) without requiring
any external encoder or database. Used by test_smoke.py and benchmark harnesses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from slowave.latent.types import Event


@dataclass
class SyntheticConfig:
    """Configuration for synthetic event generation."""

    dim: int = 64
    seed: int = 42
    event_types: list[str] = field(
        default_factory=lambda: [
            "user_message",
            "assistant_message",
            "tool_call",
            "decision",
            "discovery",
        ]
    )


def generate_synthetic_events(n: int, cfg: SyntheticConfig) -> list[Event]:
    """Generate *n* synthetic :class:`Event` objects with unit-norm embeddings.

    Embeddings are sampled i.i.d. from a standard normal distribution and
    L2-normalised, giving cosine similarities that roughly follow a zero-mean
    distribution — a realistic approximation of a diverse event stream.

    Args:
        n:   Number of events to generate.
        cfg: Configuration (dim, seed, event_types).

    Returns:
        A list of :class:`~slowave.latent.types.Event` instances, one per step,
        with sequential ``event_id`` values and monotonically increasing
        ``timestamp`` values (1 minute apart starting at Unix epoch + 1 000 000).
    """
    rng = np.random.default_rng(cfg.seed)
    types = cfg.event_types
    events: list[Event] = []

    for i in range(n):
        raw = rng.standard_normal(cfg.dim).astype(np.float32)
        norm = np.linalg.norm(raw)
        emb = raw / (norm + 1e-12)

        events.append(
            Event(
                event_id=f"syn_{i:06d}",
                timestamp=1_000_000 + i * 60,
                type=types[i % len(types)],
                entities=[],
                embedding=emb,
                metadata={"index": i},
            )
        )

    return events
