from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Event:
    """Raw event envelope used by the MVP demo.

    The system core stays latent-first; this event is just input plumbing.
    """

    event_id: str
    timestamp: int
    type: str
    entities: list[str]
    embedding: np.ndarray  # float32 [dim]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class EpisodicMemory:
    id: int
    event_id: str
    ts: int
    embedding: np.ndarray
    salience: float
    metadata: dict[str, Any]
    recalled_count: int


@dataclass(frozen=True)
class SemanticPrototype:
    id: int
    centroid: np.ndarray
    support_count: int
    variance: float
    last_updated_ts: int


@dataclass(frozen=True)
class RetrievedMemorySet:
    """Latent retrieval result (structured, no language)."""

    query_embedding: np.ndarray
    episodic: list[EpisodicMemory]
    prototypes: list[SemanticPrototype]
    expanded_neighbors: dict[int, list[tuple[int, float]]]
