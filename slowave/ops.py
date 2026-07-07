"""Shared operation contracts for the Slowave 5-verb cognitive cycle.

Both the MCP tools (slowave/mcp/tools.py) and the CLI (slowave/cli/main.py)
delegate to these functions so the input/output contract is defined once.
If a field is added, renamed, or removed here, both interfaces update together.

Functions are synchronous; the MCP layer may wrap side-effects in background
tasks for performance, but the contract shape is identical.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from slowave.core.engine import SlowaveEngine


def activate(
    eng: SlowaveEngine,
    *,
    query: str,
    scope: str | None = None,
    goal: str | None = None,
    task_type: str | None = None,
    situation: dict[str, Any] | None = None,
    requirements: list[str] | None = None,
    topics: list[str] | None = None,
    entities: list[str] | None = None,
    mode: str = "strict_scope",
    limit: int = 8,
    session_id: str | None = None,
    agent: str = "cli",
) -> dict[str, Any]:
    """Prime working memory.  Opens a session when session_id is None.

    Returns:
        retrieval_id      – pass to reinforce()
        session_id        – pass to commit()
        rendered          – human-readable brief
        schemas           – [{id, text, activation, reason, source_kind}, ...]
        cold_start        – True when the scope has no memories yet
        cue_terms         – extracted query terms
        suppressed        – gate rejection counts by reason
        activation_trace  – full trace (only when mode="debug")
    """
    situation = situation or {}
    requirements = requirements or []
    topics = topics or []
    entities = entities or []

    if session_id is None:
        session_id = eng.session_start(agent=agent, scope=scope, goal=goal)

    brief = eng.context_brief(
        query=query,
        scope=scope,
        goal=goal,
        task_type=task_type,
        situation=situation,
        requirements=requirements,
        topics=topics,
        entities=entities,
        mode=mode,
        limit=limit,
    )

    context_id = f"ctx_{uuid.uuid4().hex[:12]}"
    scope_id = scope.strip() if scope else None
    scope_kind = scope.split(":", 1)[0] if scope and ":" in scope else None
    cold_start = eng.schemas.count_by_scope(scope_id) == 0 if scope_id else False

    _internal = {
        "memory_ids": [f"sch_{item.schema.id}" for item in brief.items],
        "schemas": [
            {"id": f"sch_{item.schema.id}", "activation": item.activation} for item in brief.items
        ],
    }
    _filtered = [
        {"memory_id": f"sch_{t.schema_id}", "activation": t.activation, "reason": t.reason}
        for t in brief.activation_trace
        if not t.admitted and t.reason != "scope_mismatch"
    ]
    eng.record_context_recall(
        context_id=context_id,
        session_id=session_id,
        scope_id=scope_id,
        scope_kind=scope_kind,
        query=query,
        goal=goal,
        task_type=task_type,
        situation=situation,
        requirements=requirements,
        mode=mode,
        limit=limit,
        topics=topics,
        entities=entities,
        cue_terms=brief.cue_terms,
        suppressed=brief.suppressed,
        response=_internal,
        filtered_items=_filtered,
    )

    schemas_out = [
        {
            "id": f"sch_{item.schema.id}",
            "text": str(item.schema.content_text or "")[:500],
            "activation": round(min(1.0, max(0.0, item.activation)), 4),
            "reason": item.reason,
            "source_kind": str((item.schema.facets or {}).get("source_kind", "")),
        }
        for item in brief.items
    ]

    result: dict[str, Any] = {
        "retrieval_id": context_id,
        "session_id": session_id,
        "rendered": brief.rendered,
        "cold_start": cold_start,
        "schemas": schemas_out,
        "cue_terms": brief.cue_terms,
        "suppressed": brief.suppressed,
    }
    if mode == "debug":
        result["activation_trace"] = [asdict(t) for t in brief.activation_trace]
    return result


def remember(
    eng: SlowaveEngine,
    *,
    content: str,
    memory_type: str = "decision",
    scope: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Encode a durable typed claim.

    Returns:
        stored      – True on success
        event_id    – evt_N
        schema_id   – sch_N (or None)
        memory_type – echoed back
        scope       – echoed back
    """
    if not content or not str(content).strip():
        return {"stored": False, "skipped": True, "reason": "content is empty", "scope": scope}
    rid = eng.remember(content=content, type=memory_type, scope=scope, session_id=session_id)
    schema_id = rid.schema_id if hasattr(rid, "schema_id") and rid.schema_id else None
    return {
        "stored": True,
        "event_id": f"evt_{rid}",
        "schema_id": f"sch_{schema_id}" if schema_id else None,
        "memory_type": memory_type,
        "scope": scope,
    }


def recall(
    eng: SlowaveEngine,
    *,
    query: str,
    scope: str | None = None,
    mode: str = "default",
    top_k: int = 5,
    evidence: bool = False,
) -> dict[str, Any]:
    """Semantic retrieval.

    Returns:
        retrieval_id  – pass to reinforce()
        memories      – [{id, content_text, activation, scope_id, ...}, ...]
        episodes      – raw episode text records (when evidence=True)
        raw_events    – raw event records (when evidence=True)
    """
    result = eng.recall(query, top_k=top_k, evidence=evidence, scope=scope, mode=mode)
    recall_id = f"rec_{uuid.uuid4().hex[:12]}"
    _internal = {
        "memory_ids": [f"sch_{s.id}" for s in result.schemas],
        "schemas": [
            {"id": f"sch_{s.id}", "score": result.schema_activations.get(s.id)}
            for s in result.schemas
        ],
    }
    eng.record_retrieval(
        retrieval_id=recall_id,
        retrieval_type="recall",
        query=query,
        scope_id=scope,
        mode=mode,
        limit=top_k,
        response=_internal,
    )
    memories = [
        {
            "id": f"sch_{s.id}",
            "content_text": str(s.content_text or "")[:500],
            "activation": round(result.schema_activations.get(s.id, 0.0), 4),
            "scope_id": s.scope_id,
            "status": s.status,
            "salience": s.salience,
            "needs_review": s.needs_review,
            "generalization_stage": s.generalization_stage,
        }
        for s in result.schemas
    ]
    return {
        "retrieval_id": recall_id,
        "memories": memories,
        "episodes": result.episode_texts,
        "raw_events": result.raw_events,
    }


def reinforce(
    eng: SlowaveEngine,
    *,
    retrieval_id: str,
    feedback: str = "useful",
    outcome: str = "unknown",
    used_memory_ids: list[str] | None = None,
    irrelevant_memory_ids: list[str] | None = None,
    stale_memory_ids: list[str] | None = None,
    wrong_memory_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Apply feedback to retrieved memories.

    Returns the raw retrieval_feedback dict from the engine.
    """
    return eng.retrieval_feedback(
        retrieval_id=retrieval_id,
        feedback=feedback,
        outcome=outcome,
        used_memory_ids=used_memory_ids,
        irrelevant_memory_ids=irrelevant_memory_ids,
        stale_memory_ids=stale_memory_ids,
        wrong_memory_ids=wrong_memory_ids,
    )


def commit(
    eng: SlowaveEngine,
    *,
    session_id: str,
    outcome: str = "unknown",
) -> dict[str, Any]:
    """Close a session and encode events into episodic memories.

    Returns:
        session_id      – echoed back
        episodes_formed – number of episodic memories created
    """
    result = eng.session_end(session_id, consolidate=False, outcome=outcome)
    return {
        "session_id": session_id,
        "episodes_formed": result.get("episodes_formed", 0),
    }


def stats(eng: SlowaveEngine) -> dict[str, Any]:
    """Return system counts: episodes, prototypes, schemas, procedures, edges."""
    return eng.stats()
