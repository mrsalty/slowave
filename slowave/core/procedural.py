"""Deterministic procedural memory layer.

Procedural memories are reusable action policies learned or seeded from prior
successful interactions.  They are scope-aware but transferable: scope is a
scoring feature, not a hard namespace wall.

No LLM is used here.  Matching is deterministic lexical/metadata scoring plus
feedback-updated confidence and evidence counts.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from slowave.core.scope import scope_kind
from slowave.storage.sqlite_db import SQLiteDB
from slowave.utils.vec import dumps_json, loads_json


PROCEDURE_STATUSES = ("candidate", "active", "deprecated")


@dataclass(frozen=True)
class ProceduralMemoryConfig:
    enabled: bool = True

    # Retrieval / direct score arbitration
    top_k: int = 2
    min_procedure_score: float = 0.60
    normalize_score: bool = True  # Normalize raw score by active-field weights so threshold is field-count invariant
    include_candidates: bool = True  # Safety net: also surface candidate-status procedures
    include_deprecated: bool = False

    # Score weights
    goal_weight: float = 0.25
    task_type_weight: float = 0.15
    situation_weight: float = 0.15
    requirements_weight: float = 0.15
    trigger_weight: float = 0.15
    confidence_weight: float = 0.20
    success_rate_weight: float = 0.10
    scope_affinity_weight: float = 0.10
    recency_weight: float = 0.05

    # Penalties
    failure_penalty_weight: float = 0.25
    contradiction_penalty_weight: float = 0.30
    requirement_mismatch_penalty_weight: float = 0.30

    # Scope transfer
    allow_cross_scope_transfer: bool = True
    same_scope_affinity: float = 1.0
    related_scope_affinity: float = 0.5
    different_scope_affinity: float = 0.0

    # Generalization stage-aware affinity (v4 §5)
    stage1_cross_affinity: float = 0.5
    stage2_cross_affinity: float = 0.3
    stage3_cross_affinity: float = 1.0

    # Learning
    success_alpha: float = 0.10
    partial_success_alpha: float = 0.04
    failure_beta: float = 0.20
    irrelevant_beta: float = 0.05
    stale_beta: float = 0.15
    wrong_beta: float = 0.30

    # Promotion/demotion
    candidate_min_successes: int = 3
    candidate_min_distinct_scopes: int = 1
    candidate_min_distinct_contexts: int = 2
    active_min_confidence: float = 0.70
    demote_below_confidence: float = 0.55
    deprecate_below_confidence: float = 0.35
    deprecate_min_failures: int = 3

    # Replay hooks (reserved for deterministic replay promotion)
    replay_enabled: bool = True
    replay_min_group_size: int = 3
    replay_min_success_rate: float = 0.75
    replay_cluster_overlap_threshold: float = 0.50
    replay_goal_similarity_threshold: float = 0.70
    replay_situation_similarity_threshold: float = 0.60
    replay_max_candidates_per_run: int = 50

    # Rendering/debug
    render_procedures: bool = True
    max_steps_rendered: int = 8
    debug_score_components: bool = False


@dataclass(frozen=True)
class ProceduralMemory:
    id: int
    origin_scope_id: str | None
    origin_scope_kind: str | None
    goal: str | None
    task_type: str | None
    situation_signature: dict[str, Any]
    requirements: list[str]
    trigger_pattern: list[str]
    procedure_steps: list[str]
    confidence: float
    success_count: int
    failure_count: int
    transfer_count: int
    status: str
    created_at: int
    updated_at: int
    last_used_at: int | None
    generalization_stage: int = 0  # 0=scope-locked, 1/2/3=progressively generalized


@dataclass(frozen=True)
class ProcedureMatch:
    procedure: ProceduralMemory
    score: float
    components: dict[str, float] = field(default_factory=dict)
    reason: str = ""


class ProceduralMemoryStore:
    def __init__(self, db: SQLiteDB, cfg: ProceduralMemoryConfig):
        self.db = db
        self.cfg = cfg

    def create(
        self,
        *,
        goal: str | None,
        task_type: str | None,
        procedure_steps: list[str],
        origin_scope_id: str | None = None,
        origin_scope_kind: str | None = None,
        situation_signature: dict[str, Any] | None = None,
        requirements: list[str] | None = None,
        trigger_pattern: list[str] | None = None,
        confidence: float = 0.5,
        status: str = "candidate",
        success_count: int = 0,
        failure_count: int = 0,
    ) -> int:
        now = int(time.time())
        status = status if status in PROCEDURE_STATUSES else "candidate"
        origin_scope_kind = origin_scope_kind or scope_kind(origin_scope_id)
        
        # Auto-trigger extraction from goal + task_type + steps when caller provides none
        if not trigger_pattern:
            auto_text = " ".join([goal or "", task_type or ""] + procedure_steps)
            trigger_pattern = _terms(auto_text)[:15]  # Limit to 15 terms
        
        conn = self.db.connect()
        cur = conn.execute(
            """
            INSERT INTO procedural_memories (
              origin_scope_id, origin_scope_kind, goal, task_type,
              situation_signature_json, requirements_json, trigger_pattern_json,
              procedure_steps_json, confidence, success_count, failure_count,
              transfer_count, status, created_at, updated_at, last_used_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                origin_scope_id,
                origin_scope_kind,
                goal,
                task_type,
                dumps_json(situation_signature or {}),
                dumps_json([str(x) for x in (requirements or [])]),
                dumps_json([str(x) for x in trigger_pattern]),
                dumps_json([str(x) for x in procedure_steps]),
                float(confidence),
                int(success_count),
                int(failure_count),
                0,
                status,
                now,
                now,
            ),
        )
        pid = int(cur.lastrowid)
        conn.commit()
        return pid

    def get(self, procedure_id: int) -> ProceduralMemory:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT * FROM procedural_memories WHERE id = ?",
            (int(procedure_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"No procedural memory id={procedure_id}")
        return self._row_to_procedure(row)

    def count(self) -> int:
        row = self.db.connect().execute("SELECT COUNT(*) AS n FROM procedural_memories").fetchone()
        return int(row["n"] if row else 0)

    def list(self, *, status: str | None = None, limit: int = 100) -> list[ProceduralMemory]:
        sql = "SELECT * FROM procedural_memories WHERE 1=1"
        args: list[Any] = []
        if status is not None:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY confidence DESC, success_count DESC, updated_at DESC LIMIT ?"
        args.append(int(limit))
        rows = self.db.connect().execute(sql, tuple(args)).fetchall()
        return [self._row_to_procedure(r) for r in rows]

    def retrieve(
        self,
        *,
        scope_id: str | None = None,
        goal: str | None = None,
        task_type: str | None = None,
        situation: dict[str, Any] | None = None,
        requirements: list[str] | None = None,
        query: str | None = None,
        topics: Iterable[str] | None = None,
        entities: Iterable[str] | None = None,
        limit: int | None = None,
        mode: str = "default",
    ) -> list[ProcedureMatch]:
        if not self.cfg.enabled:
            return []
        limit = self.cfg.top_k if limit is None else int(limit)
        statuses = ["active"]
        if self.cfg.include_candidates or mode in {"broad", "debug"}:
            statuses.append("candidate")
        if self.cfg.include_deprecated or mode == "debug":
            statuses.append("deprecated")
        ph = ",".join(["?"] * len(statuses))
        rows = self.db.connect().execute(
            f"SELECT * FROM procedural_memories WHERE status IN ({ph})",
            tuple(statuses),
        ).fetchall()
        matches: list[ProcedureMatch] = []
        for row in rows:
            proc = self._row_to_procedure(row)
            match = self.score(
                proc,
                scope_id=scope_id,
                goal=goal,
                task_type=task_type,
                situation=situation or {},
                requirements=requirements or [],
                query=query,
                topics=topics or [],
                entities=entities or [],
            )
            if match.score >= self.cfg.min_procedure_score or mode == "debug":
                matches.append(match)
        matches.sort(key=lambda m: (m.score, m.procedure.confidence, m.procedure.success_count), reverse=True)
        return matches[:limit]

    def score(
        self,
        proc: ProceduralMemory,
        *,
        scope_id: str | None,
        goal: str | None,
        task_type: str | None,
        situation: dict[str, Any],
        requirements: list[str],
        query: str | None,
        topics: Iterable[str],
        entities: Iterable[str],
    ) -> ProcedureMatch:
        goal_match = _text_similarity(goal, proc.goal)
        task_type_match = _text_similarity(task_type, proc.task_type)
        situation_match = _dict_similarity(situation, proc.situation_signature)
        requirements_match = _list_similarity(requirements, proc.requirements)
        cue_text = " ".join(
            [query or "", goal or "", task_type or "", " ".join(topics), " ".join(entities), " ".join(requirements)]
        )
        trigger_match = _list_similarity(_terms(cue_text), proc.trigger_pattern)
        confidence = max(0.0, min(1.0, float(proc.confidence)))
        total = proc.success_count + proc.failure_count
        success_rate = (proc.success_count / total) if total else confidence
        failure_risk = (proc.failure_count / total) if total else 0.0
        scope_affinity = self._scope_affinity(scope_id, proc)
        recency = _recency_score(proc.last_used_at or proc.updated_at)

        # Penalize only for requirements the caller explicitly asked for that the
        # procedure does not cover.  A procedure that has *more* requirements than
        # the caller specified is not penalized — a subset query is a valid partial
        # match, not a mismatch.
        if requirements:
            caller_terms = set(_terms(requirements))
            proc_terms = set(_terms(proc.requirements))
            unmet = caller_terms - proc_terms  # caller asked for X but proc doesn't cover X
            requirement_mismatch = len(unmet) / max(1, len(caller_terms))
        else:
            requirement_mismatch = 0.0
        contradiction_risk = 1.0 if proc.status == "deprecated" else 0.0

        # ---- raw weighted score ------------------------------------------------
        raw_score = (
            self.cfg.goal_weight * goal_match
            + self.cfg.task_type_weight * task_type_match
            + self.cfg.situation_weight * situation_match
            + self.cfg.requirements_weight * requirements_match
            + self.cfg.trigger_weight * trigger_match
            + self.cfg.confidence_weight * confidence
            + self.cfg.success_rate_weight * success_rate
            + self.cfg.scope_affinity_weight * scope_affinity
            + self.cfg.recency_weight * recency
            - self.cfg.failure_penalty_weight * failure_risk
            - self.cfg.contradiction_penalty_weight * contradiction_risk
            - self.cfg.requirement_mismatch_penalty_weight * requirement_mismatch
        )

        # ---- text-relevance gate -----------------------------------------------
        # Quality signals (confidence, success_rate, recency) are always non-zero
        # for a healthy procedure.  After normalization they can carry the score
        # above the threshold even when there is zero text overlap with the cue.
        # Guard against that: require at least one text dimension to fire.
        text_overlap = trigger_match + goal_match + task_type_match
        if self.cfg.normalize_score and text_overlap == 0.0:
            components = {
                "goal_match": goal_match, "task_type_match": task_type_match,
                "situation_match": situation_match, "requirements_match": requirements_match,
                "trigger_match": trigger_match, "confidence": confidence,
                "success_rate": success_rate, "scope_affinity": scope_affinity,
                "recency": recency, "failure_risk": failure_risk,
                "contradiction_risk": contradiction_risk, "requirement_mismatch": requirement_mismatch,
                "raw_score": round(raw_score, 4),
            }
            reason = ",".join(f"{k}={v:.2f}" for k, v in components.items())
            return ProcedureMatch(procedure=proc, score=0.0, components=components, reason=reason)

        # ---- score normalization ------------------------------------------------
        # The positive weights sum to 1.30, but many are only non-zero when the
        # caller provides structured fields (goal, task_type, situation, etc.).
        # A bare query only activates ~0.50 of positive weight, making it
        # structurally impossible to cross a 0.65 threshold even with a perfect
        # text match.  Normalize by the sum of weights whose corresponding input
        # was actually provided so the threshold is invariant to field count.
        if self.cfg.normalize_score:
            active_pos_weight = (
                (self.cfg.goal_weight          if goal and goal.strip() else 0.0)
                + (self.cfg.task_type_weight   if task_type and task_type.strip() else 0.0)
                + (self.cfg.situation_weight   if situation else 0.0)
                + (self.cfg.requirements_weight if requirements else 0.0)
                + (self.cfg.trigger_weight)                          # trigger always active (built from cue_text)
                + (self.cfg.confidence_weight)                       # always active
                + (self.cfg.success_rate_weight)                     # always active
                + (self.cfg.scope_affinity_weight if scope_id else 0.0)
                + (self.cfg.recency_weight)                          # always active
            )
            # Only normalise the positive signal; penalties are applied after
            # re-scaling so they still bite proportionally.
            pos_raw = (
                self.cfg.goal_weight * goal_match
                + self.cfg.task_type_weight * task_type_match
                + self.cfg.situation_weight * situation_match
                + self.cfg.requirements_weight * requirements_match
                + self.cfg.trigger_weight * trigger_match
                + self.cfg.confidence_weight * confidence
                + self.cfg.success_rate_weight * success_rate
                + self.cfg.scope_affinity_weight * scope_affinity
                + self.cfg.recency_weight * recency
            )
            penalty = (
                self.cfg.failure_penalty_weight * failure_risk
                + self.cfg.contradiction_penalty_weight * contradiction_risk
                + self.cfg.requirement_mismatch_penalty_weight * requirement_mismatch
            )
            normalized_pos = pos_raw / max(active_pos_weight, 1e-9)
            score = max(0.0, normalized_pos - penalty)
        else:
            score = raw_score

        components = {
            "goal_match": goal_match,
            "task_type_match": task_type_match,
            "situation_match": situation_match,
            "requirements_match": requirements_match,
            "trigger_match": trigger_match,
            "confidence": confidence,
            "success_rate": success_rate,
            "scope_affinity": scope_affinity,
            "recency": recency,
            "failure_risk": failure_risk,
            "contradiction_risk": contradiction_risk,
            "requirement_mismatch": requirement_mismatch,
            "raw_score": round(raw_score, 4),
        }
        reason = ",".join(f"{k}={v:.2f}" for k, v in components.items())
        return ProcedureMatch(procedure=proc, score=round(float(score), 4), components=components, reason=reason)

    def apply_feedback(
        self,
        *,
        procedure_id: int,
        feedback: str,
        outcome: str = "unknown",
        context_id: str | None = None,
        session_id: str | None = None,
        scope_id: str | None = None,
        goal: str | None = None,
        task_type: str | None = None,
        situation: dict[str, Any] | None = None,
        requirements: list[str] | None = None,
        used_memory_ids: list[str] | None = None,
    ) -> ProceduralMemory:
        proc = self.get(procedure_id)
        fb = str(feedback or "").strip().lower()
        oc = str(outcome or "unknown").strip().lower()
        success_inc = 0
        failure_inc = 0
        confidence = float(proc.confidence)
        if fb in {"useful", "partially_useful"} and oc in {"success", "partial", "unknown"}:
            alpha = self.cfg.success_alpha if fb == "useful" and oc == "success" else self.cfg.partial_success_alpha
            confidence = confidence + alpha * (1.0 - confidence)
            if oc == "success":
                success_inc = 1
        elif fb == "irrelevant":
            confidence = confidence - self.cfg.irrelevant_beta * confidence
        elif fb == "stale":
            confidence = confidence - self.cfg.stale_beta * confidence
            failure_inc = 1 if oc == "failure" else 0
        elif fb == "wrong":
            confidence = confidence - self.cfg.wrong_beta * confidence
            failure_inc = 1
        elif oc == "failure":
            confidence = confidence - self.cfg.failure_beta * confidence
            failure_inc = 1

        confidence = max(0.0, min(1.0, confidence))
        success_count = proc.success_count + success_inc
        failure_count = proc.failure_count + failure_inc
        status = proc.status
        if status == "candidate" and success_count >= self.cfg.candidate_min_successes and confidence >= self.cfg.active_min_confidence:
            status = "active"
        if status == "active" and confidence < self.cfg.demote_below_confidence:
            status = "candidate"
        if confidence < self.cfg.deprecate_below_confidence or failure_count >= self.cfg.deprecate_min_failures:
            status = "deprecated"

        now = int(time.time())
        transfer_inc = 1 if scope_id and proc.origin_scope_id and scope_id != proc.origin_scope_id else 0
        conn = self.db.connect()
        conn.execute(
            """
            UPDATE procedural_memories
            SET confidence=?, success_count=?, failure_count=?, transfer_count=transfer_count+?,
                status=?, updated_at=?, last_used_at=?
            WHERE id=?
            """,
            (confidence, success_count, failure_count, transfer_inc, status, now, now, int(procedure_id)),
        )
        conn.execute(
            """
            INSERT INTO procedural_memory_evidence (
              procedure_id, context_id, session_id, scope_id, scope_kind, goal, task_type,
              situation_json, requirements_json, outcome, feedback, used_memory_ids_json,
              weight, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(procedure_id), context_id, session_id, scope_id, scope_kind(scope_id), goal, task_type,
                dumps_json(situation or {}), dumps_json(requirements or []), oc, fb,
                dumps_json(used_memory_ids or []), 1.0, now,
            ),
        )
        conn.commit()
        return self.get(procedure_id)

    def promote_candidates_from_feedback(
        self, *, enriched_steps_map: dict[tuple[str, str], list[str]] | None = None
    ) -> dict[str, Any]:
        """Create candidate procedures from repeated successful feedback groups.

        Deterministic v1: group successful/useful feedback by goal + task_type,
        aggregate scopes/requirements/used memory IDs, and create a candidate
        procedure when the group exceeds configured thresholds. No LLM.

        Args:
            enriched_steps_map: optional pre-computed enriched steps, keyed by (goal, task_type).
                                If provided, use these instead of generating generic steps.
        """
        if not self.cfg.replay_enabled:
            return {"enabled": False, "created": []}
        conn = self.db.connect()
        rows = conn.execute(
            """
            SELECT f.*, r.query
            FROM context_feedback_events f
            LEFT JOIN context_recall_events r ON r.context_id = f.context_id
            WHERE f.outcome = 'success'
              AND f.feedback IN ('useful', 'partially_useful')
              AND f.goal IS NOT NULL
            ORDER BY f.created_at ASC
            """
        ).fetchall()
        groups: dict[tuple[str, str], list[Any]] = {}
        for row in rows:
            key = (str(row["goal"] or ""), str(row["task_type"] or ""))
            groups.setdefault(key, []).append(row)

        created: list[dict[str, Any]] = []
        for (goal, task_type), group in groups.items():
            if len(group) < self.cfg.replay_min_group_size:
                continue
            distinct_contexts = {str(r["context_id"]) for r in group if r["context_id"]}
            if len(distinct_contexts) < self.cfg.candidate_min_distinct_contexts:
                continue
            existing = conn.execute(
                "SELECT id FROM procedural_memories WHERE goal = ? AND COALESCE(task_type, '') = ? AND status IN ('candidate','active') LIMIT 1",
                (goal, task_type or ""),
            ).fetchone()
            if existing is not None:
                continue

            requirements = _top_list_values(r["requirements_json"] for r in group)
            used_memory_ids = _top_list_values(r["used_memory_ids_json"] for r in group)
            trigger_terms = _terms(" ".join(str(r["query"] or "") for r in group) + " " + goal + " " + (task_type or ""))[:12]
            scopes = [str(r["scope_id"] or "") for r in group if r["scope_id"]]
            origin_scope = scopes[0] if scopes else None
            situation = _merge_dict_values(r["situation_json"] for r in group)

            # Determine steps: use enriched if available, else fall back to generic
            steps = (enriched_steps_map or {}).get((goal, task_type or ""))
            if not steps:
                steps = self._legacy_generic_steps(used_memory_ids, requirements, goal, task_type)

            pid = self.create(
                origin_scope_id=origin_scope,
                origin_scope_kind=scope_kind(origin_scope),
                goal=goal,
                task_type=task_type or None,
                situation_signature=situation,
                requirements=requirements,
                trigger_pattern=trigger_terms,
                procedure_steps=steps,
                confidence=max(0.5, min(0.95, self.cfg.active_min_confidence - 0.05)),
                status="candidate",
                success_count=len(group),
                failure_count=0,
            )
            created.append({"procedure_id": f"proc_{pid}", "goal": goal, "task_type": task_type, "success_count": len(group)})
        return {"enabled": True, "created": created}
    def _legacy_generic_steps(
        self, used_memory_ids: list[str], requirements: list[str], goal: str, task_type: str | None
    ) -> list[str]:
        """Generate generic placeholder steps (fallback when enrichment unavailable)."""
        steps = []
        if used_memory_ids:
            steps.append(
                "Reuse the memory cluster that was useful before: "
                + ", ".join(used_memory_ids[:6])
                + "."
            )
        if requirements:
            steps.append("Preserve recurring requirements: " + ", ".join(requirements[:6]) + ".")
        steps.append(
            f"Apply this workflow for goal '{goal}'"
            + (f" and task type '{task_type}'" if task_type else "")
            + "."
        )
        return steps

    def _scope_affinity(self, current_scope: str | None, proc: ProceduralMemory) -> float:
        """Compute scope affinity for a procedure, stage-aware (v4 §5).

        Args:
            current_scope: the requester's scope.
            proc: the procedure to score.

        Returns:
            Affinity score [0.0, 1.0], stage-aware.
        """
        if not current_scope or not proc.origin_scope_id:
            return 0.0
        if current_scope == proc.origin_scope_id:
            return self.cfg.same_scope_affinity  # 1.0
        
        # Stage-aware cross-scope affinity
        gs = proc.generalization_stage
        if gs == 0:
            # Stage 0: scope-locked, no cross-scope transfer
            return 0.0
        if gs == 3:
            # Stage 3: universal (learned across all scope kinds)
            return self.cfg.stage3_cross_affinity  # 1.0
        
        # Stages 1–2: depend on scope kind alignment
        same_kind = scope_kind(current_scope) == proc.origin_scope_kind
        if gs == 1:
            return self.cfg.stage1_cross_affinity if same_kind else 0.0
        # gs == 2
        return self.cfg.stage2_cross_affinity

    def set_generalization_stage(self, proc_id: int, stage: int) -> None:
        """Update the generalization stage of a procedure."""
        now = int(time.time())
        conn = self.db.connect()
        conn.execute(
            "UPDATE procedural_memories SET generalization_stage=?, updated_at=? WHERE id=?",
            (int(stage), now, int(proc_id)),
        )
        conn.commit()

    def promote_generalization(self, registry: Any) -> dict[str, Any]:
        """Promote procedures across generalization stages based on evidence.

        Uses procedure-specific thresholds (lower than schema thresholds).
        Requires a ScopeRegistry for active scope counts.

        Args:
            registry: ScopeRegistry instance with scope tracking.

        Returns:
            Dict with promotion stats.
        """
        # Procedure-specific generalization thresholds (v4 §5.3)
        stage1_min_scopes = 2
        stage1_min_sessions = 2
        stage2_min_scopes = 3
        stage2_min_sessions = 2
        stage2_min_breadth = 0.40
        stage3_min_scopes = 4
        stage3_min_sessions = 3
        stage3_min_breadth = 0.60

        conn = self.db.connect()
        procedures = self.list(status="active", limit=10000)
        promoted: dict[int, int] = {}  # proc_id -> new_stage
        
        try:
            total_scopes, total_kinds = registry.active_counts()
        except Exception:
            # Fallback if registry unavailable
            total_scopes = 1
            total_kinds = 1

        for proc in procedures:
            current_stage = proc.generalization_stage
            if current_stage >= 3:
                # Already at max stage
                continue

            # Query cross-scope evidence for this procedure
            evidence_row = conn.execute(
                """
                SELECT COUNT(DISTINCT scope_id) AS distinct_scopes,
                       COUNT(DISTINCT scope_kind) AS distinct_scope_kinds,
                       COUNT(DISTINCT session_id) AS distinct_sessions
                FROM procedural_memory_evidence
                WHERE procedure_id = ? AND outcome = 'success' AND scope_id != ?
                """,
                (proc.id, proc.origin_scope_id),
            ).fetchone()

            if not evidence_row:
                continue

            distinct_scopes = int(evidence_row["distinct_scopes"] or 0)
            distinct_kinds = int(evidence_row["distinct_scope_kinds"] or 0)
            distinct_sessions = int(evidence_row["distinct_sessions"] or 0)

            new_stage = current_stage
            
            # Stage 0 -> 1
            if (
                current_stage == 0
                and distinct_scopes >= stage1_min_scopes
                and distinct_sessions >= stage1_min_sessions
            ):
                new_stage = 1

            # Stage 1 -> 2
            if (
                new_stage == 1
                and distinct_scopes >= stage2_min_scopes
                and distinct_sessions >= stage2_min_sessions
            ):
                breadth = distinct_kinds / max(1, total_kinds)
                if breadth >= stage2_min_breadth:
                    new_stage = 2

            # Stage 2 -> 3
            if (
                new_stage == 2
                and distinct_scopes >= stage3_min_scopes
                and distinct_sessions >= stage3_min_sessions
            ):
                breadth = distinct_kinds / max(1, total_kinds)
                if breadth >= stage3_min_breadth:
                    new_stage = 3

            if new_stage > current_stage:
                promoted[proc.id] = new_stage
                self.set_generalization_stage(proc.id, new_stage)

        return {
            "promoted_count": len(promoted),
            "promoted_map": promoted,
        }

    def _row_to_procedure(self, row: Any) -> ProceduralMemory:

        return ProceduralMemory(
            id=int(row["id"]),
            origin_scope_id=row["origin_scope_id"],
            origin_scope_kind=row["origin_scope_kind"],
            goal=row["goal"],
            task_type=row["task_type"],
            situation_signature=_loads_dict(row["situation_signature_json"]),
            requirements=[str(x) for x in _loads_list(row["requirements_json"])],
            trigger_pattern=[str(x) for x in _loads_list(row["trigger_pattern_json"])],
            procedure_steps=[str(x) for x in _loads_list(row["procedure_steps_json"])],
            confidence=float(row["confidence"]),
            success_count=int(row["success_count"]),
            failure_count=int(row["failure_count"]),
            transfer_count=int(row["transfer_count"]),
            status=str(row["status"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            last_used_at=int(row["last_used_at"]) if row["last_used_at"] is not None else None,
            generalization_stage=int(row["generalization_stage"] or 0),
        )


def _terms(text: str | Iterable[str]) -> list[str]:
    if not isinstance(text, str):
        text = " ".join(str(x) for x in text)
    return list(dict.fromkeys(t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9_/-]{2,}", text or "")))


def _text_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    if str(a).strip().lower() == str(b).strip().lower():
        return 1.0
    return _jaccard(_terms(str(a)), _terms(str(b)))


def _list_similarity(a: Iterable[str], b: Iterable[str]) -> float:
    return _jaccard(_terms(a), _terms(b))


def _dict_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    if not a or not b:
        return 0.0
    parts_a = [f"{k}:{v}" for k, v in sorted(a.items()) if v not in (None, "", [], {})]
    parts_b = [f"{k}:{v}" for k, v in sorted(b.items()) if v not in (None, "", [], {})]
    return _jaccard(_terms(parts_a), _terms(parts_b))


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa = set(str(x).lower() for x in a if str(x).strip())
    sb = set(str(x).lower() for x in b if str(x).strip())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _recency_score(ts: int | None) -> float:
    if not ts:
        return 0.0
    age_days = max(0.0, (time.time() - int(ts)) / 86400.0)
    return 1.0 / (1.0 + age_days / 30.0)


def parse_procedure_ids(ids: list[str] | None) -> list[int]:
    out: list[int] = []
    for mid in ids or []:
        if isinstance(mid, str) and mid.startswith("proc_"):
            try:
                out.append(int(mid[5:]))
            except ValueError:
                pass
    return out


def _loads_list(text: str | None) -> list[Any]:
    if not text:
        return []
    try:
        obj = json.loads(text)
    except Exception:
        return []
    return obj if isinstance(obj, list) else []


def _loads_dict(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        obj = json.loads(text)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _top_list_values(json_texts: Iterable[str | None]) -> list[str]:
    counts: dict[str, int] = {}
    for text in json_texts:
        for value in _loads_list(text):
            key = str(value).strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _merge_dict_values(json_texts: Iterable[str | None]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for text in json_texts:
        obj = _loads_dict(text)
        for key, value in obj.items():
            if key not in merged and value not in (None, "", [], {}):
                merged[key] = value
    return merged
