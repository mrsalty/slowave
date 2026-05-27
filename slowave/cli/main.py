"""Slowave CLI entry point.

Provides the agent-facing surface: session/event/remember/recall/context/show.

Design goals:
- Every command prints either JSON or a compact human-readable form.
- JSON mode is selected with --json (recommended for agent integrations).
- The CLI is fast on the hot paths (event_append, recall): no LLM call here.
- LLM is only invoked on `session end` (consolidation) or `consolidate`.
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

import click

from slowave.core.config import SlowaveConfig
from slowave.core.paths import default_db_path
from slowave.core.engine import SlowaveEngine
from slowave.llm.base import LLMBackendConfig
from slowave.symbolic.encoder import EncoderConfig


DEFAULT_DB = "__DEFAULT_DB__"
DEFAULT_MODEL = os.environ.get("SLOWAVE_MODEL", "qwen2.5:7b-instruct")
DEFAULT_OLLAMA_URL = os.environ.get("SLOWAVE_OLLAMA_URL", "http://localhost:11434")


def _ensure_db_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _resolve_db_path(db: str) -> str:
    if db == DEFAULT_DB:
        return default_db_path()
    return os.path.expanduser(db)


def _build_engine(db: str, *, disable_llm: bool = True, schema_mode: str = "latent") -> SlowaveEngine:
    db = _resolve_db_path(db)
    _ensure_db_dir(db)
    cfg = SlowaveConfig(
        db_path=db,
        dim=384,
        encoder=EncoderConfig(),
        llm=LLMBackendConfig(model=DEFAULT_MODEL, base_url=DEFAULT_OLLAMA_URL),
        disable_llm=disable_llm,
        schema_mode=schema_mode,
    )
    return SlowaveEngine(cfg)


def _print(obj: Any, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2, default=str))


@click.group()
@click.option(
    "--db",
    default=DEFAULT_DB,
    show_default="SLOWAVE_DB or ~/.slowave/slowave.db",
    help="SQLite db path override.",
)
@click.option("--no-llm", is_flag=True, help="Disable LLM (no schema extraction).")
@click.option("--json", "as_json", is_flag=True, help="JSON output.")
@click.pass_context
def cli(ctx: click.Context, db: str, no_llm: bool, as_json: bool) -> None:
    """Slowave: brain-inspired memory for AI agents."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = _resolve_db_path(db)
    ctx.obj["no_llm"] = no_llm
    ctx.obj["json"] = as_json


@cli.group()
def session() -> None:
    """Session lifecycle."""


@session.command("start")
@click.option("--agent", default="cline-tui")
@click.option("--project", default=None)
@click.pass_context
def session_start(ctx: click.Context, agent: str, project: str | None) -> None:
    eng = _build_engine(ctx.obj["db"], disable_llm=True)  # no LLM needed at start
    sid = eng.session_start(agent=agent, project=project)
    _print({"session_id": sid}, ctx.obj["json"])
    eng.close()


@session.command("end")
@click.argument("session_id")
@click.option("--consolidate", is_flag=True,
              help="Also run replay+LLM consolidation synchronously (slow). "
                   "Default: encode only; run 'slowave consolidate' separately.")
@click.pass_context
def session_end(ctx: click.Context, session_id: str, consolidate: bool) -> None:
    """End a session and encode events into episodic memories.

    Fast by default: no LLM, no blocking. Use --consolidate only in scripts
    or tests. In production let the background worker handle consolidation.
    """
    eng = _build_engine(ctx.obj["db"], disable_llm=not consolidate or ctx.obj["no_llm"])
    stats = eng.session_end(session_id, consolidate=consolidate and not ctx.obj["no_llm"])
    _print(stats, ctx.obj["json"])
    eng.close()


@cli.command("event")
@click.option("--session", "session_id", required=True)
@click.option("--type", "type_", required=True)
@click.option("--content", required=True)
@click.pass_context
def event_append(ctx: click.Context, session_id: str, type_: str, content: str) -> None:
    """Append an event to a session."""
    eng = _build_engine(ctx.obj["db"], disable_llm=True)
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
    eng = _build_engine(ctx.obj["db"], disable_llm=True)
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
    eng = _build_engine(ctx.obj["db"], disable_llm=True)
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
@click.option("--limit", default=10, show_default=True)
@click.pass_context
def context_cmd(ctx: click.Context, project: str | None, limit: int) -> None:
    """Return a memory brief for prepending to an agent's system prompt."""
    eng = _build_engine(ctx.obj["db"], disable_llm=True)
    schemas = eng.context(project=project, limit=limit)
    if ctx.obj["json"]:
        _print([asdict(s) for s in schemas], True)
    else:
        click.echo("=== Memory Context ===")
        if not schemas:
            click.echo("  (no memories yet)")
        for s in schemas:
            click.echo(
                f"  [sch_{s.id}] {s.content_text}"
                f"  status={s.status} sal={s.salience:.3f} supports={len(s.supporting_episode_ids)}"
                f" tags={','.join(s.tags)}"
                + ("  needs_review" if s.needs_review else "")
            )
        click.echo("\nCite memories as [sch_xxx] or [epi_xxx] when you use them.")
    eng.close()


@cli.command("show")
@click.argument("ref")
@click.pass_context
def show(ctx: click.Context, ref: str) -> None:
    """Show a schema/episode/event by ref (sch_NN, epi_NN, evt_NN)."""
    eng = _build_engine(ctx.obj["db"], disable_llm=True)
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
            _print({
                "id": e.id, "session_id": e.session_id, "ts": e.ts,
                "type": e.type, "content": e.content, "metadata": e.metadata,
            }, ctx.obj["json"])
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
    eng = _build_engine(ctx.obj["db"], disable_llm=True)
    kwargs: dict[str, Any] = {"limit": limit}
    if needs_review:
        kwargs["needs_review"] = True
    items = eng.list_schemas(**kwargs)
    if ctx.obj["json"]:
        _print([asdict(s) for s in items], True)
    else:
        for s in items:
            click.echo(
                f"  [sch_{s.id}] {s.content_text}"
                f"  status={s.status} sal={s.salience:.3f} supports={len(s.supporting_episode_ids)}"
                f" tags={','.join(s.tags)}"
                + ("  needs_review" if s.needs_review else "")
            )
    eng.close()


@cli.command("stats")
@click.pass_context
def stats_cmd(ctx: click.Context) -> None:
    """Print system stats."""
    eng = _build_engine(ctx.obj["db"], disable_llm=True)
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
        rows.append({
            "pid": int(pid),
            "ppid": int(ppid),
            "stat": stat,
            "rss_kb": int(rss),
            "command": command,
        })
    return rows


@cli.command("status")
@click.pass_context
def status_cmd(ctx: click.Context) -> None:
    """Print DB, memory-health, and local process status."""
    db = ctx.obj["db"]
    eng = _build_engine(db, disable_llm=True)
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
    eng = _build_engine(ctx.obj["db"], disable_llm=True)
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
    eng = _build_engine(ctx.obj["db"], disable_llm=True, schema_mode="latent")
    stats = eng.replay_engine.replay_once()
    consolidation: dict[str, Any] = {}
    if eng.consolidator is not None:
        # Process all prototypes that have any episode mapping.
        protos = eng._prototypes_for_episodes([])
        cs = eng.consolidator.consolidate(prototype_ids=protos)
        consolidation = {
            "prototypes_processed": cs.prototypes_processed,
            "schemas_created": cs.schemas_created,
            "schemas_reinforced": cs.schemas_reinforced,
            "schemas_contradicted": cs.schemas_contradicted,
            "schemas_skipped": cs.schemas_skipped,
        }
    _print({"replay": stats, "consolidation": consolidation}, ctx.obj["json"])
    eng.close()


@cli.command("worker")
@click.option("--interval", default=300, show_default=True,
              help="Seconds between consolidation passes (simulates sleep cycles).")
@click.option("--once", is_flag=True,
              help="Run a single consolidation pass then exit (useful for cron/tests).")
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

    eng = _build_engine(ctx.obj["db"], disable_llm=True, schema_mode="latent")
    stop = False

    def _handle_signal(sig: int, frame: Any) -> None:
        nonlocal stop
        click.echo("\nworker: received signal, stopping after current pass.")
        stop = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    def _run_pass() -> dict[str, Any]:
        replay_stats = eng.replay_engine.replay_once()
        consolidation: dict[str, Any] = {}
        if eng.consolidator is not None:
            protos = eng._prototypes_for_episodes([])
            cs = eng.consolidator.consolidate(prototype_ids=protos)
            consolidation = {
                "prototypes_processed": cs.prototypes_processed,
                "schemas_created": cs.schemas_created,
                "schemas_reinforced": cs.schemas_reinforced,
                "schemas_contradicted": cs.schemas_contradicted,
                "schemas_skipped": cs.schemas_skipped,
            }
        return {"replay": replay_stats, "consolidation": consolidation}

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


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
