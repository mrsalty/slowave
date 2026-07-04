from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from slowave.storage.sqlite_db import SQLiteDB


@dataclass(frozen=True)
class GraphConfig:
    top_k_similarity: int = 8
    top_k_coactivation: int = 6
    prune_below: float = 0.05
    # w_ij = l1*similarity(s_i,s_j) + l2*P(s_j|s_i) + l3*coactivation
    lambda_similarity: float = 1.0
    lambda_transition: float = 0.5
    lambda_coactivation: float = 0.3


class GraphManager:
    """Sparse directed graph over semantic prototypes.

    - Similarity edges: top-k cosine (computed over current prototypes)
    - Transition edges: counts of (proto_t -> proto_{t+1}) from replayed sequences
    - Coactivation: prototypes co-selected in same replay batch
    """

    def __init__(self, db: SQLiteDB, cfg: GraphConfig):
        self.db = db
        self.cfg = cfg

    def _upsert_edge(
        self,
        src: int,
        dst: int,
        *,
        w_similarity: float,
        w_transition: float,
        w_coactivation: float,
        ts: int | None = None,
    ) -> None:
        if ts is None:
            ts = int(time.time())
        weight = (
            self.cfg.lambda_similarity * float(w_similarity)
            + self.cfg.lambda_transition * float(w_transition)
            + self.cfg.lambda_coactivation * float(w_coactivation)
        )
        conn = self.db.connect()
        conn.execute(
            """
            INSERT INTO prototype_edges (
              src_prototype_id, dst_prototype_id,
              w_similarity, w_transition, w_coactivation,
              weight, last_updated_ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(src_prototype_id, dst_prototype_id) DO UPDATE SET
              w_similarity = excluded.w_similarity,
              w_transition = excluded.w_transition,
              w_coactivation = excluded.w_coactivation,
              weight = excluded.weight,
              last_updated_ts = excluded.last_updated_ts
            """,
            (int(src), int(dst), float(w_similarity), float(w_transition), float(w_coactivation), float(weight), int(ts)),
        )
        conn.commit()

    def _get_components(self, src: int, dst: int) -> tuple[float, float, float]:
        conn = self.db.connect()
        row = conn.execute(
            """
            SELECT w_similarity, w_transition, w_coactivation
            FROM prototype_edges
            WHERE src_prototype_id = ? AND dst_prototype_id = ?
            """,
            (int(src), int(dst)),
        ).fetchone()
        if row is None:
            return 0.0, 0.0, 0.0
        return float(row["w_similarity"]), float(row["w_transition"]), float(row["w_coactivation"])

    def set_similarity_edges(self, *, prototype_ids: list[int], centroids: np.ndarray) -> None:
        """Recompute top-k similarity edges for given prototypes.

        For MVP we compute full pairwise similarities for small N.
        """
        if len(prototype_ids) == 0:
            return
        X = centroids.astype(np.float32)
        # Normalize for cosine
        X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)
        sim = X @ X.T  # [N,N]
        N = sim.shape[0]
        for i in range(N):
            src = int(prototype_ids[i])
            # exclude self
            scores = sim[i].copy()
            scores[i] = -1.0
            k = min(self.cfg.top_k_similarity, N - 1)
            if k <= 0:
                continue
            nn_idx = np.argpartition(-scores, kth=k - 1)[:k]
            nn_idx = nn_idx[np.argsort(-scores[nn_idx])]
            for j in nn_idx:
                dst = int(prototype_ids[int(j)])
                s = float(scores[int(j)])
                if s <= 0:
                    continue
                _ws, wt, wc = self._get_components(src, dst)
                self._upsert_edge(src, dst, w_similarity=s, w_transition=wt, w_coactivation=wc)

        self.prune_edges()

    def apply_transition_counts(self, counts: dict[tuple[int, int], float]) -> None:
        for (src, dst), c in counts.items():
            ws, _wt, wc = self._get_components(src, dst)
            self._upsert_edge(src, dst, w_similarity=ws, w_transition=float(c), w_coactivation=wc)
        self.prune_edges()

    def apply_coactivation_counts(self, counts: dict[tuple[int, int], float]) -> None:
        # Keep only top-k coactivation per source to preserve sparsity.
        by_src: dict[int, list[tuple[int, float]]] = {}
        for (src, dst), c in counts.items():
            if src == dst:
                continue
            by_src.setdefault(int(src), []).append((int(dst), float(c)))

        for src, items in by_src.items():
            items.sort(key=lambda t: t[1], reverse=True)
            for dst, c in items[: self.cfg.top_k_coactivation]:
                ws, wt, _wc = self._get_components(src, dst)
                self._upsert_edge(src, dst, w_similarity=ws, w_transition=wt, w_coactivation=float(c))
        self.prune_edges()

    def prune_edges(self) -> None:
        conn = self.db.connect()
        conn.execute("DELETE FROM prototype_edges WHERE weight < ?", (float(self.cfg.prune_below),))
        conn.commit()

    def neighbors(self, prototype_id: int, top_k: int = 8) -> list[tuple[int, float]]:
        conn = self.db.connect()
        rows = conn.execute(
            """
            SELECT dst_prototype_id, weight
            FROM prototype_edges
            WHERE src_prototype_id = ?
            ORDER BY weight DESC
            LIMIT ?
            """,
            (int(prototype_id), int(top_k)),
        ).fetchall()
        return [(int(r["dst_prototype_id"]), float(r["weight"])) for r in rows]

    def edge_count(self) -> int:
        conn = self.db.connect()
        row = conn.execute("SELECT COUNT(*) AS n FROM prototype_edges").fetchone()
        return int(row["n"])
