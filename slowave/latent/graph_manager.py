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
    # EMA decay factor for transition/coactivation accumulation across
    # replay passes. Each pass contributes (1-decay) to the running
    # estimate; old evidence fades at rate decay.
    #   new_weight = old_weight * decay + current_count * (1 - decay)
    # 0.3 = aggressive learning — 70% from current pass, 30% from past.
    # Single-exposure traces fade quickly unless reinforced (hippocampal LTP).
    accumulate_decay: float = 0.3
    # Homeostatic scaling (synaptic scaling): after each accumulation
    # pass, L1-normalize outgoing edge weights per source prototype
    # to this target sum. Prevents runaway graph densification from
    # Hebbian accumulation — the brain's solution to exactly this problem.
    homeostatic_enabled: bool = True
    homeostatic_target: float = 0.5
    # Relative pruning threshold: edges below this fraction of the
    # max weight for their source prototype are pruned. Replaces
    # absolute prune_below for per-source competition.
    # 0.2 = prune edges weaker than 20% of the strongest edge.
    prune_ratio: float = 0.2


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
            (
                int(src),
                int(dst),
                float(w_similarity),
                float(w_transition),
                float(w_coactivation),
                float(weight),
                int(ts),
            ),
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
        """Accumulate transition probabilities across replay passes via EMA.

        Each pass contributes its evidence while old evidence fades at
        ``accumulate_decay``. Homeostatic normalization runs after
        accumulation to prevent graph densification.
        """
        decay = self.cfg.accumulate_decay
        alpha = 1.0 - decay
        for (src, dst), c in counts.items():
            ws, old_wt, wc = self._get_components(src, dst)
            new_wt = old_wt * decay + float(c) * alpha
            self._upsert_edge(src, dst, w_similarity=ws, w_transition=new_wt, w_coactivation=wc)
        if self.cfg.homeostatic_enabled:
            self._homeostatic_normalize()
        else:
            self.prune_edges()

    def apply_coactivation_counts(self, counts: dict[tuple[int, int], float]) -> None:
        """Accumulate coactivation counts across replay passes via EMA.

        Top-k sparsity filter is applied first, then each surviving edge
        accumulates via EMA. Homeostatic normalization runs after.
        """
        decay = self.cfg.accumulate_decay
        alpha = 1.0 - decay
        by_src: dict[int, list[tuple[int, float]]] = {}
        for (src, dst), c in counts.items():
            if src == dst:
                continue
            by_src.setdefault(int(src), []).append((int(dst), float(c)))

        for src, items in by_src.items():
            items.sort(key=lambda t: t[1], reverse=True)
            for dst, c in items[: self.cfg.top_k_coactivation]:
                ws, wt, old_wc = self._get_components(src, dst)
                new_wc = old_wc * decay + float(c) * alpha
                self._upsert_edge(src, dst, w_similarity=ws, w_transition=wt, w_coactivation=new_wc)
        if self.cfg.homeostatic_enabled:
            self._homeostatic_normalize()
        else:
            self.prune_edges()

    def prune_edges(self) -> None:
        conn = self.db.connect()
        conn.execute("DELETE FROM prototype_edges WHERE weight < ?", (float(self.cfg.prune_below),))
        conn.commit()

    def _homeostatic_normalize(self) -> None:
        """Per-source L1 normalization + relative pruning (synaptic scaling).

        For each source prototype, L1-normalize outgoing edge weights to
        sum ≤ ``homeostatic_target``, then prune edges below
        ``prune_ratio * max_weight`` for that source.

        This is the biological solution to Hebbian densification:
        accumulation strengthens co-active synapses, but homeostatic
        scaling forces competition for a fixed total budget, starving
        weak edges naturally.
        """
        conn = self.db.connect()
        # Fetch all edges grouped by source
        rows = conn.execute("""SELECT src_prototype_id, dst_prototype_id, weight
               FROM prototype_edges
               ORDER BY src_prototype_id, weight DESC""").fetchall()

        if not rows:
            return

        # Group by source
        by_src: dict[int, list[tuple[int, float]]] = {}
        for r in rows:
            src = int(r["src_prototype_id"])
            dst = int(r["dst_prototype_id"])
            w = float(r["weight"])
            by_src.setdefault(src, []).append((dst, w))

        target = float(self.cfg.homeostatic_target)
        ratio = float(self.cfg.prune_ratio)
        updates: list[tuple[float, int, int]] = []  # (new_weight, src, dst)
        deletes: list[tuple[int, int]] = []

        for src, edges in by_src.items():
            total = sum(w for _, w in edges)
            if total <= 0.0:
                continue
            max_w = edges[0][1]  # edges sorted by weight DESC
            threshold = max_w * ratio

            for dst, w in edges:
                # L1-normalize: scale to target sum
                new_w = w * target / total
                if new_w < threshold or new_w < float(self.cfg.prune_below):
                    deletes.append((src, dst))
                else:
                    updates.append((new_w, src, dst))

        # Batch update surviving edges
        for new_w, src, dst in updates:
            conn.execute(
                "UPDATE prototype_edges SET weight = ? "
                "WHERE src_prototype_id = ? AND dst_prototype_id = ?",
                (new_w, src, dst),
            )

        # Batch delete pruned edges
        for src, dst in deletes:
            conn.execute(
                "DELETE FROM prototype_edges "
                "WHERE src_prototype_id = ? AND dst_prototype_id = ?",
                (src, dst),
            )

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
