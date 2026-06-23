"""Tier 1 procedural enforcement: detect when a session followed a procedure.

This module tracks whether a session's activities matched active procedures
and records evidence for feedback-driven learning.

All embedding work (encode, cosine similarity) lives here, not in the
embedding-free procedural.py.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from slowave.core.procedural import ProceduralMemoryStore
from slowave.storage.sqlite_db import SQLiteDB
from slowave.symbolic.encoder import TextEncoder
from slowave.symbolic.raw_log import RawEvent

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


class ProceduralEnforcement:
    """Tier 1 enforcement: track procedure execution and record feedback evidence.

    Attributes:
        store: ProceduralMemoryStore for retrieval and feedback application.
        encoder: TextEncoder for step-to-event similarity matching.
        db: SQLiteDB for raw event queries.
    """

    def __init__(
        self,
        *,
        store: ProceduralMemoryStore,
        encoder: TextEncoder | None,
        db: SQLiteDB,
    ):
        self.store = store
        self.encoder = encoder
        self.db = db

    def compute_step_coverage(
        self,
        procedure_steps: list[str],
        session_events: list[RawEvent],
        match_threshold: float = 0.65,
    ) -> float:
        """Compute fraction of procedure steps matched by session events.

        A step is considered matched if at least one remember:* event has
        cosine similarity >= match_threshold with the step embedding.

        Args:
            procedure_steps: list of declarative step strings
            session_events: list of RawEvent from the session
            match_threshold: similarity threshold for step matching [0.65]

        Returns:
            Fraction of steps matched (0.0 to 1.0)
        """
        if not procedure_steps:
            return 0.0

        # Filter to remember:* events that have embeddings
        relevant = [
            e for e in session_events if e.type.startswith("remember:") and e.embedding is not None
        ]
        if not relevant:
            return 0.0

        # If no encoder, fall back to trivial (no coverage)
        if self.encoder is None:
            return 0.0

        try:
            # Encode all steps
            step_embs = [self.encoder.encode(s) for s in procedure_steps]

            # Count steps that matched at least one event
            matches = 0
            for step_emb in step_embs:
                scores = [_cosine(step_emb, e.embedding) for e in relevant]
                if scores and max(scores) >= match_threshold:
                    matches += 1

            return matches / len(procedure_steps)
        except Exception as e:
            log.warning("compute_step_coverage failed: %s", e)
            return 0.0

    def track(self, session_id: str, goal: str | None, outcome: str) -> dict[str, Any]:
        """Called from session_end to correlate session with procedures.

        Retrieves active procedures matching the session goal, computes
        step coverage against session events, and applies feedback to
        procedures with coverage >= 0.5.

        CRITICAL: Resolves the session's scope_id and threads it into
        apply_feedback() so that procedural_memory_evidence rows are
        scope-attributed. Without this, cross-scope generalization (§5)
        cannot observe scope_id != origin_scope_id.

        Args:
            session_id: session being ended
            goal: goal from session (may be None)
            outcome: "success", "failure", or "partial"

        Returns:
            dict with keys:
              - "tracked": bool (False if no goal)
              - "reason": str (if not tracked)
              - "goal": str
              - "results": list[dict] with procedure_id, coverage, feedback
        """
        if not goal:
            return {"tracked": False, "reason": "no_goal"}

        # Resolve the session's scope_id
        session_scope = self._get_session_scope(session_id)
        events = self._get_session_events(session_id)

        # Retrieve procedures: lexical scoring (no embedding, stays in procedural.py)
        # Pass scope_id so cross-scope affinity is considered in scoring
        procs = self.store.retrieve(goal=goal, scope_id=session_scope, limit=5, mode="default")

        results = []
        for match in procs:
            # Skip low-scoring matches
            if match.score < 0.3:
                continue

            # Compute step coverage using embeddings
            coverage = self.compute_step_coverage(match.procedure.procedure_steps, events)

            feedback = None
            if coverage >= 0.5:
                # Apply feedback only if coverage is sufficient
                feedback = "useful" if outcome == "success" else "wrong"
                self.store.apply_feedback(
                    procedure_id=match.procedure.id,
                    feedback=feedback,
                    outcome=outcome,
                    session_id=session_id,
                    scope_id=session_scope,  # CRITICAL: threads scope into evidence
                    goal=goal,
                )

            results.append(
                {
                    "procedure_id": f"proc_{match.procedure.id}",
                    "coverage": round(coverage, 2),
                    "feedback": feedback,
                }
            )

        return {"tracked": True, "goal": goal, "results": results}

    def _get_session_scope(self, session_id: str) -> str | None:
        """Resolve the session's scope_id from the database.

        Args:
            session_id: session to look up

        Returns:
            scope_id (str or None)
        """
        try:
            conn = self.db.connect()
            row = conn.execute(
                "SELECT scope_id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return row["scope_id"] if row else None
        except Exception as e:
            log.warning("_get_session_scope failed for %s: %s", session_id, e)
            return None

    def _get_session_events(self, session_id: str) -> list[RawEvent]:
        """Retrieve all raw events from a session.

        Args:
            session_id: session to query

        Returns:
            list of RawEvent
        """
        try:
            conn = self.db.connect()
            rows = conn.execute(
                """
                SELECT id, session_id, ts, type, content, metadata_json, embedding, dim
                FROM raw_events
                WHERE session_id = ?
                ORDER BY ts, id
                """,
                (session_id,),
            ).fetchall()

            from slowave.utils.vec import loads_json, unpack_f32

            events = []
            for row in rows:
                emb = None
                if row["embedding"] is not None and row["dim"] is not None:
                    try:
                        emb = unpack_f32(bytes(row["embedding"]), int(row["dim"]))
                    except Exception:
                        pass
                events.append(
                    RawEvent(
                        id=int(row["id"]),
                        session_id=str(row["session_id"]),
                        ts=int(row["ts"]),
                        type=str(row["type"]),
                        content=str(row["content"]),
                        metadata=loads_json(row["metadata_json"]),
                        embedding=emb,
                        dim=int(row["dim"]) if row["dim"] else None,
                    )
                )
            return events
        except Exception as e:
            log.warning("_get_session_events failed for %s: %s", session_id, e)
            return []
