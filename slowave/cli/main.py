"""Slowave CLI entry point.

Provides the agent-facing surface: session/event/remember/recall/context/show.

Design goals:
- Every command prints either JSON or a compact human-readable form.
- JSON mode is selected with --json (recommended for agent integrations).
- The CLI never calls an LLM: ingest, consolidation, and recall are local.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from typing import Any

# macOS: avoid OpenMP runtime crashes when FAISS, torch, and tokenizers coexist.
# `python -m slowave` sets these in __main__, but the installed console script
# enters here directly.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

import logging as _logging
_logging.getLogger("huggingface_hub").setLevel(_logging.ERROR)
_logging.getLogger("onnxruntime").setLevel(_logging.ERROR)
_logging.getLogger("transformers").setLevel(_logging.ERROR)

import click

from slowave.cli.setup import setup_cmd
from slowave.core.config import SlowaveConfig
from slowave.core.paths import default_db_path
from slowave.core.engine import SlowaveEngine
from slowave.symbolic.encoder import EncoderConfig

DEFAULT_DB = "__DEFAULT_DB__"


def _ensure_db_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _resolve_db_path(db: str) -> str:
    if db == DEFAULT_DB:
        return default_db_path()
    return os.path.expanduser(db)


def _build_engine(db: str, *, disable_encoder: bool = False) -> SlowaveEngine:
    db = _resolve_db_path(db)
    _ensure_db_dir(db)
    cfg = SlowaveConfig(
        db_path=db,
        dim=384,
        encoder=EncoderConfig(),
        disable_encoder=disable_encoder,
    )
    return SlowaveEngine(cfg)


def _print(obj: Any, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(
            obj
            if isinstance(obj, str)
            else json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        )


@click.group()
@click.version_option(package_name="slowave")
@click.option(
    "--db",
    default=DEFAULT_DB,
    show_default="SLOWAVE_DB or ~/.slowave/slowave.db",
    help="SQLite db path override.",
)
@click.option("--json", "as_json", is_flag=True, help="JSON output.")
@click.pass_context
def cli(ctx: click.Context, db: str, as_json: bool) -> None:
    """Slowave: brain-inspired memory for AI agents."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = _resolve_db_path(db)
    ctx.obj["json"] = as_json


@cli.group()
def session() -> None:
    """Session lifecycle."""


@session.command("start")
@click.option("--agent", default="cline-tui")
@click.option("--scope", default=None, help="Scope id, e.g. 'project:my-repo' or 'domain:cooking'.")
@click.pass_context
def session_start(ctx: click.Context, agent: str, scope: str | None) -> None:
    eng = _build_engine(ctx.obj["db"])  # no LLM needed at start
    sid = eng.session_start(agent=agent, scope=scope)
    _print({"session_id": sid}, ctx.obj["json"])
    eng.close()


@session.command("end")
@click.argument("session_id")
@click.option(
    "--consolidate",
    is_flag=True,
    help="Also run replay + latent consolidation synchronously. "
    "Default: encode only; run 'slowave consolidate' separately.",
)
@click.pass_context
def session_end(ctx: click.Context, session_id: str, consolidate: bool) -> None:
    """End a session and encode events into episodic memories.

    Fast by default: no blocking. Use --consolidate only in scripts
    or tests. In production let the background worker handle consolidation.
    """
    eng = _build_engine(ctx.obj["db"])
    stats = eng.session_end(session_id, consolidate=consolidate)
    _print(stats, ctx.obj["json"])
    eng.close()


@cli.command("event")
@click.option("--session", "session_id", required=True)
@click.option("--type", "type_", required=True)
@click.option("--content", required=True)
@click.pass_context
def event_append(ctx: click.Context, session_id: str, type_: str, content: str) -> None:
    """Append an event to a session."""
    eng = _build_engine(ctx.obj["db"])
    rid = eng.event_append(session_id=session_id, type=type_, content=content)
    _print({"event_id": rid}, ctx.obj["json"])
    eng.close()


@cli.command("remember")
@click.argument("content")
@click.option("--type", "type_", default="decision")
@click.option("--scope", default=None, help="Scope id, e.g. 'project:my-repo'.")
@click.pass_context
def remember(ctx: click.Context, content: str, type_: str, scope: str | None) -> None:
    """Explicitly remember a typed claim."""
    eng = _build_engine(ctx.obj["db"])
    rid = eng.remember(content=content, type=type_, scope=scope)
    _print({"event_id": rid, "type": type_}, ctx.obj["json"])
    eng.close()



@cli.command("recall")
@click.argument("query")
@click.option("--top-k", default=5, show_default=True)
@click.option("--evidence", is_flag=True, help="Include raw event citations.")
@click.pass_context
def recall(ctx: click.Context, query: str, top_k: int, evidence: bool) -> None:
    """Recall memories relevant to a query."""
    eng = _build_engine(ctx.obj["db"])
    result = eng.recall(query, top_k=top_k, evidence=evidence)
    payload = {
        "schemas": [asdict(s) for s in result.schemas],
        "episodes": result.episode_texts,
        "raw_events": result.raw_events,
        "expanded_neighbors": {str(k): v for k, v in result.expanded_neighbors.items()},
    }
    if ctx.obj["json"]:
        _print(payload, True)
    else:
        _format_recall_human(payload)
    eng.close()


def _sal_bar(sal: float, width: int = 8, scale: float = 80.0) -> str:
    """Render a compact salience bar.  sal is unbounded; normalise to [0,1] with a soft cap."""
    import math
    norm = 1.0 - math.exp(-sal / scale)
    filled = round(norm * width)
    return "█" * filled + "░" * (width - filled)


def _status_icon(status: str) -> str:
    return {"active": "🟢", "needs_review": "🟡", "superseded": "⚫", "contradicted": "🔴"}.get(
        status, "⚪"
    )


def _format_recall_human(payload: dict[str, Any]) -> None:
    schemas = payload.get("schemas", [])
    episodes = payload.get("episodes", [])
    raw_events = payload.get("raw_events", [])
    divider = "  " + "─" * 54

    # ── Schemas ────────────────────────────────────────────
    click.echo()
    click.echo("  📖  schemas")
    if not schemas:
        click.echo("  (none)")
    for s in schemas:
        sal = float(s.get("salience", 0.0))
        status = s.get("status", "active")
        n_ep = len(s.get("supporting_episode_ids", []))
        tags = s.get("tags") or []
        tag_str = "  #" + " #".join(tags) if tags else ""
        text = (s.get("content_text") or "").replace("\n", " ").strip()
        if len(text) > 120:
            text = text[:120] + "…"
        nr = "  🔔 needs review" if s.get("needs_review") else ""
        click.echo(divider)
        click.echo(
            f"  {_status_icon(status)}  sch_{s['id']}"
            f"  {_sal_bar(sal)}  sal={sal:.0f}"
            f"  {n_ep} ep{'' if n_ep == 1 else 's'}"
            f"{tag_str}{nr}"
        )
        click.echo(f"  {text}")

    # ── Episodes ───────────────────────────────────────────
    if episodes:
        click.echo()
        click.echo("  💬  episodes")
        click.echo(divider)
        for ep in episodes:
            sal = float(ep.get("salience", 0.0))
            ts = ep.get("ts") or ep.get("created_at") or 0
            # ts is a unix timestamp (seconds); convert to YYYY-MM-DD
            try:
                import datetime
                date = datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
            except Exception:
                date = str(ts)[:10] if ts else "—"
            text = (ep.get("content_text") or "").replace("\n", " ").strip()
            # Strip leading [YYYY-MM-DD] date prefix already shown in the date column
            import re as _re
            text = _re.sub(r"^\[\d{4}-\d{2}-\d{2}\]\s*", "", text)
            if len(text) > 100:
                text = text[:100] + "…"
            # Episodes have salience ~0–1 typically; use a tighter scale
            click.echo(f"  epi_{ep['id']}  {date}  {_sal_bar(sal, 6, scale=0.5)}  {text}")

    # ── Raw events ─────────────────────────────────────────
    if raw_events:
        click.echo()
        click.echo("  🗒   evidence")
        click.echo(divider)
        for r in raw_events:
            text = (r.get("content") or "").replace("\n", " ").strip()
            if len(text) > 100:
                text = text[:100] + "…"
            click.echo(f"  evt_{r['id']}  {r.get('type', '')}  {text}")

    click.echo()


@cli.command("context")
@click.option("--scope", default=None, help="Generic scope id, e.g. project:slowave or domain:cooking.")
@click.option("--query", default=None, help="Current task/chat cue for relevance gating.")
@click.option("--goal", default=None, help="Goal-oriented cue for context/procedure recall.")
@click.option("--task-type", default=None, help="Broad activity type, e.g. writing/planning/debugging.")
@click.option("--situation", default=None, help="JSON object with situational metadata.")
@click.option("--requirement", "requirements", multiple=True, help="Requirement/condition cue; can be repeated.")
@click.option(
    "--application",
    default=None,
    help="Calling app/channel cue, e.g. chatbot or cline-tui.",
)
@click.option("--topic", "topics", multiple=True, help="High-level topic cue; can be repeated.")
@click.option("--entity", "entities", multiple=True, help="Salient entity cue; can be repeated.")
@click.option(
    "--mode",
    default="default",
    show_default=True,
    type=click.Choice(["default", "broad", "debug"]),
)
@click.option("--limit", default=10, show_default=True)
@click.pass_context
def context_cmd(
    ctx: click.Context,
    scope: str | None,
    query: str | None,
    goal: str | None,
    task_type: str | None,
    situation: str | None,
    requirements: tuple[str, ...],
    application: str | None,
    topics: tuple[str, ...],
    entities: tuple[str, ...],
    mode: str,
    limit: int,
) -> None:
    """Return a gated working-memory brief for an agent/chatbot prompt."""
    eng = _build_engine(ctx.obj["db"])
    situation_obj = json.loads(situation) if situation else {}
    brief = eng.context_brief(
        query=query,
        scope=scope,
        goal=goal,
        task_type=task_type,
        situation=situation_obj,
        requirements=list(requirements),
        application=application,
        topics=list(topics),
        entities=list(entities),
        mode=mode,
        limit=limit,
    )
    procedures = eng.retrieve_procedures(
        query=query,
        scope=scope,
        goal=goal,
        task_type=task_type,
        situation=situation_obj,
        requirements=list(requirements),
        topics=list(topics),
        entities=list(entities),
        mode=mode,
    )
    if ctx.obj["json"]:
        _print(
            {
                "scope": scope,
                "query": query,
                "goal": goal,
                "task_type": task_type,
                "situation": situation_obj,
                "requirements": list(requirements),
                "application": application,
                "topics": list(topics),
                "entities": list(entities),
                "mode": mode,
                "rendered": brief.rendered,
                "cue_terms": brief.cue_terms,
                "suppressed": brief.suppressed,
                "schemas": [
                    {
                        "id": item.schema.id,
                        "content_text": item.text,
                        "activation": item.activation,
                        "reason": item.reason,
                        "schema": asdict(item.schema),
                    }
                    for item in brief.items
                ],
                "procedures": [
                    {
                        "id": f"proc_{m.procedure.id}",
                        "score": m.score,
                        "reason": m.reason,
                        "procedure": asdict(m.procedure),
                    }
                    for m in procedures
                ],
                "activation_trace": (
                    [asdict(t) for t in brief.activation_trace] if mode == "debug" else []
                ),
            },
            True,
        )
    else:
        click.echo("=== Working Memory Context ===")
        if not brief.items:
            click.echo("  (no memories yet)")
        for item in brief.items:
            s = item.schema
            label = s.facets.get("display_label", "") if isinstance(s.facets, dict) else ""
            label_str = f" [{label}]" if label else ""
            click.echo(
                f"  [sch_{s.id}]{label_str} {item.text}"
                f"  act={item.activation:.3f} status={s.status} sal={s.salience:.3f}"
                f" supports={len(s.supporting_episode_ids)}"
                f" tags={','.join(s.tags)}"
                f" reason={item.reason}" + ("  needs_review" if s.needs_review else "")
            )
        for match in procedures:
            p = match.procedure
            click.echo(f"  [proc_{p.id}] score={match.score:.3f} goal={p.goal} task={p.task_type}")
            for step in p.procedure_steps[: eng.cfg.procedural.max_steps_rendered]:
                click.echo(f"    - {step}")
        if mode == "debug":
            click.echo(f"\nSuppressed: {brief.suppressed}")
        click.echo("\nCite memories as [sch_xxx] or [epi_xxx] when you use them.")
    eng.close()


@cli.command("show")
@click.argument("ref")
@click.pass_context
def show(ctx: click.Context, ref: str) -> None:
    """Show a schema/episode/event by ref (sch_NN, epi_NN, evt_NN)."""
    eng = _build_engine(ctx.obj["db"])
    if ref.startswith("sch_"):
        sid = int(ref[4:])
        try:
            s = eng.get_schema(sid)
            _print(asdict(s), ctx.obj["json"])
        except KeyError:
            _print({"error": "not found"}, ctx.obj["json"])
    elif ref.startswith("epi_"):
        eid = int(ref[4:])
        et = eng.episode_text.get(eid)
        _print(asdict(et) if et else {"error": "not found"}, ctx.obj["json"])
    elif ref.startswith("evt_"):
        eid = int(ref[4:])
        try:
            e = eng.raw_log.get(eid)
            _print(
                {
                    "id": e.id,
                    "session_id": e.session_id,
                    "ts": e.ts,
                    "type": e.type,
                    "content": e.content,
                    "metadata": e.metadata,
                },
                ctx.obj["json"],
            )
        except KeyError:
            _print({"error": "not found"}, ctx.obj["json"])
    else:
        _print({"error": f"unknown ref prefix: {ref}"}, ctx.obj["json"])
    eng.close()


@cli.command("schema")
@click.option("--needs-review", is_flag=True)
@click.option("--limit", default=50, show_default=True)
@click.pass_context
def schema_list(ctx: click.Context, needs_review: bool, limit: int) -> None:
    """List schemas (optionally filtered)."""
    eng = _build_engine(ctx.obj["db"])
    kwargs: dict[str, Any] = {"limit": limit}
    if needs_review:
        kwargs["needs_review"] = True
    items = eng.list_schemas(**kwargs)
    if ctx.obj["json"]:
        _print([asdict(s) for s in items], True)
    else:
        for s in items:
            label = s.facets.get("display_label", "") if isinstance(s.facets, dict) else ""
            label_str = f" [{label}]" if label else ""
            click.echo(
                f"  [sch_{s.id}]{label_str} {s.content_text}"
                f"  status={s.status} sal={s.salience:.3f} supports={len(s.supporting_episode_ids)}"
                f" tags={','.join(s.tags)}" + ("  needs_review" if s.needs_review else "")
            )
    eng.close()


@cli.command("stats")
@click.option("--scope", default=None, help="Filter by scope (e.g., project:myrepo).")
@click.option("--verbose", is_flag=True, help="Detailed breakdown.")
@click.pass_context
def stats_cmd(ctx: click.Context, scope: str | None, verbose: bool) -> None:
    """Print memory and storage statistics."""
    from slowave.cli.output import get_renderer
    import os
    from pathlib import Path
    
    eng = _build_engine(ctx.obj["db"], disable_encoder=True)  # Don't load embeddings
    data = eng.stats()
    
    # Get file size
    db_path = Path(ctx.obj["db"])
    db_size_bytes = db_path.stat().st_size if db_path.exists() else 0
    db_size_mb = db_size_bytes / (1024 * 1024)
    
    # Get health
    health = eng.schema_health()
    eng.close()
    
    as_json = ctx.obj["json"]
    
    if as_json:
        result = {
            "version": "1.0",
            "memory": {
                "episodes": data.get("episodes", 0),
                "schemas": data.get("schemas", 0),
                "procedures": data.get("procedures", 0),
                "prototypes": data.get("prototypes", 0),
                "edges": data.get("edges", 0),
            },
            "storage": {
                "db_path": str(db_path),
                "db_size_bytes": db_size_bytes,
                "db_size_mb": round(db_size_mb, 2),
            },
            "health": health,
        }
        _print(result, True)
    else:
        renderer = get_renderer(use_emoji=False)
        renderer.title("Slowave Stats")
        
        renderer.section("Memory (Stored Schemas)")
        renderer.item("Episodes", f"{data.get('episodes', 0):,}")
        renderer.item("Schemas", f"{data.get('schemas', 0):,}")
        renderer.item("Procedures", f"{data.get('procedures', 0):,}")
        renderer.item("Prototypes", f"{data.get('prototypes', 0):,}")
        renderer.item("Edges", f"{data.get('edges', 0):,}")
        
        renderer.section("Storage")
        renderer.item("Database", str(db_path), dim=True)
        renderer.item("Size", f"{db_size_mb:.1f} MB")
        
        renderer.section("Health")
        active = health.get("active_schemas", 0)
        unique = health.get("active_unique_exact_by_scope", 0)
        dup_ratio = health.get("active_exact_duplicate_ratio", 0.0)
        renderer.item("Active schemas", f"{active:,}")
        renderer.item("Unique (exact)", f"{unique:,}")
        renderer.item("Duplicate ratio", f"{dup_ratio:.1%}")
        
        # Hints
        if data.get("episodes", 0) == 0:
            renderer.hint("No memories yet. Episodes will appear after sessions.")
        if data.get("procedures", 0) == 0:
            renderer.hint("Procedures are empty. They will appear after repeated workflows.")
        
        click.echo()


def _slowave_processes() -> list[dict[str, Any]]:
    """Best-effort local process snapshot for operational hygiene."""
    try:
        out = subprocess.check_output(
            ["ps", "-axo", "pid,ppid,stat,rss,command"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for line in out.splitlines()[1:]:
        parts = line.strip().split(None, 4)
        if len(parts) < 5:
            continue
        pid, ppid, stat, rss, command = parts
        if (
            "slowave-mcp" not in command
            and "slowave worker" not in command
            and "slowave.cli.main" not in command
        ):
            continue
        rows.append(
            {
                "pid": int(pid),
                "ppid": int(ppid),
                "stat": stat,
                "rss_kb": int(rss),
                "command": command,
            }
        )
    return rows


def _worker_health() -> dict[str, Any]:
    """Best-effort health for the background consolidation worker.

    Worker health is independent from feedback/reinforcement health. A running
    worker means Slowave can perform background consolidation. It does not imply
    that MCP clients are sending post-recall feedback.
    """
    processes = _slowave_processes()
    worker_processes = [
        p for p in processes
        if "slowave worker" in p.get("command", "")
    ]
    return {
        "process_detected": bool(worker_processes),
        "process_count": len(worker_processes),
        "processes": worker_processes,
        "warnings": [] if worker_processes else [
            "no background worker process detected; run 'slowave worker' or configure the worker service if you want automatic consolidation"
        ],
    }


def _feedback_health(db_path: str) -> dict[str, Any]:
    """Best-effort feedback/reinforcement health from the local SQLite DB.

    This answers a different question from worker health: whether clients appear
    to send post-recall feedback/reinforcement events after retrieving context.
    """
    import sqlite3
    import time

    path = os.path.abspath(os.path.expanduser(db_path))
    result: dict[str, Any] = {
        "db_path": path,
        "available": False,
        "recall_or_context_calls": 0,
        "remember_calls": 0,
        "feedback_or_reinforcement_calls": 0,
        "last_feedback_ts": None,
        "last_feedback_age_days": None,
        "warnings": [],
    }

    if not os.path.exists(path):
        result["warnings"].append("database does not exist yet")
        return result

    def _has_table(cur: Any, name: str) -> bool:
        cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
        return cur.fetchone() is not None

    def _columns(cur: Any, table: str) -> set[str]:
        try:
            cur.execute(f"PRAGMA table_info({table})")
            return {str(row[1]) for row in cur.fetchall()}
        except Exception:
            return set()

    def _count(cur: Any, sql: str) -> int:
        try:
            cur.execute(sql)
            row = cur.fetchone()
            return int(row[0] or 0) if row else 0
        except Exception:
            return 0

    def _max_ts(cur: Any, table: str, candidates: tuple[str, ...]) -> float | None:
        cols = _columns(cur, table)
        for col in candidates:
            if col not in cols:
                continue
            try:
                cur.execute(f"SELECT MAX({col}) FROM {table}")
                value = cur.fetchone()[0]
                if value is None:
                    continue
                if isinstance(value, (int, float)):
                    return float(value)
                return float(value)
            except Exception:
                continue
        return None

    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        # Best-effort introspection only. Some legacy/broken SQLite schemas can
        # raise "malformed database schema" while reading sqlite_master. This
        # pragma lets diagnostics continue instead of surfacing unreadable schema
        # text in `slowave doctor`.
        try:
            cur.execute("PRAGMA writable_schema=ON")
        except Exception:
            pass
        result["available"] = True

        event_tables = [
            table for table in (
                "raw_events",
                "events",
                "event_log",
                "turn_events",
                "memory_events",
            )
            if _has_table(cur, table)
        ]

        for table in event_tables:
            cols = _columns(cur, table)
            type_col = next((c for c in ("type", "event_type", "kind", "name") if c in cols), None)
            content_col = next((c for c in ("content", "payload", "text") if c in cols), None)
            searchable_col = type_col or content_col
            if not searchable_col:
                continue

            result["recall_or_context_calls"] += _count(
                cur,
                f"SELECT COUNT(*) FROM {table} WHERE lower({searchable_col}) LIKE '%recall%' OR lower({searchable_col}) LIKE '%context%'",
            )
            result["remember_calls"] += _count(
                cur,
                f"SELECT COUNT(*) FROM {table} WHERE lower({searchable_col}) LIKE '%remember%'",
            )
            result["feedback_or_reinforcement_calls"] += _count(
                cur,
                f"SELECT COUNT(*) FROM {table} WHERE lower({searchable_col}) LIKE '%feedback%' OR lower({searchable_col}) LIKE '%reinforce%' OR lower({searchable_col}) LIKE '%suppress%'",
            )

        for table in (
            "feedback",
            "memory_feedback",
            "retrieval_feedback",
            "turn_feedbacks",
        ):
            if not _has_table(cur, table):
                continue
            count = _count(cur, f"SELECT COUNT(*) FROM {table}")
            result["feedback_or_reinforcement_calls"] += count
            ts = _max_ts(cur, table, ("ts", "created_at", "timestamp", "updated_at"))
            if ts is not None:
                current = result["last_feedback_ts"]
                result["last_feedback_ts"] = ts if current is None else max(float(current), ts)

        conn.close()
    except Exception as exc:
        msg = str(exc)
        if "malformed database schema" in msg.lower():
            result["warnings"].append(
                "feedback health could not inspect legacy/malformed SQLite schema; counters unavailable"
            )
        else:
            result["warnings"].append(f"could not inspect feedback health: {msg}")
        return result

    last_ts = result.get("last_feedback_ts")
    if isinstance(last_ts, (int, float)) and last_ts > 0:
        ts = float(last_ts) / 1000.0 if float(last_ts) > 10_000_000_000 else float(last_ts)
        result["last_feedback_age_days"] = round((time.time() - ts) / 86400.0, 2)

    if result["recall_or_context_calls"] > 0 and result["feedback_or_reinforcement_calls"] == 0:
        result["warnings"].append(
            "recall/context activity detected, but no post-recall feedback or reinforcement events were found; this is a client integration issue, not a worker issue"
        )

    return result


def _session_lifecycle_health(db_path: str) -> dict[str, Any]:
    """Best-effort session start/end health from the local SQLite DB."""
    import sqlite3

    path = os.path.abspath(os.path.expanduser(db_path))
    result: dict[str, Any] = {
        "db_path": path,
        "available": False,
        "sessions_started": 0,
        "sessions_committed": 0,
        "warnings": [],
    }

    if not os.path.exists(path):
        result["warnings"].append("database does not exist yet")
        return result

    def _has_table(cur: Any, name: str) -> bool:
        cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
        return cur.fetchone() is not None

    def _columns(cur: Any, table: str) -> set[str]:
        try:
            cur.execute(f"PRAGMA table_info({table})")
            return {str(row[1]) for row in cur.fetchall()}
        except Exception:
            return set()

    def _count(cur: Any, sql: str) -> int:
        try:
            cur.execute(sql)
            row = cur.fetchone()
            return int(row[0] or 0) if row else 0
        except Exception:
            return 0

    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        # Best-effort introspection only. Some legacy/broken SQLite schemas can
        # raise "malformed database schema" while reading sqlite_master. This
        # pragma lets diagnostics continue instead of surfacing unreadable schema
        # text in `slowave doctor`.
        try:
            cur.execute("PRAGMA writable_schema=ON")
        except Exception:
            pass
        result["available"] = True

        for table in ("sessions", "agent_sessions", "memory_sessions"):
            if not _has_table(cur, table):
                continue
            cols = _columns(cur, table)
            result["sessions_started"] = max(
                result["sessions_started"],
                _count(cur, f"SELECT COUNT(*) FROM {table}"),
            )
            if "ended_at" in cols:
                result["sessions_committed"] = max(
                    result["sessions_committed"],
                    _count(cur, f"SELECT COUNT(*) FROM {table} WHERE ended_at IS NOT NULL"),
                )
            elif "closed_at" in cols:
                result["sessions_committed"] = max(
                    result["sessions_committed"],
                    _count(cur, f"SELECT COUNT(*) FROM {table} WHERE closed_at IS NOT NULL"),
                )
            elif "status" in cols:
                result["sessions_committed"] = max(
                    result["sessions_committed"],
                    _count(cur, f"SELECT COUNT(*) FROM {table} WHERE status IN ('ended', 'closed', 'committed')"),
                )

        conn.close()
    except Exception as exc:
        msg = str(exc)
        if "malformed database schema" in msg.lower():
            result["warnings"].append(
                "session lifecycle health could not inspect legacy/malformed SQLite schema; counters unavailable"
            )
        else:
            result["warnings"].append(f"could not inspect session lifecycle health: {msg}")
        return result

    if result["sessions_started"] > 0 and result["sessions_committed"] == 0:
        result["warnings"].append("sessions are started but never ended/committed")
    elif result["sessions_started"] >= 3 and result["sessions_committed"] / max(result["sessions_started"], 1) < 0.5:
        result["warnings"].append("many sessions are started but fewer than half are ended/committed")

    return result


@cli.command("status")
@click.pass_context
def status_cmd(ctx: click.Context) -> None:
    """Print DB, memory-health, and local process status."""
    db = ctx.obj["db"]
    eng = _build_engine(db)
    payload = {
        "db_path": os.path.abspath(os.path.expanduser(db)),
        "db_exists": os.path.exists(os.path.expanduser(db)),
        "stats": eng.stats(),
        "schema_health": eng.schema_health(),
        "processes": _slowave_processes(),
        "worker_health": _worker_health(),
        "session_lifecycle_health": _session_lifecycle_health(db),
        "feedback_health": _feedback_health(db),
    }
    eng.close()
    if ctx.obj["json"]:
        _print(payload, True)
        return
    click.echo(f"DB: {payload['db_path']} ({'exists' if payload['db_exists'] else 'missing'})")
    click.echo(f"Stats: {payload['stats']}")
    h = payload["schema_health"]
    click.echo(
        "Schema health: "
        f"active={h['active_schemas']} unique_exact={h['active_unique_exact_by_scope']} "
        f"dup_rows={h['active_exact_duplicate_rows']} "
        f"dup_ratio={h['active_exact_duplicate_ratio']:.1%} "
        f"status={h['schemas_by_status']}"
    )
    click.echo("Processes:")
    for p in payload["processes"]:
        click.echo(
            f"  pid={p['pid']} ppid={p['ppid']} rss={p['rss_kb']}KB "
            f"stat={p['stat']} {p['command']}"
        )

    wh = payload["worker_health"]
    click.echo(
        "Worker health: "
        f"detected={wh['process_detected']} count={wh['process_count']}"
    )
    sh = payload["session_lifecycle_health"]
    click.echo(
        "Session lifecycle health: "
        f"started={sh['sessions_started']} committed={sh['sessions_committed']}"
    )
    fh = payload["feedback_health"]
    click.echo(
        "Feedback health: "
        f"recall_or_context={fh['recall_or_context_calls']} "
        f"remember={fh['remember_calls']} "
        f"feedback_or_reinforcement={fh['feedback_or_reinforcement_calls']}"
    )


@cli.command("dashboard")
@click.option("--host", default="127.0.0.1", show_default=True, help="HTTP bind host.")
@click.option("--port", default=8765, show_default=True, help="HTTP bind port.")
@click.option("--refresh-ms", default=2000, show_default=True, help="Overview refresh interval.")
@click.option("--allow-actions", is_flag=True, help="Reserved for future mutating actions.")
@click.option("--no-open", is_flag=True, help="Do not open the browser automatically.")
@click.pass_context
def dashboard_cmd(
    ctx: click.Context,
    host: str,
    port: int,
    refresh_ms: int,
    allow_actions: bool,
    no_open: bool,
) -> None:
    """Run the local read-only Slowave web dashboard."""
    from slowave.dashboard.app import run_dashboard

    run_dashboard(
        db_path=ctx.obj["db"],
        host=host,
        port=port,
        refresh_ms=refresh_ms,
        allow_actions=allow_actions,
        open_browser=not no_open,
    )


@cli.command("dedup-schemas")
@click.option("--apply", "apply_changes", is_flag=True, help="Apply cleanup. Default is dry-run.")
@click.pass_context
def dedup_schemas_cmd(ctx: click.Context, apply_changes: bool) -> None:
    """Merge exact duplicate active schemas within each scope."""
    eng = _build_engine(ctx.obj["db"])
    before = eng.schema_health()
    result = eng.dedup_schemas_exact(dry_run=not apply_changes)
    after = eng.schema_health()
    eng.close()
    payload = {"before": before, "dedup": result, "after": after}
    if ctx.obj["json"]:
        _print(payload, True)
        return
    click.echo("Schema deduplication " + ("APPLIED" if apply_changes else "DRY RUN"))
    click.echo(
        f"Before: active={before['active_schemas']} unique_exact={before['active_unique_exact_by_scope']} "
        f"dup_rows={before['active_exact_duplicate_rows']} dup_ratio={before['active_exact_duplicate_ratio']:.1%}"
    )
    click.echo(f"Dedup: {result}")
    click.echo(
        f"After : active={after['active_schemas']} unique_exact={after['active_unique_exact_by_scope']} "
        f"dup_rows={after['active_exact_duplicate_rows']} dup_ratio={after['active_exact_duplicate_ratio']:.1%}"
    )


@cli.command("consolidate")
@click.pass_context
def consolidate_cmd(ctx: click.Context) -> None:
    """Manually trigger a replay + latent consolidation pass."""
    eng = _build_engine(ctx.obj["db"])
    result = eng.consolidate_once()
    _print(result, ctx.obj["json"])
    eng.close()


@cli.command("worker")
@click.option(
    "--interval",
    default=300,
    show_default=True,
    help="Seconds between consolidation passes (simulates sleep cycles).",
)
@click.option(
    "--once",
    is_flag=True,
    help="Run a single consolidation pass then exit (useful for cron/tests).",
)
@click.pass_context
def worker_cmd(ctx: click.Context, interval: int, once: bool) -> None:
    """Background consolidation worker — the sleep simulator.

    Runs replay + latent schema construction on a schedule, decoupled from session
    ingest. Mimics slow-wave sleep: episodes accumulate during waking sessions,
    then are consolidated offline.

    In production: run as a background process or cron job.
    In tests/scripts: use --once to trigger a single pass.

    Examples:
      slowave worker --once                  # one pass, then exit
      slowave worker --interval 600          # consolidate every 10 min
      slowave worker --interval 3600 &       # background hourly consolidation
    """
    import time as _time
    import signal

    eng = _build_engine(ctx.obj["db"])
    stop = False

    def _handle_signal(sig: int, frame: Any) -> None:
        nonlocal stop
        click.echo("\nworker: received signal, stopping after current pass.")
        stop = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    def _run_pass() -> dict[str, Any]:
        return eng.consolidate_once()

    if once:
        result = _run_pass()
        _print(result, ctx.obj["json"])
        eng.close()
        return

    from slowave.utils.spinner import SleepSpinner

    def _fmt_interval(s: int) -> str:
        return f"{s // 60}m" if s >= 60 else f"{s}s"

    click.echo(f"  🧠 worker starting  (interval={_fmt_interval(interval)})  Ctrl-C to stop.")
    while not stop:
        result = _run_pass()
        if ctx.obj["json"]:
            _print(result, True)
        else:
            cs = result.get("consolidation", {})
            ts = __import__("datetime").datetime.now().strftime("%H:%M:%S")
            click.echo(
                f"  🧠 [{ts}]  "
                f"schemas +{cs.get('schemas_created', 0)} "
                f"~{cs.get('schemas_reinforced', 0)} "
                f"skip={cs.get('schemas_skipped', 0)}"
            )
        # rebuild indices so next pass sees fresh state
        eng.refresh_indices()
        spinner = SleepSpinner(interval_s=interval)
        spinner.start()
        for _ in range(interval):
            if stop:
                break
            _time.sleep(1)
        spinner.stop()

    eng.close()
    click.echo("  💤 worker stopped.")





@cli.command("doctor")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
@click.option("--verbose", is_flag=True, help="Verbose diagnostics.")
@click.pass_context
def doctor_cmd(ctx: click.Context, as_json: bool, verbose: bool) -> None:
    """Check the local Slowave environment and report any issues.

    Verifies Python version, core dependencies, the embedding backend,
    SQLite write access, and MCP server availability.
    Exits with code 1 if any check fails (FAIL status).
    """
    from slowave.cli.output import get_renderer, Status
    from slowave.cli.diagnostics import (
        get_runtime_info,
        check_python,
        check_faiss,
        check_onnxruntime,
        check_embedding_backend,
        check_sqlite_write,
        check_mcp_server,
    )
    from slowave.cli.clients import get_client_statuses, summarize_client_status
    from slowave import __version__

    as_json = as_json or ctx.obj["json"]
    renderer = get_renderer(use_emoji=False)

    if as_json:
        # JSON mode
        result = {
            "status": "ok",
            "version": __version__,
            "runtime": {}
        }

        runtime = get_runtime_info(__version__)
        result["runtime_info"] = {
            "python_version": runtime.python_version,
            "executable": runtime.python_executable,
            "db_path": runtime.db_path,
            "config_path": runtime.config_path,
            "slowave_dir": runtime.slowave_dir,
        }

        # Run checks
        checks = {
            "python": check_python(),
            "faiss": check_faiss(),
            "onnxruntime": check_onnxruntime(),
            "embedding_backend": check_embedding_backend(),
            "sqlite_write": check_sqlite_write(),
            "mcp_server": check_mcp_server(),
        }

        result["runtime"] = {
            name: {
                "status": check.status.value,
                "label": check.label,
                "detail": check.detail,
            }
            for name, check in checks.items()
        }

        # Operational checks
        worker = _worker_health()
        session_lifecycle = _session_lifecycle_health(ctx.obj["db"])
        feedback = _feedback_health(ctx.obj["db"])
        result["worker_health"] = worker
        result["session_lifecycle_health"] = session_lifecycle
        result["feedback_health"] = feedback

        # Client checks
        clients = get_client_statuses()
        result["clients"] = {}
        warnings = []
        for source, health in (
            ("WORKER_HEALTH", worker),
            ("SESSION_LIFECYCLE_HEALTH", session_lifecycle),
            ("FEEDBACK_HEALTH", feedback),
        ):
            for warning in health.get("warnings", []):
                warnings.append({
                    "code": source,
                    "message": str(warning),
                })

        for key, client in clients.items():
            status, detail = summarize_client_status(client)
            result["clients"][key] = {
                "name": client.name,
                "status": status.value,
                "detail": detail,
            }
            if status == Status.WARN:
                warnings.append({
                    "code": f"{key.upper()}_INCOMPLETE",
                    "message": f"{client.name}: {detail}",
                })

        # Determine overall status
        has_fail = any(c.status == Status.FAIL for c in checks.values())
        has_warn = any(c.status == Status.WARN for c in checks.values()) or bool(warnings)

        if has_fail:
            result["status"] = "fail"
        elif has_warn:
            result["status"] = "warn"

        result["warnings"] = warnings
        renderer.json(result)

        if has_fail:
            sys.exit(1)
    else:
        # Human-readable mode
        runtime = get_runtime_info(__version__)
        renderer.title("Slowave Doctor", f"v{__version__}")

        renderer.section("Environment")
        renderer.item("Python", runtime.python_version)
        renderer.item("Data dir", runtime.slowave_dir, dim=True)
        renderer.item("Config", runtime.config_path, dim=True)

        # Runtime checks
        renderer.section("Runtime")
        checks = [
            check_python(),
            check_faiss(),
            check_onnxruntime(),
            check_embedding_backend(),
            check_sqlite_write(),
            check_mcp_server(),
        ]

        for check in checks:
            renderer.check(check.label, check.status, check.detail, check.remediation)

        # Operational health
        worker = _worker_health()
        session_lifecycle = _session_lifecycle_health(ctx.obj["db"])
        feedback = _feedback_health(ctx.obj["db"])

        renderer.section("Worker Health")
        renderer.item("Worker process detected", str(worker.get("process_detected", False)))
        renderer.item("Worker process count", f"{worker.get('process_count', 0):,}")

        renderer.section("Session Lifecycle Health")
        renderer.item("Sessions started", f"{session_lifecycle.get('sessions_started', 0):,}")
        renderer.item("Sessions ended/committed", f"{session_lifecycle.get('sessions_committed', 0):,}")

        renderer.section("Feedback Health")
        renderer.item("Recall/context calls", f"{feedback.get('recall_or_context_calls', 0):,}")
        renderer.item("Remember calls", f"{feedback.get('remember_calls', 0):,}")
        renderer.item("Feedback/reinforcement calls", f"{feedback.get('feedback_or_reinforcement_calls', 0):,}")
        age = feedback.get("last_feedback_age_days")
        renderer.item(
            "Last feedback",
            "never" if age is None else f"{age:g} day(s) ago",
        )

        # Client checks
        renderer.section("Clients")
        clients = get_client_statuses()
        warnings_list = []

        for key, client in clients.items():
            status, detail = summarize_client_status(client)
            renderer.check(client.name, status, detail)
            if status == Status.WARN:
                warnings_list.append((client.name, detail))

        # Warnings
        operational_warnings = []
        for label, health in (
            ("Worker", worker),
            ("Session lifecycle", session_lifecycle),
            ("Feedback", feedback),
        ):
            for warning in health.get("warnings", []):
                operational_warnings.append((label, str(warning)))

        if warnings_list or operational_warnings:
            renderer.section("Warnings")
            for label, warning in operational_warnings:
                remediation = None
                if label == "Worker":
                    remediation = "Run: slowave worker --once, or configure the worker service if you want automatic consolidation."
                elif label == "Feedback":
                    if "counters unavailable" in warning:
                        remediation = "Run `slowave status --json` or inspect the SQLite DB schema; this diagnostic is best-effort and does not mean feedback is broken."
                    else:
                        remediation = "Check client lifecycle instructions and post-recall feedback hooks. This is independent from the background worker."
                elif label == "Session lifecycle":
                    if "counters unavailable" in warning:
                        remediation = "Run `slowave status --json` or inspect the SQLite DB schema; this diagnostic is best-effort and does not mean lifecycle hooks are broken."
                    else:
                        remediation = "Check that the client calls session end/commit hooks when a conversation or task finishes."
                renderer.warning(f"{label}: {warning}", remediation)
            for name, detail in warnings_list:
                if "custom instructions" in detail.lower():
                    renderer.warning(
                        f"{name}: {detail}",
                        "Run: slowave setup --dry-run, then slowave setup"
                    )
                else:
                    renderer.warning(f"{name}: {detail}")

        # Summary
        has_fail = any(c.status == Status.FAIL for c in checks)
        has_warn = bool(warnings_list) or bool(operational_warnings)

        if has_fail:
            msg = f"Setup required. {len([c for c in checks if c.status == Status.FAIL])} check(s) failed."
            renderer.summary(False, msg)
            sys.exit(1)
        elif has_warn:
            msg = f"Usable with {len(warnings_list) + len(operational_warnings)} warning(s)."
            renderer.summary(True, msg)
        else:
            renderer.summary(True, "All systems ready.")

@cli.command("uninstall")
@click.option("--dry-run", is_flag=True, help="Preview what would be removed.")
def uninstall_cmd(dry_run: bool) -> None:
    """Remove all Slowave configuration (keeps database by default).

    Removes ONLY Slowave-specific entries: MCP servers, lifecycle blocks,
    hooks, and worker service. Never deletes entire files or breaks configs.
    Database at ~/.slowave/ is preserved — remove manually if desired.
    """
    from slowave.cli.setup import (
        _claude_settings_path, _claude_desktop_config_path, _cline_mcp_settings_path,
        _claude_md_path, _clinerules_path, _read_json, _write_json,
        _MARKER_START, _MARKER_END, _HOOKS_MARKER, _home,
    )
    import platform
    from pathlib import Path

    click.echo(click.style("\nSlowave uninstall", bold=True))
    if dry_run:
        click.echo(click.style("  [DRY RUN]\n", fg="yellow"))

    changes = []
    errors = []

    def safe_remove_from_json(path: Path, remove_fn, desc: str):
        """Safely remove Slowave config from JSON without breaking structure."""
        if not path.exists():
            return
        try:
            cfg = _read_json(path)
            original = json.dumps(cfg, sort_keys=True)
            modified = remove_fn(cfg)
            if modified and json.dumps(cfg, sort_keys=True) != original:
                if not dry_run:
                    _write_json(path, cfg)
                changes.append(desc)
        except Exception as e:
            errors.append(f"{desc}: {str(e)[:100]}")

    def safe_remove_block(path: Path, desc: str):
        """Safely remove lifecycle block between markers."""
        if not path.exists():
            return
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            if _MARKER_START not in content or _MARKER_END not in content:
                return
            start_idx = content.index(_MARKER_START)
            try:
                end_idx = content.index(_MARKER_END, start_idx)
            except ValueError:
                errors.append(f"{desc}: mismatched markers")
                return
            new_content = content[:start_idx] + content[end_idx + len(_MARKER_END):]
            new_content = new_content.lstrip("\n")
            if new_content != content and not dry_run:
                path.write_text(new_content, encoding="utf-8")
            if new_content != content:
                changes.append(desc)
        except Exception as e:
            errors.append(f"{desc}: {str(e)[:100]}")

    # Claude Code - MCP and hooks
    def remove_cc_mcp_hooks(cfg):
        modified = False
        if "slowave" in cfg.get("mcpServers", {}):
            del cfg["mcpServers"]["slowave"]
            modified = True
        # Remove only Slowave hooks, preserve other hooks
        if "hooks" in cfg:
            for event in ["UserPromptSubmit", "Stop"]:
                if event in cfg["hooks"]:
                    orig_len = len(cfg["hooks"][event])
                    cfg["hooks"][event] = [
                        g for g in cfg["hooks"][event]
                        if not any(_HOOKS_MARKER in h.get("command", "") for h in g.get("hooks", []))
                    ]
                    if len(cfg["hooks"][event]) < orig_len:
                        modified = True
                    # Remove empty event arrays
                    if not cfg["hooks"][event]:
                        del cfg["hooks"][event]
            # Remove hooks key only if empty
            if not cfg["hooks"]:
                del cfg["hooks"]
        return modified

    safe_remove_from_json(_claude_settings_path(), remove_cc_mcp_hooks, "Claude Code MCP + hooks")
    safe_remove_block(_claude_md_path(), "Claude Code lifecycle")

    # Claude Desktop - use safe helper
    def remove_cd_mcp(cfg):
        if "slowave" in cfg.get("mcpServers", {}):
            del cfg["mcpServers"]["slowave"]
            return True
        return False

    safe_remove_from_json(_claude_desktop_config_path(), remove_cd_mcp, "Claude Desktop MCP")

    # Cline
    def remove_cline_mcp(cfg):
        if "slowave" in cfg.get("mcpServers", {}):
            del cfg["mcpServers"]["slowave"]
            return True
        return False

    safe_remove_from_json(_cline_mcp_settings_path(), remove_cline_mcp, "Cline MCP")
    safe_remove_block(_clinerules_path(), "Cline lifecycle")

    # Worker
    system = platform.system()
    if not dry_run:
        if system == "Darwin":
            plist = _home() / "Library/LaunchAgents/com.slowave.worker.plist"
            if plist.exists():
                subprocess.run(["launchctl", "unload", str(plist)], capture_output=True, check=False)
                plist.unlink()
                changes.append("launchd worker")
        elif system == "Linux":
            xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(_home() / ".config")))
            svc = xdg / "systemd/user/slowave-worker.service"
            if svc.exists():
                subprocess.run(["systemctl", "--user", "disable", "--now", "slowave-worker"], capture_output=True, check=False)
                svc.unlink()
                changes.append("systemd worker")
        elif system == "Windows":
            try:
                subprocess.run(["powershell", "-Command", "Unregister-ScheduledTask -TaskName SlowaveWorker -Confirm:$false"], capture_output=True, check=False)
                changes.append("Task Scheduler worker")
            except:
                pass
    else:
        changes.append(f"worker ({system})")

    if changes:
        click.echo("  Removed:" if not dry_run else "  Would remove:")
        for c in changes:
            click.echo(f"    - {c}")
    else:
        click.echo("  No configuration found")

    if not dry_run:
        click.echo("\n  ⚠️  Manual steps:")
        click.echo("    - Claude Desktop Custom Instructions (delete the Slowave block if you added it manually)")
        click.echo("    - Package: pipx uninstall slowave")
        click.echo("    - Database (optional): rm -rf ~/.slowave")
    click.echo()


from slowave.cli.cleanup import cleanup_cmd

cli.add_command(setup_cmd)
cli.add_command(cleanup_cmd)


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
