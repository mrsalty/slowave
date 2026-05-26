"""Slowave MCP server.

Exposes Slowave as an MCP server so any MCP-aware agent (Cline CLI,
Claude Code, Cursor, ...) can use it as a tool.

Tools exposed:
  - slowave_context     : memory brief for a project
  - slowave_recall      : semantic recall over schemas + episodes
  - slowave_remember    : explicit typed memory
  - slowave_event       : append a session event
  - slowave_session_start / slowave_session_end
  - slowave_consolidate : trigger replay + consolidation
  - slowave_stats       : counts

The server uses an in-process SlowaveEngine. Each tool call opens a fresh
engine against the configured DB and closes it on completion, so the server
is stateless across calls (FAISS indices rebuild from SQLite on each call,
fast for ~1k-100k vectors).

Run directly:
  python -m slowave.mcp.server

Or install and let MCP clients launch it. See `cline_mcp_settings.json` in
the README for registration.
"""
from __future__ import annotations

import os

# macOS: avoid OpenMP-duplication crashes when faiss + torch coexist.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import logging
from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.llm.base import LLMBackendConfig
from slowave.symbolic.encoder import EncoderConfig

log = logging.getLogger(__name__)

DEFAULT_DB = os.environ.get(
    "SLOWAVE_DB", os.path.expanduser("~/.slowave/slowave.db")
)
DEFAULT_MODEL = os.environ.get("SLOWAVE_MODEL", "qwen2.5:7b-instruct")
DEFAULT_OLLAMA_URL = os.environ.get("SLOWAVE_OLLAMA_URL", "http://localhost:11434")
DEFAULT_PROJECT = os.environ.get("SLOWAVE_PROJECT")  # may be None

# ---- OPTION A: Implicit session context (auto-wrap mechanical events) ----
# This enables automatic logging of agent messages without explicit session management.
# Inspired by the observation that agents forget to call slowave_event.
#
# Design:
#   - Each MCP client (agent) starts with no implicit session
#   - Call slowave_session_start_implicit() to create one
#   - All subsequent tool calls auto-log to this implicit session
#   - Call slowave_session_end_implicit() to close and consolidate
#   - Optionally: auto-session could be context-manager or process-lifetime
#
# This bridges the gap between RTK's automatic hooks and Slowave's explicit calls.
_IMPLICIT_SESSIONS: dict[str, str] = {}  # client_id -> session_id


_ENGINES: dict[tuple[bool, bool], SlowaveEngine] = {}


def _get_implicit_session(client_id: str = "default") -> str | None:
    """Get the current implicit session for this client, or None if not started."""
    return _IMPLICIT_SESSIONS.get(client_id)


def _set_implicit_session(session_id: str, client_id: str = "default") -> None:
    """Set the implicit session for this client."""
    _IMPLICIT_SESSIONS[client_id] = session_id


def _clear_implicit_session(client_id: str = "default") -> None:
    """Clear the implicit session for this client."""
    _IMPLICIT_SESSIONS.pop(client_id, None)


def _auto_log_agent_message(
    content: str, message_type: str = "agent_message", engine: SlowaveEngine | None = None
) -> None:
    """Auto-log an agent message to the implicit session if one is active.
    
    This is the mechanical auto-wrapping (Option A). Every agent output is
    automatically logged without the agent needing to remember.
    
    Args:
        content: The agent message content
        message_type: Type of message (e.g., "agent_message", "tool_call")
        engine: Optional SlowaveEngine to use (for performance in testing)
    """
    sid = _get_implicit_session()
    if sid is not None:
        try:
            if engine is None:
                engine = _build_engine(disable_llm=True)
            engine.event_append(session_id=sid, type=message_type, content=content)
            log.debug(f"auto-logged {message_type} to session {sid[:8]}")
        except Exception as e:
            log.warning(f"auto-log failed: {e}")


def _build_engine(disable_llm: bool = False, disable_encoder: bool = False) -> SlowaveEngine:
    """Return a cached engine for this (disable_llm, disable_encoder) combination.

    Engines are expensive to construct (sentence-transformers model load,
    FAISS index rebuild from SQLite). Caching across MCP calls is essential
    for tolerable latency, since FastMCP keeps the server process alive
    across many tool invocations.

    The cache is keyed by the (disable_llm, disable_encoder) flags because
    we sometimes want a cheap LLM-free engine (e.g. for stats) and
    sometimes a full one. All engines share the same SQLite DB so writes
    are visible across them.
    """
    key = (disable_llm, disable_encoder)
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
        llm=LLMBackendConfig(model=DEFAULT_MODEL, base_url=DEFAULT_OLLAMA_URL),
        disable_llm=disable_llm,
        disable_encoder=disable_encoder,
    )
    eng = SlowaveEngine(cfg)
    _ENGINES[key] = eng
    return eng


mcp = FastMCP("slowave")


@mcp.tool()
def slowave_context(project: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Return a memory brief: top schemas (typed claims) to load at task start.

    Call this once at the beginning of a task to prime the agent with prior
    durable memory for the current project.

    Args:
        project: project name (defaults to SLOWAVE_PROJECT env var).
        limit: maximum number of schemas to return.
    """
    eng = _build_engine(disable_llm=True, disable_encoder=True)
    proj = project or DEFAULT_PROJECT
    schemas = eng.context(project=proj, limit=limit)
    return {
        "project": proj,
        "count": len(schemas),
        "schemas": [
            {
                "id": f"sch_{s.id}",
                "content": s.content_text,
                "facets": s.facets,
                "tags": s.tags,
                "status": s.status,
                "salience": s.salience,
                "supports": len(s.supporting_episode_ids),
                "contradicts": len(s.contradicting_episode_ids),
                "needs_review": s.needs_review,
            }
            for s in schemas
        ],
    }


@mcp.tool()
def slowave_recall(
    query: str, top_k: int = 5, evidence: bool = False
) -> dict[str, Any]:
    """Recall memories relevant to a query.

    Returns matching schemas (typed claims), episodes (textual records), and
    optionally raw event citations for evidence drill-through.

    Args:
        query: natural-language query.
        top_k: max episodes returned.
        evidence: if true, include source raw events for provenance.
    """
    eng = _build_engine(disable_llm=True)
    r = eng.recall(query, top_k=top_k, evidence=evidence)
    return {
        "schemas": [
            {
                "id": f"sch_{s.id}",
                "content": s.content_text,
                "facets": s.facets,
                "tags": s.tags,
                "status": s.status,
                "salience": s.salience,
                "supports": len(s.supporting_episode_ids),
                "needs_review": s.needs_review,
            }
            for s in r.schemas
        ],
        "episodes": [
            {
                "id": f"epi_{ep['id']}",
                "content": ep["content_text"],
                "salience": ep["salience"],
            }
            for ep in r.episode_texts
        ],
        "raw_events": [
            {
                "id": f"evt_{e['id']}",
                "type": e["type"],
                "content": e["content"],
            }
            for e in r.raw_events
        ],
    }


@mcp.tool()
def slowave_remember(
    content: str, type: str = "decision", project: str | None = None
) -> dict[str, Any]:
    """Explicitly remember a typed claim.

    Use for explicit, durable memory writes: decisions, preferences,
    constraints. Creates a high-salience event in an ad-hoc session.

    Args:
        content: the claim, as a complete sentence.
        type: one of fact|preference|decision|constraint|procedure|task|
              open_question|warning|lesson|artifact.
        project: project scope.
    """
    eng = _build_engine(disable_llm=True)
    proj = project or DEFAULT_PROJECT
    rid = eng.remember(content=content, type=type, project=proj)
    return {"event_id": f"evt_{rid}", "type": type, "project": proj}


@mcp.tool()
def slowave_event(session_id: str, type: str, content: str) -> dict[str, Any]:
    """Append an event to a session. Call this for EVERY meaningful exchange.

    You MUST call slowave_session_start first to obtain a session_id, then
    call this tool repeatedly throughout the session — do not wait until the
    end. Log every user message, every assistant response, every tool call,
    every decision, and every error. The session_id must match the one
    returned by slowave_session_start.

    Call pattern (required):
        1. session_id = slowave_session_start(...)
        2. slowave_event(session_id, "user_message", "<user turn>")
        3. slowave_event(session_id, "assistant_message", "<your response>")
        4. slowave_event(session_id, "decision", "<any decision made>")
           ... repeat for every turn ...
        5. slowave_session_end(session_id)

    Common type values: user_message, assistant_message, tool_call,
    tool_result, decision, error, task_complete, task_failed.

    Args:
        session_id: id returned from slowave_session_start. Required.
        type: event type tag (use the common ones above).
        content: textual content of the event.
    """
    eng = _build_engine(disable_llm=True)
    rid = eng.event_append(session_id=session_id, type=type, content=content)
    return {"event_id": f"evt_{rid}"}


@mcp.tool()
def slowave_session_start(
    agent: str = "cline-tui", project: str | None = None
) -> dict[str, Any]:
    """Start a new memory session. Returns a session_id. Call this FIRST.

    Call this at the very beginning of every task, before any slowave_event
    calls. Store the returned session_id and pass it to every subsequent
    slowave_event call. End the session with slowave_session_end when done.

    Args:
        agent: identifier for this agent (e.g. "cline-tui", "claude-code").
        project: project name to scope memories (e.g. "my-repo").
    """
    eng = _build_engine(disable_llm=True, disable_encoder=True)
    proj = project or DEFAULT_PROJECT
    sid = eng.session_start(agent=agent, project=proj)
    return {"session_id": sid, "agent": agent, "project": proj}


@mcp.tool()
def slowave_session_end(session_id: str) -> dict[str, Any]:
    """End a session: encode events into episodic memories.

    Fast path — never blocks on LLM. Episodes are formed immediately and
    are available for recall. Schema consolidation happens asynchronously
    via the background worker or an explicit slowave_consolidate call.

    Returns counts of episodes formed.
    """
    eng = _build_engine(disable_llm=True)
    return eng.session_end(session_id, consolidate=False)


# ---- OPTION A: Implicit session tools (auto-wrapping mechanical events) ----

@mcp.tool()
def slowave_session_start_implicit(
    agent: str = "cline-tui", project: str | None = None
) -> dict[str, Any]:
    """Start an implicit session: auto-logs all agent messages without explicit calls.

    OPTION A (auto-wrap mechanical events):
    This is an alternative to the explicit session protocol. Instead of calling
    slowave_event() for every turn, you simply:
      1. Call slowave_session_start_implicit() at task start
      2. All subsequent agent messages are auto-logged
      3. Call slowave_session_end_implicit() at task end

    This solves the adoption problem: agents forget to call slowave_event().
    With implicit sessions, logging is automatic and unavoidable (like RTK).

    Args:
        agent: identifier for this agent (e.g., "cline-tui")
        project: project name to scope memories
    """
    eng = _build_engine(disable_llm=True, disable_encoder=True)
    proj = project or DEFAULT_PROJECT
    sid = eng.session_start(agent=agent, project=proj)
    _set_implicit_session(sid)
    return {
        "session_id": sid,
        "agent": agent,
        "project": proj,
        "mode": "implicit",
        "auto_logging": True,
        "note": "All agent messages will be automatically logged until slowave_session_end_implicit() is called"
    }


@mcp.tool()
def slowave_session_end_implicit() -> dict[str, Any]:
    """End the implicit session and consolidate events into episodes.

    Call this at task end to close the auto-logging session.
    All accumulated events are immediately encoded into episodes.
    """
    sid = _get_implicit_session()
    if sid is None:
        return {
            "error": "No implicit session active",
            "note": "Call slowave_session_start_implicit() first"
        }
    
    eng = _build_engine(disable_llm=True)
    result = eng.session_end(sid, consolidate=False)
    _clear_implicit_session()
    
    return {
        **result,
        "implicit_session_id": sid,
        "note": "Session ended and consolidated"
    }


@mcp.tool()
def slowave_consolidate() -> dict[str, Any]:
    """Manually trigger a replay + LLM consolidation pass.

    Useful between long sessions to surface schemas without waiting for
    session end.
    """
    eng = _build_engine(disable_llm=False)
    stats = eng.replay_engine.replay_once()
    if eng.consolidator is not None:
        protos = eng._prototypes_for_episodes([])
        cs = eng.consolidator.consolidate(prototype_ids=protos)
        return {
            "replay": stats,
            "prototypes_processed": cs.prototypes_processed,
            "schemas_created": cs.schemas_created,
            "schemas_reinforced": cs.schemas_reinforced,
            "schemas_contradicted": cs.schemas_contradicted,
            "schemas_skipped": cs.schemas_skipped,
        }
    return {"replay": stats}


@mcp.tool()
def slowave_stats() -> dict[str, Any]:
    """Return system counts: episodes, prototypes, schemas, edges."""
    eng = _build_engine(disable_llm=True, disable_encoder=True)
    return eng.stats()


def main() -> None:
    """Entry point: run the MCP server on stdio."""
    logging.basicConfig(level=logging.INFO, format="[slowave-mcp] %(message)s")
    mcp.run()


if __name__ == "__main__":
    main()
