from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from slowave.latent.graph_manager import GraphManager
    from slowave.latent.semantic_store import SemanticStore


@dataclass(frozen=True)
class TransitionModelConfig:
    """Config for graph-based transition model.

    Note: dim is kept for API compatibility but not used in graph-based version.
    The graph-based model learns transition probabilities P(proto_next|proto_current)
    during consolidation via Hebbian co-occurrence counting.
    """

    dim: int
    # Legacy torch params kept for config compatibility but unused
    hidden_dim: int = 128
    lr: float = 1e-3
    weight_decay: float = 1e-4
    device: str = "cpu"


class TransitionModel:
    """Graph-based transition model: predict next state via learned prototype transitions.

    Brain-inspired approach using Hebbian learning and successor representation:
    - During consolidation, count prototype transitions (Hebbian learning)
    - At prediction time, find current prototype and look up likely successors
    - Return weighted average of successor centroids (successor representation)

    This replaces the previous PyTorch MLP with a biologically plausible mechanism
    that requires no torch dependency and uses existing graph infrastructure.
    """

    def __init__(
        self,
        cfg: TransitionModelConfig,
        graph: "GraphManager | None" = None,
        semantic: "SemanticStore | None" = None,
    ):
        """Initialize graph-based transition model.

        Args:
            cfg: Config (kept for API compatibility)
            graph: GraphManager instance (set via attach_stores after engine init)
            semantic: SemanticStore instance (set via attach_stores after engine init)
        """
        self.cfg = cfg
        self._graph = graph
        self._semantic = semantic
        # Tracks how many consolidation passes have updated the graph.
        # Consumers check trained_steps > 0 before trusting predictions.
        self.trained_steps: int = 0

    def attach_stores(self, graph: "GraphManager", semantic: "SemanticStore") -> None:
        """Attach graph and semantic store after engine initialization.

        Called by SlowaveEngine after all stores are constructed to avoid
        circular dependency issues.
        """
        self._graph = graph
        self._semantic = semantic

    def predict(self, e_t: np.ndarray) -> np.ndarray:
        """Predict next embedding via graph transition probabilities.

        Args:
            e_t: Current embedding (batch_size, dim)

        Returns:
            Predicted next embedding (batch_size, dim)
        """
        if self._graph is None or self._semantic is None:
            return np.zeros_like(e_t)

        if self.trained_steps == 0:
            return np.zeros_like(e_t)

        batch_size = e_t.shape[0]
        predictions = []

        for i in range(batch_size):
            embedding = e_t[i].reshape(1, -1)
            current_proto_id = self._find_nearest_prototype(embedding)

            if current_proto_id is None:
                predictions.append(np.zeros(e_t.shape[1], dtype=np.float32))
                continue

            next_prototypes = self._get_successor_prototypes(current_proto_id)

            if not next_prototypes:
                predictions.append(np.zeros(e_t.shape[1], dtype=np.float32))
                continue

            prediction = np.zeros(e_t.shape[1], dtype=np.float32)
            total_weight = 0.0

            for next_id, transition_weight in next_prototypes:
                proto = self._semantic.get(next_id)
                if proto is not None:
                    prediction += transition_weight * proto.centroid.astype(np.float32)
                    total_weight += transition_weight

            if total_weight > 0:
                prediction /= total_weight

            predictions.append(prediction)

        return np.stack(predictions, axis=0)

    def _find_nearest_prototype(self, embedding: np.ndarray) -> int | None:
        """Find which prototype this embedding belongs to."""
        try:
            # FIX: use positional parameter name 'top_k', not 'k'
            scores, ids = self._semantic.search(embedding[0], top_k=1)
            if len(ids) > 0 and ids[0] != -1:
                return int(ids[0])
        except Exception:
            pass
        return None

    def _get_successor_prototypes(self, proto_id: int) -> list[tuple[int, float]]:
        """Get likely successor prototypes from graph edges."""
        if self._graph is None:
            return []

        conn = self._graph.db.connect()
        # FIX: use correct schema column names dst_prototype_id / src_prototype_id
        rows = conn.execute(
            "SELECT dst_prototype_id, w_transition FROM prototype_edges"
            " WHERE src_prototype_id = ? AND w_transition > 0",
            (proto_id,),
        ).fetchall()

        if not rows:
            return []

        successors = [(int(r["dst_prototype_id"]), float(r["w_transition"])) for r in rows]
        successors.sort(key=lambda x: x[1], reverse=True)
        return successors[:5]

    def train_batch(self, e_t: np.ndarray, e_next: np.ndarray) -> float:
        """No-op: training happens during graph consolidation (Hebbian learning)."""
        self.trained_steps += 1
        return 0.0
