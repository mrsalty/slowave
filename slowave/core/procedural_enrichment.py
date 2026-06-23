"""Tier 2 procedural enrichment: extract and deduplicate procedure steps from remember events.

This module extracts recall-successful remember:* events from sessions and use them to
replace generic placeholder steps in automatically-mined procedures.

All embedding work (encode, cosine dedup) lives here, not in the
embedding-free procedural.py.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from slowave.storage.sqlite_db import SQLiteDB
from slowave.symbolic.encoder import TextEncoder

log = logging.getLogger(__name__)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two float32 vectors."""
    if a.size == 0 or b.size == 0:
        return 0.0
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class ProceduralEnrichment:
    """Tier 2 enrichment: extract and deduplicate content from remember events.

    Attributes:
        encoder: TextEncoder for step deduplication via cosine similarity.
        db: SQLiteDB for raw event queries.
    """

    def __init__(self, *, encoder: TextEncoder | None, db: SQLiteDB):
        self.encoder = encoder
        self.db = db

    def enrich(self, session_ids: list[str]) -> list[str]:
        """Extract remember:* event content from successful sessions.

        Queries raw_events WHERE session_id IN (...) AND type LIKE 'remember:%'
        ORDER BY ts, id; deduplicates via cosine similarity and returns
        deduplicated content strings in arrival order.

        Args:
            session_ids: list of session IDs to extract from.

        Returns:
            List of deduplicated content strings (arrival order preserved).
        """
        if not session_ids:
            return []

        # Safe placeholder construction
        placeholders = ",".join(["?"] * len(session_ids))
        sql = f"""
            SELECT content FROM raw_events 
            WHERE session_id IN ({placeholders}) 
              AND type LIKE 'remember:%'
            ORDER BY ts, id
        """
        try:
            conn = self.db.connect()
            rows = conn.execute(sql, tuple(session_ids)).fetchall()
            contents = [str(row["content"]) for row in rows if row["content"]]
            if not contents:
                return []
            return self._deduplicate_steps(contents, threshold=0.7)
        except Exception as e:
            log.error("enrich query failed: %s", e)
            return []

    def _deduplicate_steps(
        self, candidates: list[str], threshold: float = 0.7
    ) -> list[str]:
        """Deduplicate steps via cosine similarity.

        Clusters candidates by cosine similarity >= threshold, keeps the first
        representative from each cluster, and preserves arrival order.

        Args:
            candidates: list of step strings.
            threshold: cosine similarity threshold for clustering.

        Returns:
            Deduplicated list of steps (arrival order preserved).
        """
        if not candidates:
            return []
        if not self.encoder:
            # No encoder available: return as-is
            return candidates
        if len(candidates) == 1:
            return candidates

        try:
            # Encode all candidates
            embeddings = []
            for candidate in candidates:
                try:
                    emb = self.encoder.encode(candidate)
                    embeddings.append(emb)
                except Exception as e:
                    log.warning("encode failed for '%s': %s", candidate[:50], e)
                    embeddings.append(None)

            # Cluster via cosine similarity
            clusters: dict[int, int] = {}  # representative_idx -> cluster_id
            cluster_counter = 0
            for i, emb_i in enumerate(embeddings):
                if emb_i is None:
                    continue
                if i in clusters:
                    continue
                # Start a new cluster with i as representative
                cluster_id = cluster_counter
                clusters[i] = cluster_id
                cluster_counter += 1

                # Add all subsequent items to this cluster if similar
                for j in range(i + 1, len(embeddings)):
                    if j in clusters or embeddings[j] is None:
                        continue
                    sim = _cosine(emb_i, embeddings[j])
                    if sim >= threshold:
                        clusters[j] = cluster_id

            # Collect representatives (first item in each cluster)
            representatives: dict[int, int] = {}  # cluster_id -> representative_idx
            for idx, cluster_id in clusters.items():
                if cluster_id not in representatives:
                    representatives[cluster_id] = idx

            # Return representatives in arrival order
            result = [
                candidates[idx] for idx in sorted(representatives.values())
            ]
            return result

        except Exception as e:
            log.error("_deduplicate_steps failed: %s", e)
            return candidates
