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

import logging as _logging
_logging.getLogger("huggingface_hub").setLevel(_logging.ERROR)
_logging.getLogger("sentence_transformers").setLevel(_logging.ERROR)

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
@click.option("--project", default=None)
@click.pass_context
def session_start(ctx: click.Context, agent: str, project: str | None) -> None:
    eng = _build_engine(ctx.obj["db"])  # no LLM needed at start
    sid = eng.session_start(agent=agent, project=project)
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
@click.option("--project", default=None)
@click.pass_context
def remember(ctx: click.Context, content: str, type_: str, project: str | None) -> None:
    """Explicitly remember a typed claim."""
    eng = _build_engine(ctx.obj["db"])
    rid = eng.remember(content=content, type=type_, project=project)
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


def _format_recall_human(payload: dict[str, Any]) -> None:
    schemas = payload.get("schemas", [])
    episodes = payload.get("episodes", [])
    raw_events = payload.get("raw_events", [])
    click.echo("=== Schemas ===")
    if not schemas:
        click.echo("  (none yet)")
    for s in schemas:
        click.echo(
            f"  [sch_{s['id']}] {s['content_text']}"
            f"  status={s.get('status', 'active')} sal={float(s.get('salience', 0.0)):.3f}"
            f" tags={','.join(s.get('tags', []))}"
            f" supports={len(s.get('supporting_episode_ids', []))}"
            + ("  needs_review" if s.get("needs_review") else "")
        )
    click.echo("\n=== Episodes ===")
    for ep in episodes:
        text = (ep.get("content_text") or "").replace("\n", " ")
        if len(text) > 160:
            text = text[:160] + "..."
        click.echo(f"  [epi_{ep['id']}] (sal={ep['salience']:.3f}) {text}")
    if raw_events:
        click.echo("\n=== Raw events (evidence) ===")
        for r in raw_events:
            text = (r.get("content") or "").replace("\n", " ")
            if len(text) > 160:
                text = text[:160] + "..."
            click.echo(f"  [evt_{r['id']}] {r['type']}: {text}")


@cli.command("context")
@click.option("--project", default=None)
@click.option("--query", default=None, help="Current task/chat cue for relevance gating.")
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
    project: str | None,
    query: str | None,
    application: str | None,
    topics: tuple[str, ...],
    entities: tuple[str, ...],
    mode: str,
    limit: int,
) -> None:
    """Return a gated working-memory brief for an agent/chatbot prompt."""
    eng = _build_engine(ctx.obj["db"])
    brief = eng.context_brief(
        query=query,
        project=project,
        application=application,
        topics=list(topics),
        entities=list(entities),
        mode=mode,
        limit=limit,
    )
    if ctx.obj["json"]:
        _print(
            {
                "project": project,
                "query": query,
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
@click.pass_context
def stats_cmd(ctx: click.Context) -> None:
    """Print system stats."""
    eng = _build_engine(ctx.obj["db"])
    _print(eng.stats(), ctx.obj["json"])
    eng.close()


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
        f"active={h['active_schemas']} unique_exact={h['active_unique_exact_by_project']} "
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
    """Merge exact duplicate active schemas within each project namespace."""
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
        f"Before: active={before['active_schemas']} unique_exact={before['active_unique_exact_by_project']} "
        f"dup_rows={before['active_exact_duplicate_rows']} dup_ratio={before['active_exact_duplicate_ratio']:.1%}"
    )
    click.echo(f"Dedup: {result}")
    click.echo(
        f"After : active={after['active_schemas']} unique_exact={after['active_unique_exact_by_project']} "
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

    click.echo(f"worker: starting (interval={interval}s). Ctrl-C or SIGTERM to stop.")
    while not stop:
        result = _run_pass()
        if ctx.obj["json"]:
            _print(result, True)
        else:
            cs = result.get("consolidation", {})
            click.echo(
                f"[{__import__('datetime').datetime.now().isoformat(timespec='seconds')}] "
                f"consolidation: created={cs.get('schemas_created', 0)} "
                f"reinforced={cs.get('schemas_reinforced', 0)} "
                f"skipped={cs.get('schemas_skipped', 0)}"
            )
        # rebuild indices so next pass sees fresh state
        eng.refresh_indices()
        for _ in range(interval):
            if stop:
                break
            _time.sleep(1)

    eng.close()
    click.echo("worker: stopped.")





@cli.command("doctor")
def doctor_cmd() -> None:
    """Check the local Slowave environment and report any issues.

    Verifies Python version, core dependencies, the embedding backend,
    SQLite write access, and MCP server availability. Exits with code 1
    if any check fails.
    """
    import sys
    import tempfile
    import shutil

    ok = True

    def _check(label, passed, detail=""):
        nonlocal ok
        icon = "\u2713" if passed else "\u2717"
        msg = "  " + icon + "  " + label
        if detail:
            msg += "\n       " + detail
        click.echo(msg)
        if not passed:
            ok = False

    click.echo("Slowave doctor\n")

    # Python version
    vi = sys.version_info
    py_ok = (vi.major == 3) and (vi.minor >= 10)
    _check(
        "Python {}.{}.{}".format(vi.major, vi.minor, vi.micro),
        py_ok,
        "" if py_ok else "Slowave requires Python 3.10+.",
    )

    # torch
    try:
        import torch
        _check("torch {}".format(torch.__version__), True)
    except Exception as e:
        _check("torch", False, str(e))

    # faiss
    try:
        import faiss
        _check("faiss-cpu {}".format(faiss.__version__), True)
    except Exception as e:
        _check("faiss", False, str(e))

    # sentence-transformers
    try:
        import sentence_transformers as _st
        _check("sentence-transformers {}".format(_st.__version__), True)
    except Exception as e:
        _check("sentence-transformers", False, str(e))

    # embedding backend end-to-end
    try:
        from slowave.symbolic.encoder import TextEncoder
        enc = TextEncoder()
        v = enc.encode("doctor test")
        _check("Embedding backend (dim={})".format(v.shape[0]), True)
    except Exception as e:
        _check("Embedding backend", False, str(e)[:200])

    # SQLite write
    try:
        import sqlite3
        import os
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        con = sqlite3.connect(tmp_path)
        con.execute("CREATE TABLE t (x INTEGER)")
        con.execute("INSERT INTO t VALUES (1)")
        con.commit()
        con.close()
        os.unlink(tmp_path)
        _check("SQLite write access", True)
    except Exception as e:
        _check("SQLite write access", False, str(e))

    # MCP server
    mcp_path = shutil.which("slowave-mcp")
    _check(
        "MCP server (slowave-mcp)",
        mcp_path is not None,
        "" if mcp_path else "Run: pip install slowave  (or pipx install slowave)",
    )

    click.echo("")
    if ok:
        click.echo("All checks passed.")
    else:
        click.echo("One or more checks failed. See details above.")
        sys.exit(1)


cli.add_command(setup_cmd)


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
