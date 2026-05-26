from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from slowave.latent.types import Event
from slowave.utils.vec import to_f32


@dataclass(frozen=True)
class SyntheticConfig:
    dim: int = 64
    n_entities: int = 100
    n_types: int = 12
    n_topics: int = 8
    noise: float = 0.10
    seed: int = 7


def generate_synthetic_events(n: int, cfg: SyntheticConfig) -> list[Event]:
    """Create an event stream with latent structure.

    Each event belongs to a latent "topic" that drives embedding + entities.
    This gives replay/clustering something non-trivial to discover.
    """
    rng = np.random.default_rng(cfg.seed)
    topics = to_f32(rng.normal(size=(cfg.n_topics, cfg.dim)))
    topics /= np.linalg.norm(topics, axis=1, keepdims=True) + 1e-12

    base_ts = int(time.time())
    events: list[Event] = []
    topic = int(rng.integers(0, cfg.n_topics))
    for i in range(n):
        # Markov-ish topic transitions
        if rng.random() < 0.15:
            topic = int(rng.integers(0, cfg.n_topics))
        emb = topics[topic] + cfg.noise * to_f32(rng.normal(size=(cfg.dim,)))
        emb = emb / (np.linalg.norm(emb) + 1e-12)

        etype = f"type_{int(rng.integers(0, cfg.n_types))}"
        # entities correlated with topic
        ents = [f"ent_{(topic * 13 + j) % cfg.n_entities}" for j in rng.integers(0, 5, size=3)]
        ts = base_ts + i
        events.append(
            Event(
                event_id=f"evt_{i}",
                timestamp=ts,
                type=etype,
                entities=ents,
                embedding=to_f32(emb),
                metadata={"topic": topic, "i": i},
            )
        )
    return events
