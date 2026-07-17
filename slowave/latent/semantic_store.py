from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

import faiss
import numpy as np

from slowave.latent.types import SemanticPrototype
from slowave.storage.sqlite_db import SQLiteDB
from slowave.utils.vec import pack_f32, to_f32, unpack_f32


@dataclass(frozen=True)
class SemanticStoreConfig:
    dim: int
    faiss_index_path: str = ""


class SemanticStore:
    """Stores semantic prototypes (centroids) + episode->prototype mapping.

    A second FAISS index is used for prototype retrieval.
    """

    def __init__(self, db: SQLiteDB, cfg: SemanticStoreConfig):
        self.db = db
        self.cfg = cfg

        self._index = self._load_or_create_index(cfg)

    def _load_or_create_index(self, cfg: SemanticStoreConfig) -> faiss.Index:
        if cfg.faiss_index_path:
            try:
                loaded = faiss.read_index(cfg.faiss_index_path)
                if loaded.d == cfg.dim and loaded.ntotal > 0:
                    return loaded
            except Exception:
                pass
        base = faiss.IndexFlatIP(cfg.dim)
        return faiss.IndexIDMap2(base)

    def _save_index(self) -> None:
        if self.cfg.faiss_index_path and self._index.ntotal > 0:
            try:
                faiss.write_index(self._index, self.cfg.faiss_index_path)
            except Exception:
                pass

    def reset_faiss_from_db(self) -> None:
        conn = self.db.connect()
        cur = conn.execute("SELECT id, centroid, dim FROM semantic_prototypes ORDER BY id")
        ids: list[int] = []
        vecs: list[np.ndarray] = []
        for row in cur:
            ids.append(int(row["id"]))
            vecs.append(unpack_f32(row["centroid"], int(row["dim"])))
        if not ids:
            return
        X = to_f32(np.stack(vecs, axis=0))
        faiss.normalize_L2(X)
        self._index.reset()
        self._index.add_with_ids(X, np.asarray(ids, dtype=np.int64))
        self._save_index()

    def upsert_prototype(
        self,
        *,
        prototype_id: int | None,
        centroid: np.ndarray,
        support_count: int,
        variance: float,
        ts: int | None = None,
        scale: str = "fine",
        logic_version: str = "0",
    ) -> int:
        """Insert or update a prototype.

        Stage 9: the ``scale`` parameter selects which prototype graph
        the new prototype belongs to ('fine' = CA3-like, 'coarse' =
        CA1-like). Existing rows have their scale preserved across
        updates (we never change a prototype's scale after creation).

        ``logic_version`` is stamped only at creation — like ``scale``,
        an existing prototype's version reflects when it was first formed,
        not when it was last updated by a later-version replay pass.
        """
        if ts is None:
            ts = int(time.time())
        c = to_f32(centroid).reshape(-1)
        if c.size != self.cfg.dim:
            raise ValueError(f"dim mismatch: expected {self.cfg.dim}, got {c.size}")
        conn = self.db.connect()
        if prototype_id is None:
            cur = conn.execute(
                """
                INSERT INTO semantic_prototypes
                    (centroid, dim, support_count, variance, last_updated_ts, scale, logic_version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pack_f32(c),
                    self.cfg.dim,
                    int(support_count),
                    float(variance),
                    int(ts),
                    str(scale),
                    str(logic_version),
                ),
            )
            prototype_id = int(cur.lastrowid or 0)
        else:
            conn.execute(
                """
                UPDATE semantic_prototypes
                SET centroid = ?, support_count = ?, variance = ?, last_updated_ts = ?
                WHERE id = ?
                """,
                (pack_f32(c), int(support_count), float(variance), int(ts), int(prototype_id)),
            )
        conn.commit()

        # update FAISS: easiest for MVP is full rebuild if many updates.
        # but our replay batches are small; we delete+add.
        x = c.reshape(1, -1).copy()
        faiss.normalize_L2(x)
        try:
            self._index.remove_ids(np.asarray([prototype_id], dtype=np.int64))  # type: ignore[arg-type]
        except Exception:
            pass
        self._index.add_with_ids(x, np.asarray([prototype_id], dtype=np.int64))
        self._save_index()
        return int(prototype_id)

    def get(self, prototype_id: int) -> SemanticPrototype:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT * FROM semantic_prototypes WHERE id = ?", (int(prototype_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"No prototype id={prototype_id}")
        return SemanticPrototype(
            id=int(row["id"]),
            centroid=unpack_f32(row["centroid"], int(row["dim"])),
            support_count=int(row["support_count"]),
            variance=float(row["variance"]),
            last_updated_ts=int(row["last_updated_ts"]),
            logic_version=str(row["logic_version"]),
        )

    def get_many(self, prototype_ids: Iterable[int]) -> list[SemanticPrototype]:
        ids = list(dict.fromkeys(int(i) for i in prototype_ids))
        if not ids:
            return []
        placeholders = ",".join(["?"] * len(ids))
        conn = self.db.connect()
        rows = conn.execute(
            f"SELECT * FROM semantic_prototypes WHERE id IN ({placeholders})", tuple(ids)
        ).fetchall()
        by_id = {int(r["id"]): r for r in rows}
        out: list[SemanticPrototype] = []
        for i in ids:
            r = by_id.get(i)
            if r is None:
                continue
            out.append(
                SemanticPrototype(
                    id=int(r["id"]),
                    centroid=unpack_f32(r["centroid"], int(r["dim"])),
                    support_count=int(r["support_count"]),
                    variance=float(r["variance"]),
                    last_updated_ts=int(r["last_updated_ts"]),
                    logic_version=str(r["logic_version"]),
                )
            )
        return out

    def count(self) -> int:
        conn = self.db.connect()
        row = conn.execute("SELECT COUNT(*) AS n FROM semantic_prototypes").fetchone()
        return int(row["n"])

    def map_episode_to_prototype(self, episode_id: int, prototype_id: int) -> None:
        # Stage 9: an episode can map to multiple prototypes (one per scale).
        # The (episode_id, prototype_id) pair is the unique key. Idempotent
        # via OR IGNORE — re-mapping the same pair is a no-op rather than
        # an error.
        conn = self.db.connect()
        conn.execute(
            """
            INSERT OR IGNORE INTO episode_prototype_map (episode_id, prototype_id)
            VALUES (?, ?)
            """,
            (int(episode_id), int(prototype_id)),
        )
        conn.commit()

    def bulk_map_episode_to_prototype(self, pairs: list[tuple[int, int]]) -> None:
        if not pairs:
            return
        conn = self.db.connect()
        conn.executemany(
            """
            INSERT OR IGNORE INTO episode_prototype_map (episode_id, prototype_id)
            VALUES (?, ?)
            """,
            [(int(e), int(p)) for e, p in pairs],
        )
        conn.commit()

    def prototype_for_episode(self, episode_id: int, *, scale: str | None = None) -> int | None:
        """Return one prototype for the given episode.

        Stage 9: when ``scale`` is given, return the prototype at that
        scale. When omitted, return any prototype (prefers 'fine' if
        present, otherwise the first found). This preserves existing
        callers that don't care about scale.
        """
        conn = self.db.connect()
        if scale is None:
            row = conn.execute(
                """
                SELECT m.prototype_id, p.scale
                FROM episode_prototype_map m
                JOIN semantic_prototypes p ON p.id = m.prototype_id
                WHERE m.episode_id = ?
                ORDER BY CASE p.scale WHEN 'fine' THEN 0 ELSE 1 END, m.prototype_id
                LIMIT 1
                """,
                (int(episode_id),),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT m.prototype_id
                FROM episode_prototype_map m
                JOIN semantic_prototypes p ON p.id = m.prototype_id
                WHERE m.episode_id = ? AND p.scale = ?
                LIMIT 1
                """,
                (int(episode_id), str(scale)),
            ).fetchone()
        return None if row is None else int(row["prototype_id"])

    def prototypes_for_episode(self, episode_id: int) -> dict[str, int]:
        """Return {scale: prototype_id} for all scales the episode maps to."""
        conn = self.db.connect()
        rows = conn.execute(
            """
            SELECT m.prototype_id, p.scale
            FROM episode_prototype_map m
            JOIN semantic_prototypes p ON p.id = m.prototype_id
            WHERE m.episode_id = ?
            """,
            (int(episode_id),),
        ).fetchall()
        return {str(r["scale"]): int(r["prototype_id"]) for r in rows}

    def episodes_for_prototypes(
        self,
        prototype_ids: Iterable[int],
        *,
        per_prototype: int = 8,
    ) -> dict[int, list[int]]:
        """Reverse lookup: prototype -> [episode_id, ...].

        Used by the spreading-activation retrieval pipeline to harvest
        episodes from prototypes that were activated through graph
        propagation rather than direct cosine match.

        Per-prototype the most recent episodes are returned (highest
        episode_id), capped at `per_prototype`. Salience-based ordering is
        applied later in the retrieval pipeline once the episodic rows are
        loaded.
        """
        pids = list({int(p) for p in prototype_ids})
        if not pids:
            return {}
        placeholders = ",".join(["?"] * len(pids))
        conn = self.db.connect()
        rows = conn.execute(
            f"""
            SELECT prototype_id, episode_id
            FROM episode_prototype_map
            WHERE prototype_id IN ({placeholders})
            ORDER BY prototype_id ASC, episode_id DESC
            """,
            tuple(pids),
        ).fetchall()
        out: dict[int, list[int]] = {p: [] for p in pids}
        for r in rows:
            p = int(r["prototype_id"])
            bucket = out.setdefault(p, [])
            if len(bucket) < per_prototype:
                bucket.append(int(r["episode_id"]))
        return out

    def search(self, query: np.ndarray, top_k: int) -> tuple[np.ndarray, np.ndarray]:
        q = to_f32(query).reshape(1, -1).copy()
        if q.shape[1] != self.cfg.dim:
            raise ValueError(f"dim mismatch: expected {self.cfg.dim}, got {q.shape[1]}")
        faiss.normalize_L2(q)
        scores, ids = self._index.search(q, top_k)
        return scores.reshape(-1), ids.reshape(-1)

    def search_by_scale(
        self,
        query: np.ndarray,
        *,
        scale: str,
        top_k: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Stage 9: scale-restricted FAISS search.

        The unified FAISS index contains prototypes of every scale.
        We over-fetch (top_k * 4) and then filter to the requested
        scale, returning the top_k that survive. For benchmark-scale
        prototype counts this is cheap and avoids maintaining two
        parallel FAISS indices.
        """
        over_k = max(top_k * 4, 16)
        scores, ids = self.search(query, over_k)
        keep_ids: list[int] = []
        keep_scores: list[float] = []
        # Resolve scales in one query.
        candidate_ids = [int(i) for i in ids if int(i) != -1]
        if not candidate_ids:
            return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.int64)
        placeholders = ",".join(["?"] * len(candidate_ids))
        conn = self.db.connect()
        rows = conn.execute(
            f"SELECT id, scale FROM semantic_prototypes WHERE id IN ({placeholders})",
            tuple(candidate_ids),
        ).fetchall()
        scale_by_id = {int(r["id"]): str(r["scale"]) for r in rows}
        for s, i in zip(scores, ids, strict=False):
            ii = int(i)
            if ii == -1:
                continue
            if scale_by_id.get(ii) == scale:
                keep_ids.append(ii)
                keep_scores.append(float(s))
                if len(keep_ids) >= top_k:
                    break
        return (
            np.asarray(keep_scores, dtype=np.float32),
            np.asarray(keep_ids, dtype=np.int64),
        )
