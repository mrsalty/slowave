"""Slowave MCP server.

Exposes Slowave as an MCP server so any MCP-aware agent (Cline CLI,
Claude Code, Cursor, ...) can use it as a tool.

Tools exposed:
  - slowave_context     : gated working-memory brief for prompt injection
  - slowave_recall      : semantic recall over schemas + episodes
  - slowave_remember    : explicit typed memory
  - slowave_event       : append a session event
  - slowave_session_start / slowave_session_end
  - slowave_stats        : return system counts
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
from slowave.core.paths import default_db_path
from slowave.core.engine import SlowaveEngine
from slowave.symbolic.encoder import EncoderConfig

log = logging.getLogger(__name__)

DEFAULT_DB = default_db_path()
DEFAULT_PROJECT = os.environ.get("SLOWAVE_PROJECT")  # may be None


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


@mcp.tool()
def slowave_context(
    project: str | None = None,
    limit: int = 8,
    query: str | None = None,
    application: str | None = None,
    topics: list[str] | None = None,
    entities: list[str] | None = None,
    mode: str = "default",
) -> dict[str, Any]:
    """Return a gated working-memory brief to load at task/chat start.

    Call this once at the beginning of a task to prime the agent with a small,
    cue-relevant subset of durable memory. ``project`` is optional and only one
    environmental cue; generic chatbots should pass ``query``/``topics``.

    Args:
        project: optional coding/workspace cue (defaults to SLOWAVE_PROJECT env var).
        limit: maximum number of schemas to return.
        query: current user/task text used as the primary memory cue.
        application: calling app/channel, e.g. cline-tui, chatbot, mobile.
        topics: optional high-level topic cues.
        entities: optional salient entity cues.
        mode: default, broad, or debug. Debug includes activation traces.
    """
    eng = _build_engine(disable_encoder=not bool(query or topics or entities),
    )
    proj = project or DEFAULT_PROJECT
    brief = eng.context_brief(
        query=query,
        project=proj,
        application=application,
        topics=topics or [],
        entities=entities or [],
        limit=limit,
        mode=mode,
    )
    return {
        "project": proj,
        "query": query,
        "application": application,
        "topics": topics or [],
        "entities": entities or [],
        "mode": mode,
        "count": len(brief.items),
        "rendered": brief.rendered,
        "cue_terms": brief.cue_terms,
        "suppressed": brief.suppressed,
        "schemas": [
            {
                "id": f"sch_{item.schema.id}",
                "content": item.text,
                "activation": item.activation,
                "reason": item.reason,
                "facets": item.schema.facets,
                "tags": item.schema.tags,
                "status": item.schema.status,
                "salience": item.schema.salience,
                "supports": len(item.schema.supporting_episode_ids),
                "contradicts": len(item.schema.contradicting_episode_ids),
                "needs_review": item.schema.needs_review,
            }
            for item in brief.items
        ],
        "activation_trace": [asdict(t) for t in brief.activation_trace] if mode == "debug" else [],
    }


@mcp.tool()
def slowave_recall(query: str, top_k: int = 5, evidence: bool = False) -> dict[str, Any]:
    """Recall memories relevant to a query.

    Returns matching schemas (typed claims), episodes (textual records), and
    optionally raw event citations for evidence drill-through.

    Args:
        query: natural-language query.
        top_k: max episodes returned.
        evidence: if true, include source raw events for provenance.
    """
    eng = _build_engine()
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
    eng = _build_engine()
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
    eng = _build_engine()
    rid = eng.event_append(session_id=session_id, type=type, content=content)
    return {"event_id": f"evt_{rid}"}


@mcp.tool()
def slowave_session_start(agent: str = "cline-tui", project: str | None = None) -> dict[str, Any]:
    """Start a new memory session. Returns a session_id. Call this FIRST.

    Call this at the very beginning of every task, before any slowave_event
    calls. Store the returned session_id and pass it to every subsequent
    slowave_event call. End the session with slowave_session_end when done.

    Args:
        agent: identifier for this agent (e.g. "cline-tui", "claude-code").
        project: project name to scope memories (e.g. "my-repo").
    """
    eng = _build_engine(disable_encoder=True)
    proj = project or DEFAULT_PROJECT
    sid = eng.session_start(agent=agent, project=proj)
    return {"session_id": sid, "agent": agent, "project": proj}


@mcp.tool()
def slowave_session_end(session_id: str) -> dict[str, Any]:
    """End a session: encode events into episodic memories.

    Fast path — never blocks. Episodes are formed immediately and
    are available for recall. Schema consolidation happens asynchronously
    via the background worker (`slowave worker`) or `slowave consolidate` CLI.

    Returns counts of episodes formed.
    """
    eng = _build_engine()
    return eng.session_end(session_id, consolidate=False)


@mcp.tool()
def slowave_stats() -> dict[str, Any]:
    """Return system counts: episodes, prototypes, schemas, edges."""
    eng = _build_engine(disable_encoder=True)
    return eng.stats()


def main() -> None:
    """Entry point: run the MCP server on stdio."""
    logging.basicConfig(level=logging.INFO, format="[slowave-mcp] %(message)s")
    mcp.run()


if __name__ == "__main__":
    main()
