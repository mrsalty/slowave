from __future__ import annotations

from dataclasses import dataclass

from slowave.latent.episodic_store import EpisodicStore
from slowave.latent.graph_manager import GraphManager
from slowave.latent.semantic_store import SemanticStore
from slowave.storage.sqlite_db import SQLiteDB


@dataclass(frozen=True)
class Metrics:
    prototype_compression_ratio: float
    graph_sparsity: float
    transition_prediction_loss: float
    retrieval_consistency_score: float
    avg_salience_decay_rate: float


def compute_metrics(
    *,
    db: SQLiteDB,
    episodic: EpisodicStore,
    semantic: SemanticStore,
    graph: GraphManager,
    transition_loss: float,
    retrieval_consistency_score: float,
) -> Metrics:
    n_e = float(episodic.count())
    n_p = float(max(1, semantic.count()))
    compression = n_e / n_p

    # graph sparsity: edges / possible edges (directed, without self loops)
    edges = float(graph.edge_count())
    possible = max(1.0, n_p * (n_p - 1.0))
    sparsity = edges / possible

    # avg salience decay: approximate with mean salience (lower after replay)
    conn = db.connect()
    row = conn.execute("SELECT AVG(salience) AS m FROM episodic_memories").fetchone()
    avg_sal = float(row["m"] or 0.0)
    # convert to "decay rate" proxy in [0,1] (higher => more decay). MVP proxy.
    avg_decay_rate = float(1.0 / (1.0 + avg_sal))

    # retrieval consistency is passed in; keep as-is.

    return Metrics(
        prototype_compression_ratio=float(compression),
        graph_sparsity=float(sparsity),
        transition_prediction_loss=float(transition_loss),
        retrieval_consistency_score=float(retrieval_consistency_score),
        avg_salience_decay_rate=float(avg_decay_rate),
    )
