"""Slowave MCP server.

Exposes Slowave as an MCP server so any MCP-aware agent (Cline CLI,
Claude Code, Cursor, ...) can use it as a tool.

Tools exposed (5-verb cognitive cycle):
  - slowave_activate    : prime working memory; opens implicit session
  - slowave_remember    : explicitly encode a durable typed claim
  - slowave_recall      : semantic retrieval mid-task
  - slowave_reinforce   : strengthen/suppress memories (feedback)
  - slowave_commit      : close the task; form episodes
  - slowave_stats       : return system counts
  - slowave_remember_procedure : store a deterministic workflow

Deleted (hard break from old surface):
  slowave_context, slowave_session_start, slowave_session_end,
  slowave_event, slowave_retrieval_feedback, slowave_context_feedback

Run directly:
  python -m slowave.mcp.server

Or install and let MCP clients launch it. See README for registration.
"""

from __future__ import annotations

import os

# macOS: avoid OpenMP-duplication crashes when faiss + ONNX Runtime coexist.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")

import logging as _logging
_logging.getLogger("huggingface_hub").setLevel(_logging.ERROR)
_logging.getLogger("onnxruntime").setLevel(_logging.ERROR)

import logging
from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP

from slowave.core.config import SlowaveConfig
from slowave.core.paths import default_db_path
from slowave.core.engine import SlowaveEngine
from slowave.symbolic.encoder import EncoderConfig

import atexit
import signal
import sys
import time
import asyncio

log = logging.getLogger(__name__)

DEFAULT_DB = default_db_path()


_ENGINES: dict[tuple[bool], SlowaveEngine] = {}


def _build_engine(disable_encoder: bool = False) -> SlowaveEngine:
    """Return a cached engine for this configuration.

    Engines are expensive to construct (sentence-transformers model load,
    FAISS index rebuild from SQLite). Caching across MCP calls is essential
    for tolerable latency, since FastMCP keeps the server process alive
    across many tool invocations.

    The cache is keyed by the engine mode because we sometimes want a cheap
    encoder-free engine (e.g. for stats) and sometimes a full latent engine.
    All engines share the same SQLite DB so writes are visible across them.
    """
    key = (disable_encoder,)
    eng = _ENGINES.get(key)
    if eng is not None:
        return eng
    db_dir = os.path.dirname(os.path.abspath(DEFAULT_DB))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    cfg = SlowaveConfig(
        db_path=DEFAULT_DB,
        dim=384,
        encoder=EncoderConfig(),
        disable_encoder=disable_encoder,
    )
    eng = SlowaveEngine(cfg)
    _ENGINES[key] = eng
    return eng


mcp = FastMCP("slowave")

# Keys stored in schema facets that are internal to the retrieval engine and
# carry no value for the LLM — omit them from every MCP response to keep
# token counts reasonable.  vsa_vec is a base64-encoded 384-D float32 blob
# (~700 chars) used purely for VSA arithmetic; the other keys are scoring
# bookkeeping that agents cannot act on.
_INTERNAL_FACET_KEYS: frozenset[str] = frozenset({
    "vsa_vec",
})


def _public_facets(facets: dict) -> dict:
    """Return a copy of *facets* with internal/bulky keys removed."""
    return {k: v for k, v in facets.items() if k not in _INTERNAL_FACET_KEYS}


def _dedup_episodes(episodes: list[dict]) -> list[dict]:
    """Return *episodes* with exact-content duplicates removed (first wins)."""
    seen: set[str] = set()
    out: list[dict] = []
    for ep in episodes:
        key = ep.get("content_text") or ep.get("content", "")
        if key not in seen:
            seen.add(key)
            out.append(ep)
    return out


# ---------------------------------------------------------------------------
# Import session infrastructure built in Steps 2 & 4
# ---------------------------------------------------------------------------
from slowave.mcp import session_resolver
from slowave.mcp import session_reaper




# Background task helpers for fire-and-forget recording
async def _bg_record_context_recall(eng, **kwargs):
    """Fire-and-forget background task to record context recall."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: eng.record_context_recall(**kwargs))
    except Exception as e:
        log.warning("_bg_record_context_recall failed: %s", e)


async def _bg_record_retrieval(eng, **kwargs):
    """Fire-and-forget background task to record retrieval."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: eng.record_retrieval(**kwargs))
    except Exception as e:
        log.warning("_bg_record_retrieval failed: %s", e)

@mcp.tool(name="activate")
async def slowave_activate(
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
) -> dict[str, Any]:
    """Prime working memory with relevant context. Opens an implicit session.

    Call this once at the beginning of every task. Spreading activation surfaces
    relevant memories and procedures, and opens a server-side session so you
    never need to call session_start manually.

    The cognitive cycle:
        1. slowave_activate(query, scope, goal, task_type)  <- start here
        2. slowave_remember(content, type, scope)           <- for durable facts
        3. slowave_recall(query)                            <- mid-task lookup
        4. slowave_reinforce(retrieval_id, feedback, ...)   <- after using memories
        5. slowave_commit(scope, outcome)                   <- close the task

    Args:
        query: current task description (required).
        scope: STRONGLY RECOMMENDED for any project work (e.g. \"project:my-repo\").
               Omitting scope causes memories from all scopes to bleed into retrieval.
               Use \"project:<name>\" for project-scoped work, \"user:<id>\" for user profiles.
        goal: 3-6 word verb-noun phrase, e.g. \"implement oauth login\".
        task_type: category, e.g. \"coding\", \"debugging\".
        mode: strict_scope (default), broad, or debug.
              When scope is set, strict_scope hard-isolates to that scope (+ global/profile).
              When scope is None, strict_scope is equivalent to default — no behaviour change.
        limit: max schemas returned (default 8).

    Returns:
        retrieval_id: pass to slowave_reinforce.
        session_id: informational; used automatically by remember/commit.
        rendered: human-readable memory brief.
        schemas: [{id, text, activation, reason, source_kind}, ...].
        procedures: matching workflows.
    """
    import uuid
    try:
        eng = _build_engine(disable_encoder=not bool(query or topics or entities))
        sid = eng.session_start(agent="mcp", scope=scope)
        session_resolver.bind(scope, sid)
        brief = eng.context_brief(
            query=query, scope=scope, goal=goal, task_type=task_type,
            situation=situation or {}, requirements=requirements or [],
            topics=topics or [], entities=entities or [], limit=limit, mode=mode,
        )
        procedure_matches = eng.retrieve_procedures(
            query=query, scope=scope, goal=goal, task_type=task_type,
            situation=situation or {}, requirements=requirements or [],
            topics=topics or [], entities=entities or [], mode=mode,
        )
        scope_id = scope.strip() if scope else None
        memory_count = eng.schemas.count_by_scope(scope_id)
        cold_start = memory_count == 0
        context_id = f"ctx_{uuid.uuid4().hex[:12]}"
        _internal = {
            "memory_ids": [f"sch_{item.schema.id}" for item in brief.items],
            "procedure_ids": [f"proc_{m.procedure.id}" for m in procedure_matches],
            "schemas": [{"id": f"sch_{item.schema.id}", "activation": item.activation} for item in brief.items],
            "procedures": [{"id": f"proc_{m.procedure.id}"} for m in procedure_matches],
        }
        public_schemas = [
            {
                "id": f"sch_{item.schema.id}",
                "text": str(item.schema.content_text or "")[:500],
                "activation": round(min(1.0, max(0.0, item.activation)), 2),
                "reason": item.reason,
                "source_kind": str((item.schema.facets or {}).get("source_kind", "")),
                **({"confidence": item.schema.confidence} if item.schema.confidence < 0.7 else {}),
            }
            for item in brief.items
        ]
        public_procedures = [
            {
                "id": f"proc_{m.procedure.id}",
                "goal": m.procedure.goal,
                "task_type": m.procedure.task_type,
                "trigger_pattern": m.procedure.trigger_pattern,
                "procedure_steps": m.procedure.procedure_steps,
                "confidence": m.procedure.confidence,
                "score": m.score,
            }
            for m in procedure_matches
        ]
        rendered = brief.rendered
        if cold_start:
            scope_label = scope_id if scope_id else "global (no scope set — consider passing scope='project:<name>')"
            hint = (
                f"[cold start] No memories found for scope '{scope_label}'.\n"
                "Recommended on cold start:\n"
                "  1. Check for these files (in order, stop at first found): "
                "README.md, CLAUDE.md. Read the first one that exists.\n"
                "  2. For each fact in that document, ask: would this be useful in any future "
                "interaction within this scope? Can it be inferred as durable and critical — "
                "something a future session could not assume without it? "
                "If yes to both, call slowave_remember() — one call per fact, not one call per group. "
                "Exhaust the document before moving on.\n"
                "  3. If neither file exists, apply the same questions to what is visible "
                "from the current request.\n"
                "  4. Then respond to the user."
            )
            rendered = f"{rendered}\n\n{hint}".lstrip("\n")
        response: dict[str, Any] = {
            "retrieval_id": context_id,
            "session_id": sid,
            "rendered": rendered,
            "cold_start": cold_start,
            "schemas": public_schemas,
            "procedures": public_procedures,
        }
        if cold_start:
            response["suggested_actions"] = ["remember_project_facts"]
            response["cold_start_hints"] = (
                "Memory is empty for this scope. "
                "Consider reading README.md or CLAUDE.md (whichever exists first). "
                "For each fact ask: would this be useful in any future interaction within this scope? "
                "Can it be inferred as durable and critical — something a future session could not assume without it? "
                "If yes to both, call slowave_remember() — one call per fact, not one call per group. "
                "Exhaust the document before moving on. "
                "If neither file exists, apply the same questions to what is visible from the current request. "
                "Then respond to the user."
            )
        if mode == "debug":
            response["activation_trace"] = [asdict(t) for t in brief.activation_trace]
            response["cue_terms"] = brief.cue_terms
        scope_kind_val = scope.split(":", 1)[0] if scope and ":" in scope else ("generic" if scope else None)
        # Phase 1: build filtered_items from activation_trace (admitted=False entries).
        # These are schemas the working-memory gate evaluated but did not select.
        _filtered_items = [
            {
                "memory_id": f"sch_{t.schema_id}",
                "memory_type": "schema",
                "activation": t.activation,
                "reason": t.reason,
            }
            for t in brief.activation_trace
            if not t.admitted
        ]
        asyncio.create_task(_bg_record_context_recall(
            eng, context_id=context_id, session_id=sid, scope_id=scope,
            scope_kind=scope_kind_val, query=query, goal=goal, task_type=task_type,
            situation=situation or {}, requirements=requirements or [], mode=mode,
            limit=limit, topics=topics or [], entities=entities or [],
            cue_terms=brief.cue_terms, suppressed=brief.suppressed, response=_internal,
            filtered_items=_filtered_items,
        ))
        asyncio.create_task(_bg_log_event(eng, sid, "context_query", query))
        return response
    except Exception as e:
        log.error("slowave_activate failed: %s", e, exc_info=True)
        return {"retrieval_id": None, "session_id": None, "rendered": "", "schemas": [], "procedures": [], "error": str(e)}


async def _bg_log_event(eng: SlowaveEngine, session_id: str, event_type: str, content: str) -> None:
    """Fire-and-forget: log a synthetic session event."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: eng.event_append(session_id=session_id, type=event_type, content=content or "[empty]")
        )
    except Exception as e:
        log.warning("_bg_log_event failed: %s", e)


@mcp.tool(name="recall")
async def slowave_recall(
    query: str,
    top_k: int = 5,
    evidence: bool = False,
    scope: str | None = None,
    mode: str = "default",
) -> dict[str, Any]:
    """Semantic retrieval: bring relevant memories into working memory.

    Use for deliberate mid-task lookups when you need specific historical
    context beyond what activate surfaced.

    WARNING: omitting scope returns memories from ALL projects. Always pass
    scope="project:<name>" when working within a specific project.

    Args:
        query: natural-language query.
        top_k: max memories returned (default 5).
        evidence: if true, include source raw events for provenance.
        scope: optional scope filter (e.g. "project:myrepo"). Recommended.
        mode: "default" (active only), "strict_scope" (scope-hard-filtered),
              "broad" (active + needs_review), "debug" (all statuses).

    Returns:
        retrieval_id: pass to slowave_reinforce after using memories.
        memories: list of {id, text, activation, reason, source_kind}.
    """
    import uuid
    try:
        eng = _build_engine()
        r = eng.recall(query, top_k=top_k, evidence=evidence, scope=scope, mode=mode)
        recall_id = f"rec_{uuid.uuid4().hex[:12]}"
        from slowave.mcp.compact import CompactSchema
        _internal_ids = [f"sch_{s.id}" for s in r.schemas]
        _internal_schemas = [
            {"id": f"sch_{s.id}", "score": r.schema_activations.get(s.id),
             "salience": s.salience, "confidence": s.confidence, "content": str(s.content_text or "")[:200]}
            for s in r.schemas
        ]
        asyncio.create_task(_bg_record_retrieval(
            eng, retrieval_id=recall_id, retrieval_type="recall", query=query, mode="recall", limit=top_k,
            response={"memory_ids": _internal_ids, "schemas": _internal_schemas},
        ))
        return {
            "retrieval_id": recall_id,
            "memories": [CompactSchema.from_schema(s, activation=r.schema_activations.get(s.id)).to_dict() for s in r.schemas],
        }
    except Exception as e:
        log.error("slowave_recall failed: %s", e, exc_info=True)
        return {"retrieval_id": None, "memories": [], "error": str(e)}


@mcp.tool(name="remember")
async def slowave_remember(
    content: str,
    type: str = "decision",
    scope: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Explicitly encode a durable typed claim into long-term memory.

    Use for decisions, preferences, constraints, lessons, or any fact that
    should persist across sessions. If called after slowave_activate without
    a session_id, the implicit session is used automatically.

    Args:
        content: the claim, as a complete sentence.
        type: fact|preference|decision|constraint|procedure|task|
              open_question|warning|lesson|artifact.
        scope: optional scope, e.g. \"project:my-repo\".
        session_id: optional; inferred from activate's implicit session if omitted.

    IMPORTANT: Use ONLY for durable knowledge that should persist across sessions:
    decisions, lessons, preferences, constraints, architectural facts, procedures.
    Do NOT store ephemeral task state (current PR, in-progress bug, temp workarounds)
    — that belongs in session events (encoded automatically by activate/commit).
    """
    if not content or not str(content).strip():
        return {"stored": False, "skipped": True, "reason": "content is empty", "scope": scope}
    try:
        eng = _build_engine()
        resolved_sid = session_id or session_resolver.resolve(scope)
        rid = eng.remember(content=content, type=type, scope=scope, session_id=resolved_sid)
        return {"stored": True, "event_id": f"evt_{rid}", "type": type, "scope": scope}
    except Exception as e:
        log.error("slowave_remember failed: %s", e, exc_info=True)
        return {"stored": False, "error": str(e), "type": type, "scope": scope}


@mcp.tool(name="remember_procedure")
async def slowave_remember_procedure(
    procedure_steps: list[str],
    goal: str | None = None,
    task_type: str | None = None,
    scope: str | None = None,
    situation: dict[str, Any] | None = None,
    requirements: list[str] | None = None,
    trigger_pattern: list[str] | None = None,
    confidence: float = 0.7,
    status: str = "active",
) -> dict[str, Any]:
    """Store a deterministic procedural memory / reusable workflow.

    This is a no-LLM seed path for learned or explicit workflows.
    Pass ``scope='project:<name>'`` for project-specific procedures.
    """
    try:
        eng = _build_engine(disable_encoder=True)
        pid = eng.remember_procedure(
            procedure_steps=procedure_steps,
            goal=goal,
            task_type=task_type,
            scope=scope,
            situation=situation or {},
            requirements=requirements or [],
            trigger_pattern=trigger_pattern or [],
            confidence=confidence,
            status=status,
        )
        return {"procedure_id": f"proc_{pid}", "goal": goal, "task_type": task_type, "scope": scope}
    except Exception as e:
        log.error("slowave_remember_procedure failed: %s", e, exc_info=True)
        return {"procedure_id": None, "error": str(e), "goal": goal, "task_type": task_type, "scope": scope}


@mcp.tool(name="reinforce")
async def slowave_reinforce(
    retrieval_id: str,
    feedback: str,
    outcome: str = "unknown",
    used_memory_ids: list[str] | None = None,
    irrelevant_memory_ids: list[str] | None = None,
    stale_memory_ids: list[str] | None = None,
    wrong_memory_ids: list[str] | None = None,
    used_procedure_ids: list[str] | None = None,
    irrelevant_procedure_ids: list[str] | None = None,
    stale_procedure_ids: list[str] | None = None,
    wrong_procedure_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Strengthen or suppress memories based on how useful they were.

    Call after using memories from slowave_activate or slowave_recall.
    goal, task_type, scope, session, situation, requirements are auto-derived
    from the original retrieval snapshot — you only supply the signal.

    Feedback: useful|partially_useful|irrelevant|stale|wrong|missing|too_much_context
    Outcome:  success|partial|failure|unknown

    Args:
        retrieval_id: from slowave_activate or slowave_recall response.
        feedback: quality label for the retrieved memories.
        outcome: result of the downstream task.
        used_memory_ids: schema IDs that were actually relied on.
        irrelevant/stale/wrong_memory_ids: IDs needing penalty or review.
        used/irrelevant/stale/wrong_procedure_ids: same for procedures.
    """
    try:
        eng = _build_engine(disable_encoder=True)
        return eng.retrieval_feedback(
            retrieval_id=retrieval_id,
            feedback=feedback,
            outcome=outcome,
            used_memory_ids=used_memory_ids,
            irrelevant_memory_ids=irrelevant_memory_ids,
            stale_memory_ids=stale_memory_ids,
            wrong_memory_ids=wrong_memory_ids,
            used_procedure_ids=used_procedure_ids,
            irrelevant_procedure_ids=irrelevant_procedure_ids,
            stale_procedure_ids=stale_procedure_ids,
            wrong_procedure_ids=wrong_procedure_ids,
        )
    except Exception as e:
        log.error("slowave_reinforce failed: %s", e, exc_info=True)
        return {"error": str(e), "retrieval_id": retrieval_id}


@mcp.tool(name="commit")
async def slowave_commit(
    outcome: str | None = None,
    scope: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Close the current task and trigger offline memory consolidation.

    Call at the end of every task. If skipped, the idle-session reaper closes
    the session after SLOWAVE_SESSION_IDLE_TIMEOUT seconds (default 3600).

    Args:
        outcome: task result — success|partial|failure|unknown.
        scope: scope used in activate (clears the implicit session binding).
        session_id: from activate response; inferred from scope if omitted.

    Returns:
        session_id: the session that was closed.
        episodes_formed: number of episodic memories created.
    """
    try:
        eng = _build_engine(disable_encoder=True)
        resolved_sid = session_id or session_resolver.resolve(scope)
        if resolved_sid is None:
            return {"session_id": None, "episodes_formed": 0, "warning": "no active session found"}
        outcome_str = outcome or "unknown"
        asyncio.create_task(_bg_log_event(eng, resolved_sid, "task_complete", f"outcome={outcome_str}"))
        await asyncio.sleep(0.05)
        result = eng.session_end(resolved_sid, consolidate=False)
        session_resolver.clear(scope)
        return {"session_id": resolved_sid, "episodes_formed": result.get("episodes_formed", 0)}
    except Exception as e:
        log.error("slowave_commit failed: %s", e, exc_info=True)
        return {"session_id": session_id, "episodes_formed": 0, "error": str(e)}


@mcp.tool(name="stats")
async def slowave_stats() -> dict[str, Any]:
    """Return system counts: episodes, prototypes, schemas, edges."""
    try:
        eng = _build_engine(disable_encoder=True)
        return eng.stats()
    except Exception as e:
        log.error("slowave_stats failed: %s", e, exc_info=True)
        return {"error": str(e), "episodes": 0, "schemas": 0, "procedures": 0}




def main() -> None:
    """Entry point: run the MCP server on stdio.

    Registers signal handlers for graceful shutdown and an idle-timeout
    watchdog.  The watchdog exits the process when no MCP message has been
    received for ``SLOWAVE_MCP_IDLE_TIMEOUT`` seconds (default: 1800 = 30 min).
    This is the primary defence against zombie processes: when Cline / Claude
    Code abandons a connection without closing stdin (because the hub-daemon
    keeps the socket alive), the idle timer fires and the process self-exits.

    Set ``SLOWAVE_MCP_IDLE_TIMEOUT=0`` to disable the watchdog entirely.
    """
    logging.basicConfig(level=logging.INFO, format="[slowave-mcp] %(message)s")

    # ── idle-timeout watchdog ──────────────────────────────────────────────
    # How it works: a daemon thread wakes every 60 s and checks whether
    # _last_activity_ts has been updated.  If the gap exceeds the timeout it
    # calls os._exit() directly — safe to call from a non-main thread and
    # guaranteed to bypass any stuck async event loop.
    _IDLE_TIMEOUT_S = int(os.environ.get("SLOWAVE_MCP_IDLE_TIMEOUT", "1800"))
    _last_activity: list[float] = [float(time.time())]  # mutable cell for thread

    def _touch_activity() -> None:
        """Record that a tool call (or any stdin message) just happened."""
        _last_activity[0] = float(time.time())

    # Patch _build_engine so every tool invocation resets the idle clock.
    _orig_build_engine = _build_engine

    def _build_engine_with_touch(disable_encoder: bool = False) -> SlowaveEngine:
        _touch_activity()
        return _orig_build_engine(disable_encoder=disable_encoder)

    import slowave.mcp.server as _self_module
    _self_module._build_engine = _build_engine_with_touch  # type: ignore[attr-defined]

    if _IDLE_TIMEOUT_S > 0:
        import threading

        def _watchdog() -> None:
            while True:
                time.sleep(60)
                idle = time.time() - _last_activity[0]
                if idle >= _IDLE_TIMEOUT_S:
                    log.info(
                        "slowave-mcp: idle for %.0f s (limit %d s), exiting.",
                        idle,
                        _IDLE_TIMEOUT_S,
                    )
                    _cleanup()
                    os._exit(0)

        t = threading.Thread(target=_watchdog, daemon=True, name="slowave-mcp-watchdog")
        t.start()
        log.info("slowave-mcp: idle watchdog active (timeout=%ds, env SLOWAVE_MCP_IDLE_TIMEOUT)", _IDLE_TIMEOUT_S)

    # ── cleanup helper ─────────────────────────────────────────────────────
    def _cleanup() -> None:
        """Close all cached engines and release resources."""
        if _ENGINES:
            log.info("Cleaning up cached engines...")
            for key, engine in list(_ENGINES.items()):
                try:
                    engine.close()
                except Exception as e:
                    log.warning(f"Error closing engine {key}: {e}")
            _ENGINES.clear()

    # ── signal handlers ────────────────────────────────────────────────────
    def _signal_handler(signum: int, frame: Any) -> None:
        sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        log.info(f"Received signal {sig_name}, shutting down gracefully...")
        _cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _signal_handler)

    atexit.register(_cleanup)

    # ── session-idle reaper (Step 4) ───────────────────────────────────────
    session_reaper.start(build_engine=_build_engine_with_touch, poll_interval_s=120)

    # ── run ────────────────────────────────────────────────────────────────
    try:
        mcp.run()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        _cleanup()
        sys.exit(0)
    except Exception as e:
        log.error(f"MCP server error: {e}", exc_info=True)
        _cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()
