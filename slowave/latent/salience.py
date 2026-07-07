from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SalienceConfig:
    # Exponential decay: s <- s * exp(-dt / tau)
    tau_seconds: float = 3600.0
    min_salience: float = 0.01
    novelty_weight: float = 1.0
    recall_reinforcement: float = 0.2
    consolidation_penalty: float = 0.5


class SalienceEngine:
    """Salience = novelty + usage + feedback (minimal MVP).

    MVP implements:
      - novelty (distance to nearest neighbor in episodic space)
      - exponential recency decay
      - reinforcement on recall
      - penalty after consolidation
    """

    def __init__(self, cfg: SalienceConfig):
        self.cfg = cfg

    def decay(self, salience: float, dt_seconds: float) -> float:
        s = float(salience) * math.exp(-float(dt_seconds) / float(self.cfg.tau_seconds))
        return max(self.cfg.min_salience, s)

    def compute_novelty_salience(self, nn_similarity: float) -> float:
        """Novelty from cosine similarity to nearest neighbor.

        With normalized vectors, similarity in [-1, 1]. Higher similarity => lower novelty.
        We map novelty = (1 - sim) / 2 in [0,1].
        """
        sim = float(nn_similarity)
        novelty = (1.0 - sim) / 2.0
        return max(self.cfg.min_salience, self.cfg.novelty_weight * novelty)

    def reinforce_on_recall(self, salience: float) -> float:
        return float(salience) + float(self.cfg.recall_reinforcement)

    def penalize_after_consolidation(self, salience: float) -> float:
        s = float(salience) * float(self.cfg.consolidation_penalty)
        return max(self.cfg.min_salience, s)

    def sample_proportional(self, ids_and_salience: list[tuple[int, float]], n: int) -> list[int]:
        if not ids_and_salience or n <= 0:
            return []
        ids = np.asarray([i for i, _ in ids_and_salience], dtype=np.int64)
        w = np.asarray(
            [max(self.cfg.min_salience, float(s)) for _, s in ids_and_salience], dtype=np.float64
        )
        w = w / (w.sum() + 1e-12)
        n = min(int(n), ids.size)
        chosen = np.random.choice(ids, size=n, replace=False, p=w)
        return [int(x) for x in chosen]
