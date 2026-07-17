from __future__ import annotations

from dataclasses import dataclass, field
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
    logic_version: str = "0"


@dataclass(frozen=True)
class EpisodeDiagnostic:
    """Per-episode provenance and score breakdown for a single retrieve() call."""

    episode_id: int
    source: str  # "cosine_direct" | "graph_harvest" | "predictive"
    prototype_id: int | None
    cosine_score: float  # direct cosine score; 0.0 for graph-only or predictive-only
    graph_activation: float  # prototype spread activation; 0.0 for cosine-direct
    temporal_bonus: float  # α_t * cos(t_q, t_e)
    salience_bonus: float  # α_s * salience
    is_dual_scale: bool  # appeared in both fine and coarse scales
    final_score: float  # score used by the pipeline for sorting
    is_in_final_head: bool  # in top episodic_top_k of pipeline output


@dataclass(frozen=True)
class QueryDiagnostics:
    """Per-query aggregate metrics for a single retrieve() call."""

    seed_prototypes_n: int
    activated_after_spread_n: int  # prototypes with activation > floor after spreading
    activation_depth: list[int]  # |active_set| after each spread step
    cosine_direct_n: int  # episodes from pure cosine-FAISS
    graph_harvest_n: int  # graph-only episodes added to merged pool
    graph_only_saves: int  # graph episodes in final head that cosine missed
    cosine_score_min: float
    cosine_score_p50: float
    cosine_score_max: float
    dual_scale_episodes_pct: float  # fraction of final head with dual-scale bonus
    q_pred_sim: float  # cos(q, q_pred); 1.0 if no prediction used
    predictive_seed_used: bool


@dataclass(frozen=True)
class RetrievedMemorySet:
    """Latent retrieval result (structured, no language)."""

    query_embedding: np.ndarray
    episodic: list[EpisodicMemory]
    prototypes: list[SemanticPrototype]
    expanded_neighbors: dict[int, list[tuple[int, float]]]
    episode_diagnostics: list[EpisodeDiagnostic] = field(default_factory=list)
    query_diagnostics: QueryDiagnostics | None = None
