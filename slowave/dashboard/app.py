"""Local Slowave dashboard.

Dependency-free: stdlib HTTP server + SQLite read APIs + embedded UI.
The dashboard is local-only by default and read-only unless future actions
are explicitly enabled.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


VALID_SCHEMA_STATUSES = ("active", "needs_review", "superseded", "contradicted", "archived")
VALID_SCHEMA_RELATIONS = ("reinforces", "refines", "contradicts", "supersedes", "related_to", "part_of")


def run_dashboard(
    *,
    db_path: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    refresh_ms: int = 2000,
    allow_actions: bool = False,
    open_browser: bool = True,
) -> None:
    """Run the local dashboard HTTP server."""
    db_path = os.path.abspath(os.path.expanduser(db_path))
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "WARNING: slowave dashboard is intended for localhost use; "
            f"binding to {host!r} may expose private memories on your network.",
            flush=True,
        )

    handler = _make_handler(
        db_path=db_path,
        refresh_ms=int(refresh_ms),
        allow_actions=bool(allow_actions),
    )
    server = ThreadingHTTPServer((host, int(port)), handler)
    url = f"http://{host}:{int(port)}"
    print(f"slowave dashboard: {url}", flush=True)
    print(f"db: {db_path}", flush=True)
    print("Press Ctrl-C to stop.", flush=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nslowave dashboard: stopping", flush=True)
    finally:
        server.server_close()


def _make_handler(*, db_path: str, refresh_ms: int, allow_actions: bool):
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "slowave-dashboard/0.2"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            qs = parse_qs(parsed.query)
            try:
                if path == "/":
                    self._send_html(_INDEX_HTML)
                elif path == "/api/status":
                    self._send_json(_status_payload(db_path))
                elif path == "/api/processes":
                    self._send_json({"processes": _slowave_processes()})
                elif path == "/api/db/health":
                    self._send_json(_db_health(db_path))
                elif path == "/api/schemas":
                    self._send_json(_schemas_payload(db_path, qs))
                elif path == "/api/graph/schemas":
                    self._send_json(_schema_graph_payload(db_path, qs))
                elif path.startswith("/api/schemas/"):
                    schema_id = int(path.split("/")[-1].replace("sch_", ""))
                    self._send_json(_schema_detail(db_path, schema_id))
                elif path == "/api/procedures":
                    self._send_json(_procedures_payload(db_path, qs))
                elif path == "/api/worker/runs":
                    self._send_json(_worker_runs_payload(db_path, qs))
                elif path == "/api/generalization":
                    self._send_json(_generalization_payload(db_path))
                else:
                    self._send_json({"error": "not found", "path": path}, status=HTTPStatus.NOT_FOUND)
            except Exception as e:
                self._send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8") if length else "{}"
                payload = json.loads(body or "{}")
                if path == "/api/recall":
                    self._send_json(_recall_payload(db_path, payload))
                elif path == "/api/processes/kill":
                    if not allow_actions:
                        self._send_json(
                            {"error": "kill actions are disabled; restart dashboard with --allow-actions"},
                            status=HTTPStatus.FORBIDDEN,
                        )
                    else:
                        self._send_json(_kill_process(payload))
                else:
                    self._send_json({"error": "not found", "path": path}, status=HTTPStatus.NOT_FOUND)
            except Exception as e:
                self._send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def _send_html(self, html: str) -> None:
            html = html.replace("__REFRESH_MS__", str(refresh_ms)).replace(
                "__ALLOW_ACTIONS__", "true" if allow_actions else "false"
            )
            data = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, obj: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return DashboardHandler


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # SQLite performance pragmas: WAL mode allows concurrent readers while a writer is active
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-65536")  # 64MB page cache
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"] if row else 0)
    except sqlite3.Error:
        return 0


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _ids_from_json(value: Any) -> list[int]:
    payload = _json_loads(value, {})
    if isinstance(payload, dict):
        raw = payload.get("ids", [])
    elif isinstance(payload, list):
        raw = payload
    else:
        raw = []
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(item))
        except Exception:
            continue
    return out


def _tags_from_json(value: Any) -> list[str]:
    payload = _json_loads(value, {})
    raw = payload.get("tags", []) if isinstance(payload, dict) else []
    return [str(x) for x in raw]


def _schema_class(facets: dict[str, Any]) -> str | None:
    value = facets.get("schema_class") or facets.get("class") or facets.get("type")
    return None if value in (None, "") else str(value)


def _schema_row_to_node(row: sqlite3.Row, prototype_ids: list[int] | None = None) -> dict[str, Any]:
    facets = _json_loads(row["facets_json"], {})
    if not isinstance(facets, dict):
        facets = {}
    tags = _tags_from_json(row["tags_json"])
    supporting = _ids_from_json(row["supporting_episode_ids"])
    contradicting = _ids_from_json(row["contradicting_episode_ids"])
    content = str(row["content_text"])
    # Generalization stage (Stage 11) — default 0 for legacy rows without the column
    try:
        gen_stage = int(row["generalization_stage"])
    except (KeyError, TypeError, IndexError):
        gen_stage = 0
    return {
        "id": f"sch_{int(row['id'])}",
        "schema_id": int(row["id"]),
        "label": content if len(content) <= 80 else content[:77] + "...",
        "content": content,
        "scope": row["scope_id"],
        "status": str(row["status"]),
        "confidence": float(row["confidence"]),
        "salience": float(row["salience"]),
        "needs_review": bool(row["needs_review"]),
        "facets": facets,
        "schema_class": _schema_class(facets),
        "tags": tags,
        "support_count": len(supporting),
        "contradict_count": len(contradicting),
        "prototype_ids": prototype_ids or [],
        "first_formed_ts": int(row["first_formed_ts"]),
        "last_updated_ts": int(row["last_updated_ts"]),
        # Generalization fields (Stage 11)
        "generalization_stage": gen_stage,
        "distinct_scope_count": int(facets.get("distinct_scope_count", 0)),
        "distinct_scope_kind_count": int(facets.get("distinct_scope_kind_count", 0)),
        "scope_breadth_pct": float(facets.get("scope_breadth_pct", 0.0)),
        "scope_kind_breadth_pct": float(facets.get("scope_kind_breadth_pct", 0.0)),
        "cross_scope_recall_count": int(facets.get("cross_scope_recall_count", 0)),
    }


def _count_by_gen_stage(conn: sqlite3.Connection, *, min_stage: int) -> int:
    """Count active schemas with generalization_stage >= min_stage."""
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM schemas WHERE status = 'active' AND generalization_stage >= ?",
            (min_stage,),
        ).fetchone()
        return int(row["n"]) if row else 0
    except sqlite3.Error:
        return 0


def _status_payload(db_path: str) -> dict[str, Any]:
    exists = os.path.exists(db_path)
    db_file = Path(db_path)
    conn = _connect(db_path) if exists else None
    try:
        stats: dict[str, Any] = {}
        schema_health: dict[str, Any] = {}
        scopes: list[dict[str, Any]] = []
        recent_sessions: list[dict[str, Any]] = []
        last_consolidation_ts: int | None = None
        if conn is not None:
            stats = {
                "sessions": _table_count(conn, "sessions"),
                "raw_events": _table_count(conn, "raw_events"),
                "episodes": _table_count(conn, "episodic_memories"),
                "episode_texts": _table_count(conn, "episode_text"),
                "prototypes": _table_count(conn, "semantic_prototypes"),
                "schemas": _table_count(conn, "schemas"),
                "procedures": _table_count(conn, "procedural_memories"),
                "edges": _table_count(conn, "prototype_edges"),
                "schema_relations": _table_count(conn, "schema_relations"),
                "schema_evidence": _table_count(conn, "schema_evidence"),
                "feedback_events": _table_count(conn, "context_feedback_events"),
                # Generalization stage counts (Stage 11)
                "promoted_schemas": _count_by_gen_stage(conn, min_stage=1),
                "global_schemas": _count_by_gen_stage(conn, min_stage=3),
                "known_scopes": _table_count(conn, "scope_registry"),
            }
            schema_health = _schema_health(conn)
            scopes = [
                {"scope": r["scope"], "sessions": int(r["n"])}
                for r in conn.execute(
                    "SELECT COALESCE(scope_id, '(none)') AS scope, COUNT(*) AS n "
                    "FROM sessions GROUP BY COALESCE(scope_id, '(none)') ORDER BY n DESC"
                ).fetchall()
            ]
            raw_sessions = conn.execute(
                """
                SELECT s.id, s.agent, s.scope_id, s.started_ts, s.ended_ts,
                       COUNT(re.id) AS events,
                       COUNT(DISTINCT et.episode_id) AS episodes
                FROM sessions s
                LEFT JOIN raw_events re ON re.session_id = s.id
                LEFT JOIN episode_text et ON et.session_id = s.id
                GROUP BY s.id
                ORDER BY s.started_ts DESC
                LIMIT 10
                """
            ).fetchall()
            recent_sessions = []
            for r in raw_sessions:
                d = dict(r)
                started = d.get("started_ts") or 0
                ended = d.get("ended_ts")
                d["duration_seconds"] = int(ended) - int(started) if ended else None
                recent_sessions.append(d)
            # last consolidation: most recently ended session
            lc = conn.execute(
                "SELECT MAX(ended_ts) AS ts FROM sessions WHERE ended_ts IS NOT NULL"
            ).fetchone()
            if lc and lc["ts"]:
                last_consolidation_ts = int(lc["ts"])
        processes = _slowave_processes()
        return {
            "db_path": db_path,
            "db_exists": exists,
            "db_size_bytes": db_file.stat().st_size if exists else 0,
            "wal_size_bytes": Path(db_path + "-wal").stat().st_size if Path(db_path + "-wal").exists() else 0,
            "shm_size_bytes": Path(db_path + "-shm").stat().st_size if Path(db_path + "-shm").exists() else 0,
            "stats": stats,
            "schema_health": schema_health,
            "scopes": scopes,
            "recent_sessions": recent_sessions,
            "processes": processes,
            "warnings": _warnings(schema_health, processes),
            "last_consolidation_ts": last_consolidation_ts,
            "now_ts": int(time.time()),
        }
    finally:
        if conn is not None:
            conn.close()


def _schema_health(conn: sqlite3.Connection) -> dict[str, Any]:
    total = _table_count(conn, "schemas")
    by_status = {
        str(r["status"]): int(r["n"])
        for r in conn.execute("SELECT status, COUNT(*) AS n FROM schemas GROUP BY status").fetchall()
    }
    active = int(by_status.get("active", 0))
    needs_review = int(by_status.get("needs_review", 0))
    sal = conn.execute(
        "SELECT MIN(salience) AS min_salience, AVG(salience) AS avg_salience, "
        "MAX(salience) AS max_salience FROM schemas WHERE status IN ('active', 'needs_review')"
    ).fetchone()
    dup_rows = 0
    try:
        rows = conn.execute(
            """
            SELECT scope_id, lower(trim(content_text)) AS norm, COUNT(*) AS n
            FROM schemas
            WHERE status IN ('active', 'needs_review')
            GROUP BY scope_id, lower(trim(content_text))
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        dup_rows = sum(int(r["n"]) - 1 for r in rows)
    except sqlite3.Error:
        dup_rows = 0
    denom = max(1, active + needs_review)
    return {
        "schemas_total": total,
        "schemas_by_status": by_status,
        "active_schemas": active,
        "needs_review_schemas": needs_review,
        "active_exact_duplicate_rows": dup_rows,
        "active_exact_duplicate_ratio": dup_rows / denom,
        "active_salience": {
            "min": 0.0 if sal is None or sal["min_salience"] is None else float(sal["min_salience"]),
            "avg": 0.0 if sal is None or sal["avg_salience"] is None else float(sal["avg_salience"]),
            "max": 0.0 if sal is None or sal["max_salience"] is None else float(sal["max_salience"]),
        },
    }


def _warnings(schema_health: dict[str, Any], processes: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    mcp = [p for p in processes if "slowave-mcp" in p.get("command", "")]
    if len(mcp) > 1:
        out.append(f"{len(mcp)} slowave-mcp processes detected; check duplicate MCP clients or stale sessions.")
    orphaned = [p for p in mcp if int(p.get("ppid", 0)) == 1]
    if orphaned:
        out.append(f"{len(orphaned)} slowave-mcp processes are orphaned with PPID=1.")
    if schema_health.get("needs_review_schemas", 0):
        out.append(f"{schema_health['needs_review_schemas']} schemas need review.")
    if schema_health.get("active_exact_duplicate_rows", 0):
        out.append(f"{schema_health['active_exact_duplicate_rows']} active duplicate schema rows detected.")
    return out


def _slowave_processes() -> list[dict[str, Any]]:
    try:
        out = subprocess.check_output(
            ["ps", "-axo", "pid,ppid,stat,etime,rss,command"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for line in out.splitlines()[1:]:
        parts = line.strip().split(None, 5)
        if len(parts) < 6:
            continue
        pid, ppid, stat, etime, rss, command = parts
        is_mcp = "slowave-mcp" in command
        is_worker = "slowave worker" in command or (
            "slowave.cli.main" in command and " worker" in command
        )
        is_dashboard = "slowave dashboard" in command or (
            "slowave.cli.main" in command and " dashboard" in command
        )
        if not (is_mcp or is_worker or is_dashboard):
            continue
        parent_command = None
        try:
            parent_command = subprocess.check_output(
                ["ps", "-p", str(ppid), "-o", "command="], text=True, stderr=subprocess.DEVNULL
            ).strip() or None
        except Exception:
            pass
        rows.append({
            "pid": int(pid),
            "ppid": int(ppid),
            "stat": stat,
            "age_seconds": _parse_etime_seconds(etime),
            "rss_kb": int(rss),
            "command": command,
            "parent_command": parent_command,
            "kind": "mcp" if is_mcp else ("worker" if is_worker else "dashboard"),
            "orphaned": int(ppid) == 1,
        })
    return rows


def _parse_etime_seconds(value: str) -> int:
    """Parse ps(1) elapsed time [[dd-]hh:]mm:ss into seconds."""
    value = str(value).strip()
    days = 0
    if "-" in value:
        day_s, value = value.split("-", 1)
        try:
            days = int(day_s)
        except ValueError:
            days = 0
    parts = value.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = (int(x) for x in parts)
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = (int(x) for x in parts)
        elif len(parts) == 1:
            hours = 0
            minutes = 0
            seconds = int(parts[0])
        else:
            return 0
    except ValueError:
        return 0
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _db_health(db_path: str) -> dict[str, Any]:
    if not os.path.exists(db_path):
        return {"db_path": db_path, "db_exists": False}
    conn = _connect(db_path)
    try:
        pragmas: dict[str, Any] = {}
        for name in ("journal_mode", "foreign_keys", "page_count", "page_size"):
            try:
                row = conn.execute(f"PRAGMA {name}").fetchone()
                pragmas[name] = row[0] if row is not None else None
            except sqlite3.Error as e:
                pragmas[name] = f"error: {e}"
        try:
            integrity = [r[0] for r in conn.execute("PRAGMA integrity_check").fetchall()]
        except sqlite3.Error as e:
            integrity = [f"error: {e}"]
        try:
            fk = [dict(r) for r in conn.execute("PRAGMA foreign_key_check").fetchall()]
        except sqlite3.Error as e:
            fk = [{"error": str(e)}]
        tables = [
            {"name": r["name"], "type": r["type"], "count": _table_count(conn, r["name"]) if r["type"] == "table" and not str(r["name"]).startswith("sqlite_") else None}
            for r in conn.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY type, name"
            ).fetchall()
        ]
        return {
            "db_path": db_path,
            "db_exists": True,
            "pragmas": pragmas,
            "integrity_check": integrity,
            "foreign_key_check": fk,
            "tables": tables,
        }
    finally:
        conn.close()


def _schemas_payload(db_path: str, qs: dict[str, list[str]]) -> dict[str, Any]:
    limit = max(1, min(500, int((qs.get("limit") or [100])[0])))
    status = (qs.get("status") or [""])[0]
    scope = (qs.get("scope") or [""])[0]
    q = (qs.get("q") or [""])[0].strip().lower()
    args: list[Any] = []
    sql = "SELECT * FROM schemas WHERE 1=1"
    if status in VALID_SCHEMA_STATUSES:
        sql += " AND status = ?"
        args.append(status)
    if scope:
        sql += " AND scope_id = ?"
        args.append(scope)
    if q:
        sql += " AND lower(content_text) LIKE ?"
        args.append(f"%{q}%")
    sql += " ORDER BY salience DESC, last_updated_ts DESC LIMIT ?"
    args.append(limit)
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, tuple(args)).fetchall()
        proto_map = _prototype_map(conn, [int(r["id"]) for r in rows])
        return {"schemas": [_schema_row_to_node(r, proto_map.get(int(r["id"]), [])) for r in rows]}
    finally:
        conn.close()


def _prototype_map(conn: sqlite3.Connection, schema_ids: list[int]) -> dict[int, list[int]]:
    if not schema_ids:
        return {}
    ph = ",".join(["?"] * len(schema_ids))
    out: dict[int, list[int]] = {sid: [] for sid in schema_ids}
    for r in conn.execute(
        f"SELECT schema_id, prototype_id FROM schema_prototype_map WHERE schema_id IN ({ph})",
        tuple(schema_ids),
    ).fetchall():
        out.setdefault(int(r["schema_id"]), []).append(int(r["prototype_id"]))
    return out


def _schema_graph_payload(db_path: str, qs: dict[str, list[str]]) -> dict[str, Any]:
    limit = max(1, min(300, int((qs.get("limit") or [120])[0])))
    scope = (qs.get("scope") or [""])[0]
    statuses_raw = (qs.get("statuses") or ["active,needs_review,contradicted,superseded"])[0]
    relations_raw = (qs.get("relations") or ["reinforces,refines,contradicts,supersedes,related_to,part_of"])[0]
    statuses = [s for s in statuses_raw.split(",") if s in VALID_SCHEMA_STATUSES]
    relations = [r for r in relations_raw.split(",") if r in VALID_SCHEMA_RELATIONS]
    if not statuses:
        statuses = ["active", "needs_review"]
    min_salience = _optional_float((qs.get("min_salience") or [""])[0])
    max_salience = _optional_float((qs.get("max_salience") or [""])[0])
    args: list[Any] = []
    ph_status = ",".join(["?"] * len(statuses))
    sql = f"SELECT * FROM schemas WHERE status IN ({ph_status})"
    args.extend(statuses)
    if scope:
        sql += " AND scope_id = ?"
        args.append(scope)
    if min_salience is not None:
        sql += " AND salience >= ?"
        args.append(float(min_salience))
    if max_salience is not None:
        sql += " AND salience <= ?"
        args.append(float(max_salience))
    sql += " ORDER BY salience DESC, last_updated_ts DESC LIMIT ?"
    args.append(limit)
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, tuple(args)).fetchall()
        schema_ids = [int(r["id"]) for r in rows]
        proto_map = _prototype_map(conn, schema_ids)
        nodes = [_schema_row_to_node(r, proto_map.get(int(r["id"]), [])) for r in rows]
        edges: list[dict[str, Any]] = []
        if schema_ids and relations:
            ph_ids = ",".join(["?"] * len(schema_ids))
            ph_rel = ",".join(["?"] * len(relations))
            edge_rows = conn.execute(
                f"""
                SELECT * FROM schema_relations
                WHERE src_schema_id IN ({ph_ids})
                  AND dst_schema_id IN ({ph_ids})
                  AND relation IN ({ph_rel})
                ORDER BY created_ts DESC
                """,
                tuple(schema_ids + schema_ids + relations),
            ).fetchall()
            for r in edge_rows:
                src = int(r["src_schema_id"])
                dst = int(r["dst_schema_id"])
                rel = str(r["relation"])
                edges.append({
                    "id": f"rel_{src}_{dst}_{rel}",
                    "source": f"sch_{src}",
                    "target": f"sch_{dst}",
                    "src_schema_id": src,
                    "dst_schema_id": dst,
                    "relation": rel,
                    "confidence": float(r["confidence"]),
                    "reason": r["reason"],
                    "created_ts": int(r["created_ts"]),
                })
        return {
            "nodes": nodes,
            "edges": edges,
            "limit": limit,
            "statuses": statuses,
            "relations": relations,
            "salience_filter": {"min": min_salience, "max": max_salience},
        }
    finally:
        conn.close()


def _optional_float(value: Any) -> float | None:
    try:
        text = str(value).strip()
        if text == "":
            return None
        return float(text)
    except Exception:
        return None


def _schema_detail(db_path: str, schema_id: int) -> dict[str, Any]:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM schemas WHERE id = ?", (schema_id,)).fetchone()
        if row is None:
            return {"error": "schema not found", "schema_id": schema_id}
        proto_map = _prototype_map(conn, [schema_id])
        schema = _schema_row_to_node(row, proto_map.get(schema_id, []))
        evidence = [dict(r) for r in conn.execute(
            "SELECT * FROM schema_evidence WHERE schema_id = ? ORDER BY weight DESC LIMIT 50",
            (schema_id,),
        ).fetchall()]
        outgoing = [dict(r) for r in conn.execute(
            "SELECT * FROM schema_relations WHERE src_schema_id = ? ORDER BY created_ts DESC",
            (schema_id,),
        ).fetchall()]
        incoming = [dict(r) for r in conn.execute(
            "SELECT * FROM schema_relations WHERE dst_schema_id = ? ORDER BY created_ts DESC",
            (schema_id,),
        ).fetchall()]
        return {"schema": schema, "evidence": evidence, "outgoing": outgoing, "incoming": incoming}
    finally:
        conn.close()


def _procedures_payload(db_path: str, qs: dict[str, list[str]]) -> dict[str, Any]:
    if not os.path.exists(db_path):
        return {"procedures": []}
    limit = max(1, min(200, int((qs.get("limit") or [50])[0])))
    scope = (qs.get("scope") or [""])[0]
    status = (qs.get("status") or [""])[0]
    conn = _connect(db_path)
    try:
        args: list[Any] = []
        sql = "SELECT * FROM procedural_memories WHERE 1=1"
        if status:
            sql += " AND status = ?"
            args.append(status)
        if scope:
            sql += " AND origin_scope_id = ?"
            args.append(scope)
        sql += " ORDER BY confidence DESC, created_at DESC LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, tuple(args)).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": int(r["id"]),
                "goal": r["goal"],
                "task_type": r["task_type"],
                "scope": r["origin_scope_id"],
                "status": str(r["status"]),
                "confidence": float(r["confidence"]),
                "steps": _json_loads(r["procedure_steps_json"], []),
                "trigger_pattern": _json_loads(r["trigger_pattern_json"], []),
                "created_at": int(r["created_at"]) if r["created_at"] else 0,
                "updated_at": int(r["updated_at"]) if r["updated_at"] else 0,
            })
        return {"procedures": out}
    except sqlite3.Error:
        return {"procedures": []}
    finally:
        conn.close()


def _generalization_payload(db_path: str) -> dict[str, Any]:
    """Return cross-scope generalization stats: stage distribution + scope registry."""
    if not os.path.exists(db_path):
        return {"stage_distribution": {}, "scope_registry": [], "top_promoted": []}
    conn = _connect(db_path)
    try:
        # Stage distribution across active schemas
        stage_rows = conn.execute(
            "SELECT generalization_stage AS stage, COUNT(*) AS n "
            "FROM schemas WHERE status = 'active' "
            "GROUP BY generalization_stage ORDER BY generalization_stage"
        ).fetchall()
        stage_dist = {int(r["stage"]): int(r["n"]) for r in stage_rows}

        # Scope registry (may not exist on older DBs)
        reg_rows: list[dict[str, Any]] = []
        try:
            reg_rows = [
                {
                    "scope_id": str(r["scope_id"]),
                    "scope_kind": r["scope_kind"],
                    "session_count": int(r["session_count"]),
                    "recall_count": int(r["recall_count"]),
                    "last_active_ts": int(r["last_active_ts"]),
                    "first_seen_ts": int(r["first_seen_ts"]),
                }
                for r in conn.execute(
                    "SELECT * FROM scope_registry ORDER BY last_active_ts DESC"
                ).fetchall()
            ]
        except Exception:
            pass

        # Top promoted schemas (stage >= 1), sorted by breadth
        promoted_rows = conn.execute(
            """
            SELECT id, content_text, scope_id, generalization_stage,
                   salience, facets_json
            FROM schemas
            WHERE generalization_stage >= 1 AND status = 'active'
            ORDER BY generalization_stage DESC, salience DESC
            LIMIT 50
            """
        ).fetchall()
        top_promoted = []
        for r in promoted_rows:
            facets = _json_loads(r["facets_json"], {})
            top_promoted.append({
                "id": f"sch_{int(r['id'])}",
                "schema_id": int(r["id"]),
                "content": str(r["content_text"])[:200],
                "scope": r["scope_id"],
                "stage": int(r["generalization_stage"]),
                "salience": float(r["salience"]),
                "distinct_scope_count": int(facets.get("distinct_scope_count", 0)),
                "distinct_scope_kind_count": int(facets.get("distinct_scope_kind_count", 0)),
                "scope_breadth_pct": float(facets.get("scope_breadth_pct", 0.0)),
                "scope_kind_breadth_pct": float(facets.get("scope_kind_breadth_pct", 0.0)),
                "cross_scope_recall_count": int(facets.get("cross_scope_recall_count", 0)),
            })

        total_active = sum(stage_dist.values())
        promoted_count = sum(v for k, v in stage_dist.items() if k >= 1)
        global_count = stage_dist.get(3, 0)

        return {
            "stage_distribution": stage_dist,
            "scope_registry": reg_rows,
            "top_promoted": top_promoted,
            "summary": {
                "total_active_schemas": total_active,
                "promoted_schemas": promoted_count,
                "global_schemas": global_count,
                "total_known_scopes": len(reg_rows),
                "total_scope_kinds": len({r["scope_kind"] for r in reg_rows if r["scope_kind"]}),
            },
        }
    finally:
        conn.close()


def _worker_runs_payload(db_path: str, qs: dict[str, list[str]]) -> dict[str, Any]:
    """Return worker consolidation run history and summary statistics."""
    if not os.path.exists(db_path):
        return {"runs": [], "summary": {}}
    limit = max(1, min(200, int((qs.get("limit") or [50])[0])))
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM worker_runs ORDER BY started_ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        runs = [dict(r) for r in rows]
        # summary stats
        total_row = conn.execute(
            "SELECT COUNT(*) AS n, MAX(started_ts) AS last_ts,"
            " SUM(schemas_created) AS schemas_created,"
            " SUM(schemas_reinforced) AS schemas_reinforced,"
            " AVG(duration_ms) AS avg_ms"
            " FROM worker_runs WHERE error_text IS NULL"
        ).fetchone()
        return {
            "runs": runs,
            "summary": {
                "total_passes": int(total_row["n"]) if total_row else 0,
                "last_run_ts": total_row["last_ts"] if total_row else None,
                "total_schemas_created": int(total_row["schemas_created"] or 0) if total_row else 0,
                "total_schemas_reinforced": int(total_row["schemas_reinforced"] or 0) if total_row else 0,
                "avg_duration_ms": round(float(total_row["avg_ms"] or 0), 1) if total_row else 0,
            },
        }
    except sqlite3.Error:
        return {"runs": [], "summary": {}}
    finally:
        conn.close()


def _kill_process(payload: dict[str, Any]) -> dict[str, Any]:
    """Send SIGTERM to a slowave-mcp or slowave-worker process by PID.

    Only kills processes whose command line contains 'slowave-mcp' or
    'slowave worker' — refuses to kill anything else for safety.
    """
    pid = payload.get("pid")
    if not pid:
        return {"error": "pid is required"}
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return {"error": f"invalid pid: {pid!r}"}

    # Safety check: only kill known slowave processes
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except subprocess.CalledProcessError:
        return {"error": f"pid {pid} not found"}

    is_mcp = "slowave-mcp" in out
    is_worker = "slowave worker" in out or ("slowave.cli.main" in out and " worker" in out)
    if not (is_mcp or is_worker):
        return {
            "error": f"pid {pid} is not a slowave-mcp or slowave-worker process (command: {out[:80]!r})"
        }

    sig = payload.get("signal", "TERM").upper()
    signum = {"TERM": 15, "KILL": 9, "INT": 2}.get(sig, 15)
    try:
        os.kill(pid, signum)
        return {"ok": True, "pid": pid, "signal": sig, "command": out[:80]}
    except ProcessLookupError:
        return {"error": f"pid {pid} no longer exists"}
    except PermissionError:
        return {"error": f"permission denied killing pid {pid}"}


def _recall_payload(db_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    top_k = max(1, min(20, int(payload.get("top_k") or 5)))
    evidence = bool(payload.get("evidence", True))
    from dataclasses import asdict as _asdict

    from slowave.core.config import SlowaveConfig
    from slowave.core.engine import SlowaveEngine
    from slowave.symbolic.encoder import EncoderConfig

    eng = SlowaveEngine(
        SlowaveConfig(
            db_path=db_path,
            dim=384,
            encoder=EncoderConfig(),
        )
    )
    try:
        r = eng.recall(query, top_k=top_k, evidence=evidence)
        return {
            "query": query,
            "schemas": [_asdict(s) for s in r.schemas],
            "episodes": r.episode_texts,
            "raw_events": r.raw_events,
            "expanded_neighbors": {str(k): v for k, v in r.expanded_neighbors.items()},
        }
    finally:
        eng.close()


_INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Slowave Dashboard</title>
<style>
:root{
  --bg:#080e1c;--panel:#0f1829;--panel2:#141e33;--panel3:#192540;
  --text:#dce6f9;--muted:#7a8db5;--line:#1e2d4a;--line2:#253658;
  --green:#3ecf6e;--amber:#f5b942;--red:#f04e6a;--blue:#4f9bff;
  --purple:#9d71f0;--cyan:#34c4c4;--gray:#5a6e91;
  --green-bg:#0a2018;--amber-bg:#221800;--red-bg:#200d14;
  --font:"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  --radius:10px;--radius-sm:6px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font);background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;min-height:100vh}
a{color:var(--blue);text-decoration:none}

/* ── LAYOUT ── */
.app-header{
  background:#060c19;
  border-bottom:1px solid var(--line);
  position:sticky;top:0;z-index:100;
  padding:0 22px;
}
.header-top{
  display:flex;align-items:center;justify-content:space-between;
  padding:12px 0;
  gap:12px;
}
.brand{display:flex;align-items:center;gap:10px}
.brand-icon{font-size:22px;line-height:1}
.brand-name{font-size:18px;font-weight:700;letter-spacing:-0.3px;color:#fff}
.brand-version{font-size:11px;color:var(--muted);margin-left:6px;font-weight:400}
.header-meta{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.db-path{
  font-size:11px;color:var(--muted);max-width:380px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  font-family:"SF Mono","Fira Code",monospace;
}
.live-badge{
  display:inline-flex;align-items:center;gap:5px;
  font-size:11px;color:var(--muted);
}
.live-dot{
  width:7px;height:7px;border-radius:50%;background:var(--green);
  animation:pulse 2s ease-in-out infinite;
}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.last-updated{font-size:11px;color:var(--muted)}

.nav-tabs{
  display:flex;gap:2px;
  border-top:1px solid var(--line);
  overflow-x:auto;
}
.tab{
  border:0;background:transparent;color:var(--muted);
  padding:10px 16px;cursor:pointer;font-size:13px;font-weight:500;
  border-bottom:2px solid transparent;white-space:nowrap;
  display:flex;align-items:center;gap:6px;
  transition:color .15s,border-color .15s;
  font-family:var(--font);
}
.tab:hover{color:var(--text)}
.tab.active{color:var(--blue);border-bottom-color:var(--blue)}
.tab-badge{
  background:var(--red);color:#fff;border-radius:999px;
  font-size:10px;font-weight:700;padding:1px 5px;min-width:16px;text-align:center;
  display:none;
}
.tab-badge.show{display:inline-block}

main{padding:20px;max-width:1600px;margin:0 auto}
.section{display:none}.section.active{display:block}

/* ── CARDS ── */
.stat-grid{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(145px,1fr));
  gap:10px;margin-bottom:16px;
}
.stat-card{
  background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:14px 16px;position:relative;overflow:hidden;
}
.stat-card::before{
  content:"";position:absolute;top:0;left:0;right:0;height:2px;
  background:var(--accent,var(--blue));border-radius:var(--radius) var(--radius) 0 0;
}
.stat-card .sc-icon{font-size:18px;margin-bottom:6px;opacity:.8}
.stat-card .sc-label{font-size:11px;color:var(--muted);font-weight:500;text-transform:uppercase;letter-spacing:.5px}
.stat-card .sc-value{font-size:28px;font-weight:700;letter-spacing:-1px;line-height:1.1;margin-top:2px}
.stat-card .sc-sub{font-size:11px;color:var(--muted);margin-top:3px}

/* ── PANELS ── */
.panel{
  background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px;
}
.panel-title{font-size:14px;font-weight:600;color:var(--text);margin-bottom:12px}
.panel + .panel{margin-top:10px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.three-col{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
@media(max-width:900px){.two-col,.three-col{grid-template-columns:1fr}}

/* ── ALERTS ── */
.alert{
  border-radius:var(--radius);padding:12px 16px;margin-bottom:12px;
  display:flex;align-items:flex-start;gap:10px;
  font-size:13px;
}
.alert-warn{background:#2a1e06;border:1px solid #5a3c0a;color:#ffe0a0}
.alert-ok{background:var(--green-bg);border:1px solid #1a4d2e;color:#9af5c0}
.alert-error{background:var(--red-bg);border:1px solid #4a1a22;color:#ffb4c8}
.alert-icon{font-size:16px;flex-shrink:0;margin-top:1px}
.alert ul{margin:6px 0 0 16px;list-style:disc}
.alert li{margin-bottom:2px}

/* ── TABLES ── */
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:9px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px;background:var(--panel2);position:sticky;top:0}
tr:hover td{background:var(--panel2)}
.empty-state{padding:40px;text-align:center;color:var(--muted)}
.empty-state .es-icon{font-size:36px;margin-bottom:8px}
.empty-state .es-text{font-size:14px}

/* ── PILLS ── */
.pill{
  display:inline-flex;align-items:center;border-radius:999px;
  padding:2px 8px;font-size:11px;border:1px solid var(--line);margin:1px;
  white-space:nowrap;
}
.pill-active{background:#0a2018;color:#7af5aa;border-color:#1a4d2e}
.pill-needs_review{background:#221800;color:#ffd580;border-color:#5a3c0a}
.pill-contradicted{background:#200d14;color:#ff9aaa;border-color:#4a1a22}
.pill-superseded{background:#1a1430;color:#c4b0f5;border-color:#3a2d6a}
.pill-archived{background:#181e30;color:#8090b4;border-color:#2a3558}
.pill-mcp{background:#0e1e36;color:#7ab5ff;border-color:#1e3d6a}
.pill-worker{background:#0e261e;color:#7af5aa;border-color:#1a4d2e}
.pill-dashboard{background:#221800;color:#ffd580;border-color:#5a3c0a}
.pill-ok{background:var(--green-bg);color:#7af5aa;border-color:#1a4d2e}
.pill-warn{background:#221800;color:#ffd580;border-color:#5a3c0a}
.pill-orphan{background:var(--red-bg);color:#ff9aaa;border-color:#4a1a22}

/* ── SALIENCE BAR ── */
.sal-bar-wrap{display:inline-block;width:60px;vertical-align:middle}
.sal-bar-track{background:var(--panel2);border-radius:999px;height:5px;overflow:hidden}
.sal-bar-fill{height:5px;border-radius:999px;background:var(--blue);transition:width .3s}

/* ── PROGRESS PILLS (schema status distribution) ── */
.status-bar{display:flex;height:8px;border-radius:999px;overflow:hidden;gap:2px;margin:8px 0}
.status-bar-seg{height:8px;border-radius:999px;min-width:4px}

/* ── CONTROLS ── */
.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.controls input,.controls select,input[type=text],input[type=number],select,textarea{
  background:var(--panel2);border:1px solid var(--line2);color:var(--text);
  border-radius:var(--radius-sm);padding:7px 10px;font-size:13px;
  font-family:var(--font);
}
.controls input:focus,.controls select:focus,input:focus,select:focus,textarea:focus{
  outline:none;border-color:var(--blue);box-shadow:0 0 0 2px rgba(79,155,255,.15);
}
btn,button.btn,.btn{
  display:inline-flex;align-items:center;gap:6px;
  border:1px solid var(--line2);border-radius:var(--radius-sm);
  padding:7px 14px;font-size:13px;font-weight:500;cursor:pointer;
  font-family:var(--font);background:var(--panel2);color:var(--text);
  transition:background .15s,border-color .15s;
}
btn.primary,.btn-primary,button.primary{
  background:var(--blue);color:#060c19;border-color:var(--blue);font-weight:700;
}
btn.primary:hover,.btn-primary:hover{background:#6aabff}
btn:hover,.btn:hover,button.btn:hover{background:var(--panel3)}

/* ── SPINNER ── */
.spinner{
  display:inline-block;width:16px;height:16px;
  border:2px solid var(--line2);border-top-color:var(--blue);
  border-radius:50%;animation:spin .7s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg)}}
.loading-overlay{
  display:none;align-items:center;justify-content:center;
  padding:40px;color:var(--muted);gap:10px;
}
.loading-overlay.show{display:flex}

/* ── GRAPH ── */
.graph-layout{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:12px}
.graph-box{
  height:680px;background:#050b18;border:1px solid var(--line);
  border-radius:var(--radius);position:relative;overflow:hidden;
}
svg{width:100%;height:100%}
.edge{stroke-opacity:.7;transition:stroke-opacity .2s}
.edge:hover{stroke-opacity:1}
.node{cursor:pointer;transition:r .15s}
.node.selected{stroke:#fff!important;stroke-width:3!important}
.node-label{font-size:10px;fill:#b8c8e8;pointer-events:none;user-select:none}
.edge-label{font-size:9px;fill:#7a8db5;pointer-events:none;user-select:none}
.graph-side{height:680px;overflow-y:auto}
.graph-legend{
  display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;
  padding:10px 12px;background:var(--panel2);
  border:1px solid var(--line);border-radius:var(--radius);
}
.legend-item{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--muted)}
.legend-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.legend-line{width:18px;height:3px;border-radius:2px;flex-shrink:0}
@media(max-width:1100px){.graph-layout{grid-template-columns:1fr}.graph-side{height:auto}.graph-box{height:500px}}

/* ── TOOLTIP ── */
#tooltip{
  position:fixed;pointer-events:none;z-index:999;
  background:#101828;border:1px solid var(--line2);border-radius:var(--radius);
  padding:8px 12px;font-size:12px;max-width:320px;display:none;
  box-shadow:0 8px 32px rgba(0,0,0,.5);
  line-height:1.5;
}

/* ── DETAIL PANEL ── */
.detail-section{margin-top:14px}
.detail-section h4{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
pre.code-block{
  background:#060c19;border:1px solid var(--line);border-radius:var(--radius-sm);
  padding:10px;font-size:11px;color:#a8c0e8;overflow:auto;
  font-family:"SF Mono","Fira Code",monospace;line-height:1.5;max-height:200px;
}
.conf-bar{display:inline-flex;align-items:center;gap:6px}
.conf-track{width:80px;height:5px;background:var(--panel2);border-radius:999px;overflow:hidden}
.conf-fill{height:5px;background:var(--green);border-radius:999px}

/* ── PROCEDURES ── */
.proc-card{
  background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:14px;margin-bottom:10px;
}
.proc-header{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px}
.proc-goal{font-weight:600;font-size:14px;color:var(--text)}
.proc-meta{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.proc-steps ol{padding-left:18px;margin-top:6px}
.proc-steps li{font-size:13px;color:var(--muted);margin-bottom:3px;line-height:1.5}
.proc-steps li strong{color:var(--text)}

/* ── EXPANDABLE ROWS ── */
tr.expandable{cursor:pointer}
tr.expandable:hover td{background:var(--panel3)}
.expand-row td{background:var(--panel2)!important;padding:0}
.expand-content{padding:12px 16px}

/* ── GENERALIZATION STAGE BADGES ── */
.gen-badge{
  display:inline-flex;align-items:center;gap:4px;
  border-radius:999px;padding:2px 8px;font-size:11px;font-weight:600;
  white-space:nowrap;border:1px solid;
}
.gen-0{background:#111827;color:#5a6e91;border-color:#253050}
.gen-1{background:#0e1e36;color:#7ab5ff;border-color:#1e3d6a}
.gen-2{background:#1a1000;color:#ffd580;border-color:#5a3c0a}
.gen-3{background:#0a1e14;color:#6af5aa;border-color:#1a4d2e}
.gen-bar-wrap{display:flex;align-items:center;gap:6px;margin:4px 0}
.gen-bar{height:6px;border-radius:999px;background:var(--blue);min-width:2px}
.gen-bar-track{flex:1;height:6px;background:var(--panel3);border-radius:999px;overflow:hidden}
.scope-reg-card{
  background:var(--panel2);border:1px solid var(--line);border-radius:var(--radius-sm);
  padding:10px 14px;margin-bottom:6px;display:flex;align-items:center;justify-content:space-between;gap:10px;
}
.scope-reg-id{font-family:"SF Mono","Fira Code",monospace;font-size:12px;font-weight:600}
.scope-reg-meta{font-size:11px;color:var(--muted)}
</style>
</head>
<body>
<div id="tooltip"></div>

<header class="app-header">
  <div class="header-top">
    <div class="brand">
      <span class="brand-icon">🧠</span>
      <span class="brand-name">Slowave <span class="brand-version">Dashboard</span></span>
    </div>
    <div class="header-meta">
      <div class="db-path" id="dbPath" title="">loading...</div>
      <div class="live-badge"><span class="live-dot"></span> live</div>
      <div class="last-updated" id="lastUpdated"></div>
    </div>
  </div>
  <nav class="nav-tabs">
    <button class="tab active" data-tab="overview">📊 Overview</button>
    <button class="tab" data-tab="schemas">📖 Schemas</button>
    <button class="tab" data-tab="procedures">🧭 Procedures</button>
    <button class="tab" data-tab="graph">🕸 Graph</button>
    <button class="tab" data-tab="recall">🔍 Recall</button>
    <button class="tab" data-tab="processes">⚙️ Processes</button>
    <button class="tab" data-tab="worker">🧠 Worker</button>
    <button class="tab" data-tab="generalization">🌐 Generalization</button>
    <button class="tab" data-tab="db">💾 DB Health</button>
  </nav>
</header>

<main>
<!-- OVERVIEW -->
<section id="overview" class="section active">
  <div id="alertArea"></div>
  <div class="stat-grid" id="statGrid"></div>
  <div class="two-col">
    <div class="panel">
      <div class="panel-title">📊 Schema health</div>
      <div id="schemaHealthPanel"></div>
    </div>
    <div class="panel">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <div class="panel-title" style="margin:0">⚙️ Running processes</div>
        <div style="display:flex;gap:6px">
          <button class="btn" style="font-size:11px;padding:4px 10px" onclick="document.querySelector('.tab[data-tab=processes]').click()">View all</button>
          <button id="killAllBtn" class="btn" style="font-size:11px;padding:4px 10px;color:var(--red);border-color:var(--red);display:none" onclick="killAllStaleMcp()">✕ Kill stale MCP</button>
        </div>
      </div>
      <div id="processMini"></div>
    </div>
  </div>
  <div class="two-col" style="margin-top:10px">
    <div class="panel">
      <div class="panel-title">🕐 Recent sessions</div>
      <div id="recentSessions"></div>
    </div>
    <div class="panel">
      <div class="panel-title">🗂 Scopes</div>
      <div id="scopesPanel"></div>
    </div>
  </div>
</section>

<!-- SCHEMAS -->
<section id="schemas" class="section">
  <div class="panel">
    <div class="controls">
      <select id="schemaStatus">
        <option value="">All statuses</option>
        <option>active</option><option>needs_review</option>
        <option>contradicted</option><option>superseded</option><option>archived</option>
      </select>
      <input id="schemaScope" placeholder="scope filter" style="width:160px"/>
      <input id="schemaQ" placeholder="search content…" style="flex:1;min-width:160px"/>
      <input id="schemaLimit" type="number" value="100" min="1" max="500" style="width:70px"/>
      <button class="btn primary" onclick="loadSchemas()">Load</button>
    </div>
    <div id="schemaLoading" class="loading-overlay"><div class="spinner"></div> Loading schemas…</div>
    <div class="table-wrap" id="schemaTable"></div>
    <div id="schemaDetail" style="margin-top:12px"></div>
  </div>
</section>

<!-- PROCEDURES -->
<section id="procedures" class="section">
  <div class="panel" style="margin-bottom:10px">
    <div class="controls">
      <input id="procScope" placeholder="scope filter" style="width:180px"/>
      <select id="procStatus"><option value="">All statuses</option><option>active</option><option>candidate</option><option>archived</option></select>
      <input id="procLimit" type="number" value="50" min="1" max="200" style="width:70px"/>
      <button class="btn primary" onclick="loadProcedures()">Load</button>
    </div>
  </div>
  <div id="procLoading" class="loading-overlay"><div class="spinner"></div> Loading procedures…</div>
  <div id="procList"></div>
</section>

<!-- GRAPH -->
<section id="graph" class="section">
  <div class="panel" style="margin-bottom:10px">
    <div class="controls">
      <input id="graphScope" placeholder="scope filter" style="width:160px"/>
      <input id="graphLimit" type="number" value="120" min="1" max="300" style="width:70px"/>
      <label class="pill"><input type="checkbox" class="gstat" value="active" checked> active</label>
      <label class="pill"><input type="checkbox" class="gstat" value="needs_review" checked> needs review</label>
      <label class="pill"><input type="checkbox" class="gstat" value="contradicted" checked> contradicted</label>
      <label class="pill"><input type="checkbox" class="gstat" value="superseded" checked> superseded</label>
      <label class="pill"><input type="checkbox" class="gstat" value="archived"> archived</label>
      <button class="btn primary" onclick="loadGraph()">Refresh</button>
    </div>
    <div class="controls" style="margin-bottom:0">
      <span style="font-size:12px;color:var(--muted)">Min salience</span>
      <span id="graphMinSalienceLabel" class="pill">0.00</span>
      <input id="graphMinSalience" type="range" value="0" min="0" max="25" step="0.1"
        oninput="syncSalienceSlider()" style="flex:1;min-width:200px;accent-color:var(--blue)">
      <span style="font-size:11px;color:var(--muted)">max: <span id="graphObservedMaxSalienceLabel">25.00</span></span>
      <button class="btn" onclick="resetSalienceSlider()">Reset</button>
    </div>
  </div>
  <div class="graph-legend" id="graphLegend"></div>
  <div class="graph-layout">
    <div class="graph-box">
      <svg id="schemaGraph"></svg>
    </div>
    <div class="panel graph-side">
      <div class="panel-title">Schema detail</div>
      <div id="graphDetail" style="color:var(--muted);font-size:13px">Click a node to inspect schema, evidence and relations.</div>
    </div>
  </div>
</section>

<!-- RECALL -->
<section id="recall" class="section">
  <div class="panel">
    <div class="panel-title">🔍 Recall playground</div>
    <textarea id="recallQuery" rows="3" style="width:100%;margin-bottom:10px" placeholder="Enter a query — what should Slowave remember about this?"></textarea>
    <div class="controls">
      <label style="font-size:13px;color:var(--muted)">Top-K</label>
      <input id="recallTopK" type="number" value="5" min="1" max="20" style="width:60px"/>
      <label class="pill"><input id="recallEvidence" type="checkbox" checked> evidence</label>
      <button class="btn primary" onclick="runRecall()">Run recall</button>
    </div>
    <div id="recallLoading" class="loading-overlay"><div class="spinner"></div> Running recall (encoder may take a moment)…</div>
    <div id="recallResults"></div>
  </div>
</section>

<!-- PROCESSES -->
<section id="processes" class="section">
  <div class="panel">
    <div class="panel-title">⚙️ Slowave processes</div>
    <div id="processLoading" class="loading-overlay"><div class="spinner"></div></div>
    <div class="table-wrap" id="processTable"></div>
  </div>
</section>

<!-- WORKER -->
<section id="worker" class="section">
  <div class="stat-grid" id="workerStatGrid"></div>
  <div class="panel">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div class="panel-title">🧠 Consolidation run history</div>
      <div style="display:flex;gap:6px;align-items:center">
        <label style="font-size:12px;color:var(--muted)">Limit</label>
        <input id="workerLimit" type="number" value="50" min="1" max="200" style="width:65px"/>
        <button class="btn" onclick="loadWorker()">↺ Refresh</button>
      </div>
    </div>
    <div id="workerLoading" class="loading-overlay"><div class="spinner"></div> Loading…</div>
    <div id="workerChart" style="margin-bottom:12px"></div>
    <div class="table-wrap" id="workerTable"></div>
  </div>
</section>

<!-- GENERALIZATION -->
<section id="generalization" class="section">
  <div class="stat-grid" id="genStatGrid"></div>
  <div class="two-col" style="margin-top:0">
    <div class="panel">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <div class="panel-title" style="margin:0">🏆 Promoted memories</div>
        <button class="btn" style="font-size:11px;padding:4px 10px" onclick="loadGeneralization()">↺ Refresh</button>
      </div>
      <div id="genLoading" class="loading-overlay"><div class="spinner"></div> Loading…</div>
      <div id="genPromotedList"></div>
    </div>
    <div class="panel">
      <div class="panel-title">🗂 Scope registry</div>
      <div id="genScopeRegistry"></div>
    </div>
  </div>
</section>

<!-- DB HEALTH -->
<section id="db" class="section">
  <div class="panel">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div class="panel-title" style="margin:0">💾 Database health</div>
      <button class="btn" onclick="loadDbHealth()">↺ Refresh</button>
    </div>
    <div id="dbHealthLoading" class="loading-overlay"><div class="spinner"></div></div>
    <div id="dbHealth"></div>
  </div>
</section>
</main>

<script>
const REFRESH_MS=__REFRESH_MS__;
const ALLOW_ACTIONS=__ALLOW_ACTIONS__;

const statusColor={active:"#3ecf6e",needs_review:"#f5b942",contradicted:"#f04e6a",superseded:"#9d71f0",archived:"#5a6e91"};
const relColor={reinforces:"#3ecf6e",refines:"#4f9bff",contradicts:"#f04e6a",supersedes:"#f5b942",related_to:"#5a6e91",part_of:"#34c4c4"};
const relLabel={reinforces:"reinforces",refines:"refines",contradicts:"contradicts",supersedes:"supersedes",related_to:"related",part_of:"part of"};

function esc(s){return String(s??"")
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  .replace(/"/g,"&quot;").replace(/'/g,"&#39;");}
function fmtBytes(n){n=Number(n||0);if(n<1024)return n+" B";if(n<1048576)return (n/1024).toFixed(1)+" KB";return (n/1048576).toFixed(2)+" MB";}
function fmtTs(ts){if(!ts)return "—";return new Date(Number(ts)*1000).toLocaleString();}
function fmtDate(ts){if(!ts)return "—";return new Date(Number(ts)*1000).toLocaleDateString();}
function age(s){s=Number(s||0);if(s<60)return s+"s";if(s<3600)return Math.floor(s/60)+"m";if(s<86400)return Math.floor(s/3600)+"h "+Math.floor((s%3600)/60)+"m";return Math.floor(s/86400)+"d";}
function dur(s){if(s==null||s===undefined)return "open";s=Number(s);if(s<1)return "<1s";return age(s);}
function num(n){return Number(n||0).toLocaleString();}
async function getJSON(url){const r=await fetch(url);return await r.json();}
async function postJSON(url,obj){const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(obj)});return await r.json();}

// ── TOOLTIP ──
const ttEl=document.getElementById("tooltip");
function showTip(e,html){ttEl.innerHTML=html;ttEl.style.display="block";moveTip(e);}
function moveTip(e){const x=e.clientX,y=e.clientY,w=ttEl.offsetWidth,h=ttEl.offsetHeight;ttEl.style.left=Math.min(x+12,window.innerWidth-w-8)+"px";ttEl.style.top=Math.min(y+12,window.innerHeight-h-8)+"px";}
function hideTip(){ttEl.style.display="none";}
document.addEventListener("mousemove",moveTip);

// ── TABS ──
document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));
  document.querySelectorAll(".section").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  document.getElementById(b.dataset.tab).classList.add("active");
  const tab=b.dataset.tab;
  if(tab==="processes")loadProcesses();
  else if(tab==="schemas")loadSchemas();
  else if(tab==="procedures")loadProcedures();
  else if(tab==="graph")loadGraph();
  else if(tab==="worker")loadWorker();
  else if(tab==="generalization")loadGeneralization();
  else if(tab==="db")loadDbHealth();
});

// ── HELPERS ──
function pill(status){
  return `<span class="pill pill-${esc(status)}">${esc(status)}</span>`;
}
function salBar(val,max){
  const pct=Math.min(100,Math.round(val/Math.max(0.001,max)*100));
  return `<div class="sal-bar-wrap"><div class="sal-bar-track"><div class="sal-bar-fill" style="width:${pct}%"></div></div></div>`;
}
function confBar(val){
  const pct=Math.round(val*100);
  return `<div class="conf-bar"><div class="conf-track"><div class="conf-fill" style="width:${pct}%"></div></div><span style="font-size:11px;color:var(--muted)">${pct}%</span></div>`;
}
function table(head,rows,rawCols=[]){
  if(!rows.length)return emptyState("No data.");
  const ths=head.map(h=>`<th>${esc(h)}</th>`).join("");
  const trs=rows.map((r,ri)=>{
    const tds=r.map((c,ci)=>`<td>${rawCols.includes(ci)?c:esc(c)}</td>`).join("");
    return `<tr>${tds}</tr>`;
  }).join("");
  return `<div class="table-wrap"><table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></div>`;
}
function emptyState(msg,icon="📭"){
  return `<div class="empty-state"><div class="es-icon">${icon}</div><div class="es-text">${esc(msg)}</div></div>`;
}

// ── OVERVIEW ──
async function loadStatus(){
  const d=await getJSON("/api/status");
  window.lastStatus=d;
  document.getElementById("dbPath").textContent=d.db_path;
  document.getElementById("dbPath").title=d.db_path;
  document.getElementById("lastUpdated").textContent="Updated "+new Date().toLocaleTimeString();

  // Init salience slider once we have data
  if(!window.salienceSliderInitialized){initSalienceSlider(d);}

  const s=d.stats||{}, h=d.schema_health||{};
  const maxSal=Number(h?.active_salience?.max||1);

  // STAT CARDS
  const cards=[
    {icon:"💬",label:"Sessions",val:num(s.sessions),sub:"total",accent:"var(--cyan)"},
    {icon:"⚡",label:"Raw events",val:num(s.raw_events),sub:"logged",accent:"var(--blue)"},
    {icon:"🎞",label:"Episodes",val:num(s.episodes),sub:"formed",accent:"var(--blue)"},
    {icon:"🔵",label:"Prototypes",val:num(s.prototypes),sub:"semantic",accent:"var(--purple)"},
    {icon:"📖",label:"Schemas",val:num(s.schemas),sub:h.schemas_by_status?statusBreakdown(h.schemas_by_status):"",accent:"var(--green)",raw:true},
    {icon:"🟢",label:"Active",val:num(h.active_schemas),sub:`avg sal ${Number(h?.active_salience?.avg||0).toFixed(2)}`,accent:"var(--green)"},
    {icon:"🟡",label:"Needs review",val:num(h.needs_review_schemas),sub:h.needs_review_schemas>0?"⚠️ action needed":"clean",accent:h.needs_review_schemas>0?"var(--amber)":"var(--green)"},
    {icon:"🧭",label:"Procedures",val:num(s.procedures),sub:"stored",accent:"var(--cyan)"},
    {icon:"🕸",label:"Edges",val:num(s.edges),sub:"prototype",accent:"var(--purple)"},
    {icon:"🔗",label:"Relations",val:num(s.schema_relations),sub:"schema",accent:"var(--purple)"},
    {icon:"🗣",label:"Feedback",val:num(s.feedback_events),sub:"events",accent:"var(--cyan)"},
    {icon:"🌐",label:"Promoted",val:num(s.promoted_schemas),sub:"stage ≥ 1",accent:"var(--amber)"},
    {icon:"✨",label:"Global",val:num(s.global_schemas),sub:"stage 3",accent:"var(--green)"},
    {icon:"🗺",label:"Known scopes",val:num(s.known_scopes),sub:"registered",accent:"var(--cyan)"},
    {icon:"💾",label:"DB size",val:fmtBytes(d.db_size_bytes),sub:d.wal_size_bytes>0?"WAL: "+fmtBytes(d.wal_size_bytes):"",accent:"var(--muted)"},
  ];
  document.getElementById("statGrid").innerHTML=cards.map(c=>{
    return `<div class="stat-card" style="--accent:${c.accent}">
      <div class="sc-icon">${c.icon}</div>
      <div class="sc-label">${esc(c.label)}</div>
      <div class="sc-value">${c.raw?c.val:esc(String(c.val??0))}</div>
      <div class="sc-sub">${c.raw?c.sub:esc(c.sub||"")} </div>
    </div>`;
  }).join("");

  // ALERTS
  const warns=d.warnings||[];
  let alertHtml="";
  if(!d.db_exists){
    alertHtml=`<div class="alert alert-error"><span class="alert-icon">❌</span><div><b>Database not found</b><br>Path: ${esc(d.db_path)}</div></div>`;
  } else if(warns.length){
    alertHtml=`<div class="alert alert-warn"><span class="alert-icon">⚠️</span><div><b>${warns.length} warning${warns.length>1?"s":""}</b><ul>${warns.map(w=>`<li>${esc(w)}</li>`).join("")}</ul></div></div>`;
    // Update badge
    document.querySelectorAll(".tab[data-tab=processes] .tab-badge").forEach(b=>{b.textContent=warns.length;b.classList.add("show");});
  } else {
    alertHtml=`<div class="alert alert-ok"><span class="alert-icon">✅</span><div><b>All systems healthy</b> — no warnings detected.</div></div>`;
    document.querySelectorAll(".tab[data-tab=processes] .tab-badge").forEach(b=>{b.classList.remove("show");});
  }
  document.getElementById("alertArea").innerHTML=alertHtml;

  // SCHEMA HEALTH PANEL
  const byStatus=h.schemas_by_status||{};
  const total=Math.max(1,h.schemas_total||0);
  const statusOrder=["active","needs_review","contradicted","superseded","archived"];
  const barSegs=statusOrder.map(st=>{
    const n=byStatus[st]||0;
    const pct=Math.round(n/total*100);
    return n>0?`<div class="status-bar-seg" style="width:${pct}%;background:${statusColor[st]||"#5a6e91"}"
      title="${st}: ${n}"></div>`:"";
  }).join("");
  const sal=h.active_salience||{};
  const avgSal=Number(sal.avg||0);
  const maxSalience=Number(sal.max||0);
  const salPct=maxSalience>0?Math.round(avgSal/maxSalience*100):0;
  const lastConsolidated=d.last_consolidation_ts?"Last session: "+fmtTs(d.last_consolidation_ts):"No sessions yet";
  const procCount=num(s.procedures);
  document.getElementById("schemaHealthPanel").innerHTML=`
    <div class="status-bar">${barSegs||"<div class=\"status-bar-seg\" style=\"width:100%;background:var(--line)\"></div>"}</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin:8px 0">
      ${statusOrder.map(st=>{
        const n=byStatus[st]||0;
        return n>0?`<span class="pill pill-${st}">${st} ${num(n)}</span>`:"";
      }).join("")}
    </div>
    <div style="margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
      <div><span style="color:var(--muted)">Avg salience</span><br><b>${avgSal.toFixed(3)}</b></div>
      <div><span style="color:var(--muted)">Max salience</span><br><b>${maxSalience.toFixed(3)}</b></div>
      <div><span style="color:var(--muted)">Duplicates</span><br><b>${num(h.active_exact_duplicate_rows||0)}</b></div>
      <div><span style="color:var(--muted)">Procedures</span><br><b>${procCount}</b></div>
    </div>
    <div style="margin-top:10px;font-size:11px;color:var(--muted)">${esc(lastConsolidated)}</div>
  `;

  // PROCESS MINI
  const procs=d.processes||[];
  const staleMcp=procs.filter(p=>p.kind==="mcp"&&p.age_seconds>600);
  const killAllBtn=document.getElementById("killAllBtn");
  if(killAllBtn) killAllBtn.style.display=staleMcp.length&&ALLOW_ACTIONS?"":"none";
  if(!procs.length){
    document.getElementById("processMini").innerHTML="<div style='color:var(--muted);font-size:13px'>No slowave processes detected.</div>";
  } else {
    document.getElementById("processMini").innerHTML=procs.map(p=>{
      const badge=p.orphaned?`<span class="pill pill-orphan">orphan</span>`:`<span class="pill pill-ok">healthy</span>`;
      const stale=p.kind==="mcp"&&p.age_seconds>600?`<span class="pill pill-warn" style="font-size:10px">stale</span>`:"";
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line);font-size:13px">
        <div><span class="pill pill-${esc(p.kind)}">${esc(p.kind)}</span> PID ${p.pid} ${stale}</div>
        <div style="color:var(--muted);font-size:11px">${age(p.age_seconds)} · ${fmtBytes(p.rss_kb*1024)}</div>
        ${badge}
      </div>`;
    }).join("");
  }

  // RECENT SESSIONS
  const sess=d.recent_sessions||[];
  if(!sess.length){
    document.getElementById("recentSessions").innerHTML=emptyState("No sessions yet.","💬");
  } else {
    document.getElementById("recentSessions").innerHTML=table(
      ["Session","Agent","Scope","Started","Duration","Events","Ep."],
      sess.map(r=>[
        r.id,r.agent||"—",r.scope_id||"(none)",
        fmtTs(r.started_ts),dur(r.duration_seconds),
        num(r.events),num(r.episodes)
      ])
    );
  }

  // SCOPES
  const scopes=d.scopes||[];
  if(!scopes.length){
    document.getElementById("scopesPanel").innerHTML=emptyState("No scopes.","🗂");
  } else {
    document.getElementById("scopesPanel").innerHTML=table(
      ["Scope","Sessions"],
      scopes.map(r=>[r.scope,num(r.sessions)])
    );
  }
}

function statusBreakdown(by){
  const statusOrder=["active","needs_review","contradicted","superseded","archived"];
  return statusOrder
    .filter(s=>by[s]>0)
    .map(s=>`<span class="pill pill-${s}" style="font-size:10px">${s[0].toUpperCase()} ${by[s]}</span>`)
    .join("");
}

// ── SCHEMAS ──
let schemaMaxSalience=1;
async function loadSchemas(){
  const el=document.getElementById("schemaTable");
  const ld=document.getElementById("schemaLoading");
  ld.classList.add("show");el.innerHTML="";
  document.getElementById("schemaDetail").innerHTML="";
  try{
    const st=document.getElementById("schemaStatus").value;
    const sc=encodeURIComponent(document.getElementById("schemaScope").value);
    const q=encodeURIComponent(document.getElementById("schemaQ").value);
    const lim=document.getElementById("schemaLimit").value;
    const d=await getJSON(`/api/schemas?limit=${lim}&status=${encodeURIComponent(st)}&scope=${sc}&q=${q}`);
    schemaMaxSalience=Math.max(1,...(d.schemas||[]).map(s=>s.salience));
    el.innerHTML=renderSchemasTable(d.schemas||[]);
    // attach expand handlers
    el.querySelectorAll("tr.expandable").forEach(tr=>{
      tr.addEventListener("click",()=>expandSchemaRow(tr,parseInt(tr.dataset.id)));
    });
  } finally{ld.classList.remove("show");}
}
function renderSchemasTable(schemas){
  if(!schemas.length)return emptyState("No schemas found.","📖");
  const rows=schemas.map(s=>{
    const salPct=Math.round(s.salience/Math.max(0.001,schemaMaxSalience)*100);
    const salHtml=`<span style="font-size:12px;font-weight:600">${s.salience.toFixed(3)}</span>
      <div class="sal-bar-track" style="width:50px;display:inline-block;vertical-align:middle;margin-left:4px">
        <div class="sal-bar-fill" style="width:${salPct}%"></div></div>`;
    const confHtml=confBar(s.confidence);
    const tagsHtml=(s.tags||[]).map(t=>`<span class="pill" style="font-size:10px">${esc(t)}</span>`).join("");
    const nr=s.needs_review?`<span class="pill pill-warn" style="font-size:10px">⚠ review</span>`:""
    const stage=s.generalization_stage||0;
    const stageBadge=stage>0?`<span class="gen-badge gen-${stage}" style="font-size:10px">${GEN_LABELS[stage]||stage}</span>`:`<span class="gen-badge gen-0" style="font-size:10px">SCOPED</span>`;
    return `<tr class="expandable" data-id="${s.schema_id}">
      <td><code style="font-size:11px">sch_${s.schema_id}</code></td>
      <td>${pill(s.status)}${nr}</td>
      <td>${salHtml}</td>
      <td>${confHtml}</td>
      <td>${stageBadge}</td>
      <td>${esc(s.schema_class||"—")}</td>
      <td>${esc(s.scope||"—")}</td>
      <td>${num(s.support_count)}</td>
      <td style="max-width:380px;word-break:break-word">${esc(s.content)}</td>
    </tr>`;
  }).join("");
  return `<table><thead><tr>
    <th>ID</th><th>Status</th><th>Salience</th><th>Confidence</th>
    <th>Stage</th><th>Class</th><th>Scope</th><th>Support</th><th>Content</th>
  </tr></thead><tbody>${rows}</tbody></table>`;
}
async function expandSchemaRow(tr,schemaId){
  // Toggle existing
  const nextTr=tr.nextElementSibling;
  if(nextTr&&nextTr.classList.contains("expand-row")){
    nextTr.remove();return;
  }
  const d=await getJSON(`/api/schemas/${schemaId}`);
  const s=d.schema;
  const evHtml=d.evidence&&d.evidence.length?table(["Episode","Event","Weight","Quote"],
    d.evidence.map(e=>[e.episode_id?`epi_${e.episode_id}`:"—",e.raw_event_id?`evt_${e.raw_event_id}`:"—",
      Number(e.weight||0).toFixed(3),e.quote||"—"])):"<em style='color:var(--muted)'>No evidence.</em>";
  const outHtml=d.outgoing&&d.outgoing.length?table(["To","Relation","Confidence","Reason"],
    d.outgoing.map(e=>[`sch_${e.dst_schema_id}`,e.relation,Number(e.confidence||0).toFixed(2),e.reason||"—"])):"<em style='color:var(--muted)'>None.</em>";
  const inHtml=d.incoming&&d.incoming.length?table(["From","Relation","Confidence","Reason"],
    d.incoming.map(e=>[`sch_${e.src_schema_id}`,e.relation,Number(e.confidence||0).toFixed(2),e.reason||"—"])):"<em style='color:var(--muted)'>None.</em>";
  const expTr=document.createElement("tr");
  expTr.className="expand-row";
  const stage=s.generalization_stage||0;
  const genHtml=`<div class="detail-section"><h4>Generalization</h4>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      ${genBadge(stage)}
      <span style="font-size:12px;color:var(--muted)">${GEN_DESC[stage]||""}</span>
    </div>
    ${stage>0?`
      ${genBreadthBar((s.scope_breadth_pct||0),"scope breadth")}
      ${genBreadthBar((s.scope_kind_breadth_pct||0),"kind breadth")}
      <div style="font-size:11px;color:var(--muted);margin-top:4px">
        ${(s.distinct_scope_count||0)} scope${s.distinct_scope_count!==1?"s":""} ·
        ${(s.distinct_scope_kind_count||0)} kind${s.distinct_scope_kind_count!==1?"s":""} ·
        ${(s.cross_scope_recall_count||0)} cross-scope recall${s.cross_scope_recall_count!==1?"s":""}
      </div>`:"<div style='font-size:12px;color:var(--muted)'>Not yet recalled across multiple scopes.</div>"}
  </div>`;
  expTr.innerHTML=`<td colspan="9"><div class="expand-content">
    <div class="three-col">
      <div>
        <div class="detail-section"><h4>Facets</h4><pre class="code-block">${esc(JSON.stringify(s.facets,null,2))}</pre></div>
        ${genHtml}
      </div>
      <div>
        <div class="detail-section"><h4>Tags</h4>${(s.tags||[]).map(t=>`<span class="pill">${esc(t)}</span>`).join("")||"<em style='color:var(--muted)'>none</em>"}</div>
        <div class="detail-section" style="margin-top:10px"><h4>Timestamps</h4>
          <div style="font-size:12px;color:var(--muted)">First formed: ${fmtTs(s.first_formed_ts)}<br>Updated: ${fmtTs(s.last_updated_ts)}</div>
        </div>
      </div>
      <div><div class="detail-section"><h4>Outgoing relations</h4>${outHtml}</div>
           <div class="detail-section" style="margin-top:10px"><h4>Incoming relations</h4>${inHtml}</div></div>
    </div>
    <div class="detail-section"><h4>Evidence</h4>${evHtml}</div>
  </div></td>`;
  tr.after(expTr);
}

// ── PROCEDURES ──
async function loadProcedures(){
  const ld=document.getElementById("procLoading");
  const list=document.getElementById("procList");
  ld.classList.add("show");list.innerHTML="";
  try{
    const sc=encodeURIComponent(document.getElementById("procScope").value);
    const st=encodeURIComponent(document.getElementById("procStatus").value);
    const lim=document.getElementById("procLimit").value;
    const d=await getJSON(`/api/procedures?limit=${lim}&scope=${sc}&status=${st}`);
    const procs=d.procedures||[];
    if(!procs.length){list.innerHTML=emptyState("No procedures stored yet.","🧭");return;}
    list.innerHTML=procs.map(p=>{
      const steps=(p.steps||[]).map((s,i)=>`<li><strong>${i+1}.</strong> ${esc(s)}</li>`).join("");
      const triggers=(p.trigger_pattern||[]).map(t=>`<span class="pill">${esc(t)}</span>`).join("");
      const confPct=Math.round((p.confidence||0)*100);
      return `<div class="proc-card">
        <div class="proc-header">
          <div>
            <div class="proc-goal">${esc(p.goal||"(no goal)")}</div>
            <div class="proc-meta">
              ${pill(p.status)}
              ${p.task_type?`<span class="pill">${esc(p.task_type)}</span>`:""}
              ${p.scope?`<span class="pill">${esc(p.scope)}</span>`:""}
              <span class="pill">proc_${p.id}</span>
            </div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="font-size:12px;color:var(--muted)">Confidence</div>
            ${confBar(p.confidence||0)}
          </div>
        </div>
        ${triggers?`<div style="margin-bottom:8px;font-size:12px;color:var(--muted)">Triggers: ${triggers}</div>`:""}
        <div class="proc-steps"><ol>${steps}</ol></div>
        <div style="margin-top:8px;font-size:11px;color:var(--muted)">Created ${fmtDate(p.created_at)} · Updated ${fmtDate(p.updated_at)}</div>
      </div>`;
    }).join("");
  }finally{ld.classList.remove("show");}
}

// ── PROCESSES ──
async function loadProcesses(){
  const ld=document.getElementById("processLoading");
  ld.classList.add("show");
  try{
    const d=await getJSON("/api/processes");
    const procs=d.processes||[];
    if(!procs.length){
      document.getElementById("processTable").innerHTML=emptyState("No slowave processes found.","⚙️");
      return;
    }
    const heads=["PID","Kind","PPID","Stat","Age","RSS","Status","Command","Parent"];
    if(ALLOW_ACTIONS) heads.push("Kill");
    const rows=procs.map(p=>{
      const killBtn=ALLOW_ACTIONS
        ?`<button class="btn" style="padding:4px 10px;font-size:11px;color:var(--red);border-color:var(--red)"
            onclick="killProc(${p.pid},this)">✕ kill</button>`
        :`<span style="font-size:11px;color:var(--muted)" title="Restart dashboard with --allow-actions to enable">locked</span>`;
      const row=[
        `<b>${p.pid}</b>`,
        `<span class="pill pill-${esc(p.kind)}">${esc(p.kind)}</span>`,
        p.ppid,p.stat,age(p.age_seconds),fmtBytes(p.rss_kb*1024),
        p.orphaned?`<span class="pill pill-orphan">orphaned</span>`:`<span class="pill pill-ok">healthy</span>`,
        `<code style="font-size:11px">${esc((p.command||"").slice(0,80))}</code>`,
        `<code style="font-size:11px">${esc((p.parent_command||"").slice(0,60))}</code>`,
      ];
      if(ALLOW_ACTIONS) row.push(killBtn);
      return row;
    });
    const rawCols=[0,1,6,7,8,...(ALLOW_ACTIONS?[9]:[])];
    document.getElementById("processTable").innerHTML=table(heads,rows,rawCols);
    if(!ALLOW_ACTIONS){
      document.getElementById("processTable").insertAdjacentHTML("afterbegin",
        `<div class="alert alert-warn" style="margin-bottom:8px"><span class="alert-icon">🔒</span>
         <div>Kill buttons are <b>disabled</b>. Restart with <code>slowave dashboard --allow-actions</code> to enable them.
         Or use the quick-kill command: <code>pkill -f slowave-mcp</code></div></div>`);
    }
  }finally{ld.classList.remove("show");}
}

async function killProc(pid,btn){
  if(!confirm(`Send SIGTERM to PID ${pid}?`)) return;
  btn.disabled=true;btn.textContent="…";
  try{
    const d=await postJSON("/api/processes/kill",{pid,signal:"TERM"});
    if(d.ok){
      btn.textContent="✓ sent";btn.style.color="var(--green)";
      setTimeout(loadProcesses,1500);
    } else {
      btn.textContent="✕ err";btn.style.color="var(--red)";
      alert("Error: "+(d.error||JSON.stringify(d)));
      btn.disabled=false;
    }
  }catch(e){btn.textContent="✕ err";btn.disabled=false;alert(String(e));}
}


// ── WORKER ──
async function loadWorker(){
  const ld=document.getElementById("workerLoading");
  const tbl=document.getElementById("workerTable");
  const chart=document.getElementById("workerChart");
  ld.classList.add("show");tbl.innerHTML="";chart.innerHTML="";
  try{
    const lim=document.getElementById("workerLimit").value;
    const d=await getJSON(`/api/worker/runs?limit=${lim}`);
    const runs=d.runs||[];
    const sum=d.summary||{};

    // Stat cards
    const cards=[
      {icon:"🔄",label:"Total passes",val:num(sum.total_passes),accent:"var(--blue)"},
      {icon:"📖",label:"Schemas created",val:num(sum.total_schemas_created),accent:"var(--green)"},
      {icon:"🔁",label:"Reinforced",val:num(sum.total_schemas_reinforced),accent:"var(--cyan)"},
      {icon:"⏱",label:"Avg duration",val:(sum.avg_duration_ms||0).toFixed(0)+"ms",accent:"var(--amber)"},
      {icon:"🕐",label:"Last run",val:fmtTs(sum.last_run_ts),accent:"var(--muted)",raw:true},
    ];
    document.getElementById("workerStatGrid").innerHTML=cards.map(c=>
      `<div class="stat-card" style="--accent:${c.accent}">
        <div class="sc-icon">${c.icon}</div>
        <div class="sc-label">${esc(c.label)}</div>
        <div class="sc-value">${c.raw?c.val:esc(String(c.val))}</div>
      </div>`
    ).join("");

    // Mini bar chart: schemas created per run (last 20)
    const chartRuns=runs.slice(0,20).reverse();
    if(chartRuns.length){
      const maxCreated=Math.max(1,...chartRuns.map(r=>r.schemas_created||0));
      chart.innerHTML=`
        <div style="display:flex;align-items:flex-end;gap:3px;height:48px;padding:0 2px">
          ${chartRuns.map(r=>{
            const h=Math.round(((r.schemas_created||0)/maxCreated)*44)+4;
            const color=r.error_text?"var(--red)":"var(--blue)";
            return `<div title="${fmtTs(r.started_ts)}: +${r.schemas_created||0} schemas"
              style="flex:1;height:${h}px;background:${color};border-radius:2px 2px 0 0;min-width:4px;opacity:.8"></div>`;
          }).join("")}
        </div>
        <div style="font-size:10px;color:var(--muted);margin-top:3px">schemas created per pass (last ${chartRuns.length})</div>`;
    }

    // Table
    if(!runs.length){
      tbl.innerHTML=emptyState("No worker runs recorded yet. Start the worker with: slowave worker","🧠");
      return;
    }
    const heads=["#","Started","Duration","Trigger","Schemas +","~Reinf.","Protos","Status"];
    const rows=runs.map(r=>[
      r.id,
      fmtTs(r.started_ts),
      r.duration_ms!=null?r.duration_ms+"ms":"—",
      r.triggered_by||"worker",
      `<b style="color:var(--green)">+${r.schemas_created||0}</b>`,
      num(r.schemas_reinforced||0),
      num(r.prototypes_processed||0),
      r.error_text
        ?`<span class="pill pill-contradicted" title="${esc(r.error_text)}">error</span>`
        :`<span class="pill pill-active">ok</span>`,
    ]);
    const rawCols=[4,7];
    tbl.innerHTML=table(heads,rows,rawCols);
  }finally{ld.classList.remove("show");}
}

async function killAllStaleMcp(){
  const d=await getJSON("/api/processes");
  const stale=(d.processes||[]).filter(p=>p.kind==="mcp"&&p.age_seconds>600);
  if(!stale.length){alert("No stale MCP processes found.");return;}
  if(!confirm(`Kill ${stale.length} stale slowave-mcp process${stale.length>1?"es":""} (age > 10 min)?`)) return;
  let ok=0,fail=0;
  for(const p of stale){
    const r=await postJSON("/api/processes/kill",{pid:p.pid,signal:"TERM"});
    if(r.ok) ok++; else fail++;
  }
  alert(`Sent SIGTERM: ${ok} succeeded, ${fail} failed.`);
  setTimeout(()=>{loadStatus();if(document.querySelector(".tab[data-tab=processes].active"))loadProcesses();},1500);
}

// ── GRAPH ──
function initSalienceSlider(status){
  if(window.salienceSliderInitialized)return;
  const maxSal=Number(status?.schema_health?.active_salience?.max||25);
  const upper=Math.max(1,Math.ceil(maxSal));
  const minEl=document.getElementById("graphMinSalience");
  if(!minEl)return;
  minEl.max=String(upper);
  document.getElementById("graphObservedMaxSalienceLabel").textContent=maxSal.toFixed(2);
  window.salienceSliderInitialized=true;
  syncSalienceSlider(false);
}
function syncSalienceSlider(autoLoad=true){
  const minEl=document.getElementById("graphMinSalience");
  const min=Number(minEl.value);
  document.getElementById("graphMinSalienceLabel").textContent=min.toFixed(2);
  clearTimeout(window.salienceLoadTimer);
  if(autoLoad)window.salienceLoadTimer=setTimeout(loadGraph,400);
}
function resetSalienceSlider(){
  document.getElementById("graphMinSalience").value="0";
  syncSalienceSlider();
}
async function loadGraph(){
  const sts=[...document.querySelectorAll(".gstat:checked")].map(x=>x.value).join(",");
  const lim=document.getElementById("graphLimit").value;
  const scope=encodeURIComponent(document.getElementById("graphScope").value);
  const minSal=encodeURIComponent(document.getElementById("graphMinSalience").value);
  const d=await getJSON(`/api/graph/schemas?limit=${lim}&statuses=${sts}&scope=${scope}&min_salience=${minSal}`);
  renderLegend();
  drawGraph(d);
}
function renderLegend(){
  const statusEntries=Object.entries(statusColor).map(([k,v])=>`<div class="legend-item"><div class="legend-dot" style="background:${v}"></div>${k}</div>`).join("");
  const relEntries=Object.entries(relColor).map(([k,v])=>`<div class="legend-item"><div class="legend-line" style="background:${v}"></div>${relLabel[k]||k}</div>`).join("");
  document.getElementById("graphLegend").innerHTML=`
    <div style="font-size:11px;color:var(--muted);font-weight:600;margin-right:4px">Nodes:</div>${statusEntries}
    <div style="width:1px;background:var(--line);margin:0 6px"></div>
    <div style="font-size:11px;color:var(--muted);font-weight:600;margin-right:4px">Edges:</div>${relEntries}
  `;
}
function drawGraph(g){
  const svg=document.getElementById("schemaGraph");
  svg.innerHTML=`<defs>
    <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L8,3 z" fill="#7a8db5" opacity="0.8"/>
    </marker>
    <filter id="glow"><feGaussianBlur stdDeviation="2" result="coloredBlur"/>
      <feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>`;
  const w=svg.clientWidth||900,h=svg.clientHeight||660,cx=w/2,cy=h/2;
  const nodes=g.nodes||[],edges=g.edges||[];
  if(!nodes.length){
    const t=document.createElementNS("http://www.w3.org/2000/svg","text");
    t.setAttribute("x",cx);t.setAttribute("y",cy);
    t.setAttribute("text-anchor","middle");t.setAttribute("fill","#5a6e91");t.setAttribute("font-size","14");
    t.textContent="No nodes for selected filters";
    svg.appendChild(t);return;
  }
  const byId=Object.fromEntries(nodes.map(n=>[n.id,n]));
  // Initial layout: spiral
  nodes.forEach((n,i)=>{
    const a=2*Math.PI*i/Math.max(1,nodes.length);
    const r=Math.min(w,h)*(0.25+0.2*((i%5)/5));
    n.x=cx+Math.cos(a)*r;n.y=cy+Math.sin(a)*r;
    n.vx=0;n.vy=0;
  });
  // Force-directed layout
  for(let iter=0;iter<120;iter++){
    nodes.forEach(n=>{n.vx*=0.78;n.vy*=0.78;});
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
      const a=nodes[i],b=nodes[j],dx=a.x-b.x,dy=a.y-b.y;
      const d2=dx*dx+dy*dy+0.01,d=Math.sqrt(d2),force=1100/d2;
      a.vx+=dx/d*force;b.vx-=dx/d*force;
      a.vy+=dy/d*force;b.vy-=dy/d*force;
    }
    edges.forEach(e=>{
      const a=byId[e.source],b=byId[e.target];
      if(!a||!b)return;
      const dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)+0.01,force=(d-160)*0.003;
      a.vx+=dx/d*force;b.vx-=dx/d*force;
      a.vy+=dy/d*force;b.vy-=dy/d*force;
    });
    // center gravity
    nodes.forEach(n=>{
      n.vx+=(cx-n.x)*0.002;n.vy+=(cy-n.y)*0.002;
      n.x=Math.max(24,Math.min(w-24,n.x+n.vx));
      n.y=Math.max(24,Math.min(h-24,n.y+n.vy));
    });
  }
  // Draw edges
  edges.forEach(e=>{
    const a=byId[e.source],b=byId[e.target];
    if(!a||!b)return;
    const color=relColor[e.relation]||"#5a6e91";
    const sw=1.5+2*(e.confidence||0.5);
    // offset for arrow
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)+0.01;
    const x2=b.x-dx/d*12,y2=b.y-dy/d*12;
    const line=document.createElementNS("http://www.w3.org/2000/svg","line");
    line.setAttribute("x1",a.x);line.setAttribute("y1",a.y);
    line.setAttribute("x2",x2);line.setAttribute("y2",y2);
    line.setAttribute("class","edge");line.setAttribute("stroke",color);
    line.setAttribute("stroke-width",sw);line.setAttribute("marker-end","url(#arrow)");
    line.addEventListener("mouseenter",ev=>showTip(ev,`<b>${e.relation}</b><br>sch_${e.src_schema_id} → sch_${e.dst_schema_id}<br>confidence: ${Number(e.confidence||0).toFixed(2)}${e.reason?`<br><em>${esc(e.reason)}</em>`:""}`) );
    line.addEventListener("mouseleave",hideTip);
    svg.appendChild(line);
    // edge label mid-point
    const t=document.createElementNS("http://www.w3.org/2000/svg","text");
    t.setAttribute("x",(a.x+b.x)/2);t.setAttribute("y",(a.y+b.y)/2-3);
    t.setAttribute("class","edge-label");t.setAttribute("text-anchor","middle");
    t.setAttribute("fill",color);t.textContent=relLabel[e.relation]||e.relation;
    svg.appendChild(t);
  });
  // Draw nodes
  nodes.forEach(n=>{
    const r=8+Math.min(18,Math.sqrt(Math.max(0,n.salience))*3.5);
    const color=statusColor[n.status]||"#5a6e91";
    const c=document.createElementNS("http://www.w3.org/2000/svg","circle");
    c.setAttribute("cx",n.x);c.setAttribute("cy",n.y);c.setAttribute("r",r);
    c.setAttribute("fill",color);c.setAttribute("fill-opacity","0.85");
    c.setAttribute("stroke",color);c.setAttribute("stroke-width","1.5");
    c.setAttribute("class","node");
    c.addEventListener("mouseenter",ev=>showTip(ev,`<b>sch_${n.schema_id}</b><br><span style="color:#7a8db5">${esc(n.status)}</span> · sal ${Number(n.salience).toFixed(3)}<br><em>${esc(n.label)}</em>`));
    c.addEventListener("mouseleave",hideTip);
    c.onclick=()=>selectGraphNode(n,c);
    svg.appendChild(c);
    // short label
    const lab=document.createElementNS("http://www.w3.org/2000/svg","text");
    lab.setAttribute("x",n.x+r+3);lab.setAttribute("y",n.y+4);
    lab.setAttribute("class","node-label");lab.textContent=`sch_${n.schema_id}`;
    svg.appendChild(lab);
  });
}
async function selectGraphNode(n,el){
  document.querySelectorAll(".node").forEach(x=>x.classList.remove("selected"));
  el.classList.add("selected");
  const d=await getJSON(`/api/schemas/${n.schema_id}`);
  const s=d.schema||n;
  const evHtml=d.evidence&&d.evidence.length
    ?table(["Ep.","Evt.","Weight","Quote"],d.evidence.map(e=>[
        e.episode_id?`epi_${e.episode_id}`:"—",e.raw_event_id?`evt_${e.raw_event_id}`:"—",
        Number(e.weight||0).toFixed(3),e.quote||"—"]))
    :"<em style='color:var(--muted)'>No evidence.</em>";
  const outHtml=d.outgoing&&d.outgoing.length
    ?table(["To","Rel.","Conf.","Reason"],d.outgoing.map(e=>[
        `sch_${e.dst_schema_id}`,e.relation,Number(e.confidence||0).toFixed(2),e.reason||"—"]))
    :"<em style='color:var(--muted)'>None.</em>";
  const inHtml=d.incoming&&d.incoming.length
    ?table(["From","Rel.","Conf.","Reason"],d.incoming.map(e=>[
        `sch_${e.src_schema_id}`,e.relation,Number(e.confidence||0).toFixed(2),e.reason||"—"]))
    :"<em style='color:var(--muted)'>None.</em>";
  document.getElementById("graphDetail").innerHTML=`
    <div style="margin-bottom:10px">
      <div style="font-size:16px;font-weight:700">sch_${s.schema_id}</div>
      <div style="margin-top:6px">${pill(s.status)}
        <span class="pill">sal ${Number(s.salience).toFixed(3)}</span>
        <span class="pill">conf ${Number(s.confidence).toFixed(2)}</span>
        ${s.schema_class?`<span class="pill">${esc(s.schema_class)}</span>`:""}
        ${s.needs_review?`<span class="pill pill-warn">⚠ review</span>`:""}
      </div>
    </div>
    <div style="font-size:13px;color:var(--text);line-height:1.6;margin-bottom:12px;padding:10px;background:var(--panel2);border-radius:var(--radius-sm);border:1px solid var(--line)">${esc(s.content)}</div>
    <div class="detail-section"><h4>Facets</h4><pre class="code-block">${esc(JSON.stringify(s.facets,null,2))}</pre></div>
    <div class="detail-section"><h4>Tags</h4>${(s.tags||[]).map(t=>`<span class="pill">${esc(t)}</span>`).join("")||"<em style='color:var(--muted)'>none</em>"}</div>
    <div class="detail-section"><h4>Outgoing relations</h4>${outHtml}</div>
    <div class="detail-section"><h4>Incoming relations</h4>${inHtml}</div>
    <div class="detail-section"><h4>Evidence</h4>${evHtml}</div>
    <div style="margin-top:10px;font-size:11px;color:var(--muted)">First formed: ${fmtTs(s.first_formed_ts)}<br>Last updated: ${fmtTs(s.last_updated_ts)}</div>
  `;
}

// ── RECALL ──
async function runRecall(){
  const query=document.getElementById("recallQuery").value.trim();
  if(!query)return;
  const top_k=parseInt(document.getElementById("recallTopK").value)||5;
  const evidence=document.getElementById("recallEvidence").checked;
  const ld=document.getElementById("recallLoading");
  const res=document.getElementById("recallResults");
  ld.classList.add("show");res.innerHTML="";
  try{
    const d=await postJSON("/api/recall",{query,top_k,evidence});
    if(d.error){
      res.innerHTML=`<div class="alert alert-error"><span class="alert-icon">❌</span><div><b>Error</b><br>${esc(d.error)}</div></div>`;
      return;
    }
    const maxSal=Math.max(1,...(d.schemas||[]).map(s=>s.salience||0));
    let html="";
    if(d.schemas&&d.schemas.length){
      html+=`<div style="font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin:14px 0 6px">📖 Schemas (${d.schemas.length})</div>`;
      html+=table(
        ["ID","Status","Salience","Class","Content"],
        d.schemas.map(s=>[
          `<code style="font-size:11px">sch_${s.id||s.schema_id}</code>`,
          pill(s.status),
          salBar(s.salience||0,maxSal)+` <span style="font-size:11px">${Number(s.salience||0).toFixed(3)}</span>`,
          esc(s.facets?.schema_class||s.schema_class||"—"),
          esc(s.content_text||s.content||"")
        ]),
        [0,1,2]
      );
    }
    if(d.episodes&&d.episodes.length){
      html+=`<div style="font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin:14px 0 6px">🎞 Episodes (${d.episodes.length})</div>`;
      html+=table(
        ["ID","Salience","Date","Content"],
        d.episodes.map(e=>[
          `epi_${e.id}`,
          Number(e.salience||0).toFixed(3),
          fmtDate(e.ts||0),
          esc((e.content_text||"").slice(0,200))
        ]),
        [0]
      );
    }
    if(d.raw_events&&d.raw_events.length){
      html+=`<div style="font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin:14px 0 6px">🗒 Evidence events (${d.raw_events.length})</div>`;
      html+=table(
        ["ID","Type","Content"],
        d.raw_events.map(e=>[`evt_${e.id}`,e.type||"—",esc((e.content||"").slice(0,200))]),
        [0]
      );
    }
    if(!html)html=emptyState("No results for this query.","🔍");
    res.innerHTML=html;
  }finally{ld.classList.remove("show");}
}
// Enter key in recall textarea
document.getElementById("recallQuery").addEventListener("keydown",e=>{
  if(e.key==="Enter"&&(e.metaKey||e.ctrlKey))runRecall();
});

// ── DB HEALTH ──
async function loadDbHealth(){
  const ld=document.getElementById("dbHealthLoading");
  const el=document.getElementById("dbHealth");
  ld.classList.add("show");el.innerHTML="";
  try{
    const d=await getJSON("/api/db/health");
    if(!d.db_exists){
      el.innerHTML=`<div class="alert alert-error"><span class="alert-icon">❌</span><div>Database not found at <code>${esc(d.db_path)}</code></div></div>`;
      return;
    }
    const integrityOk=d.integrity_check&&d.integrity_check.length===1&&d.integrity_check[0]==="ok";
    const fkOk=!d.foreign_key_check||d.foreign_key_check.length===0;
    let html=`
      <div class="two-col" style="margin-bottom:12px">
        <div class="panel">
          <div class="panel-title">Pragmas</div>
          <pre class="code-block">${esc(JSON.stringify(d.pragmas,null,2))}</pre>
        </div>
        <div class="panel">
          <div class="panel-title">Integrity</div>
          <div class="alert ${integrityOk?"alert-ok":"alert-error"}">
            <span class="alert-icon">${integrityOk?"✅":"❌"}</span>
            <div>${integrityOk?"Integrity check passed":`Issues: ${esc(JSON.stringify(d.integrity_check))}`}</div>
          </div>
          <div class="alert ${fkOk?"alert-ok":"alert-warn"}" style="margin-top:8px">
            <span class="alert-icon">${fkOk?"✅":"⚠️"}</span>
            <div>${fkOk?"No FK violations":"FK violations: "+esc(JSON.stringify(d.foreign_key_check))}</div>
          </div>
        </div>
      </div>
    `;
    html+=`<div class="panel"><div class="panel-title">Tables &amp; Views</div>`;
    html+=table(
      ["Name","Type","Row count"],
      (d.tables||[]).map(t=>[t.name,t.type,t.count!=null?num(t.count):"—"])
    );
    html+="</div>";
    el.innerHTML=html;
  }finally{ld.classList.remove("show");}
}

// ── GENERALIZATION ──
const GEN_LABELS=['SCOPED','PORTABLE','CONTEXTUAL','GLOBAL'];
const GEN_COLORS=['var(--gray)','var(--blue)','var(--amber)','var(--green)'];
const GEN_DESC=[
  'Only retrieved within its origin scope',
  'Retrieved across same-kind scopes (e.g. project:* → project:*)',
  'Retrieved everywhere with a relevance floor',
  'Retrieved everywhere with no restriction',
];
function genBadge(stage){
  const lbl=GEN_LABELS[stage]||'SCOPED';
  return `<span class="gen-badge gen-${stage}">${lbl}</span>`;
}
function genBreadthBar(pct,label){
  const w=Math.round(Math.min(100,pct*100));
  return `<div class="gen-bar-wrap">
    <div class="gen-bar-track"><div class="gen-bar" style="width:${w}%"></div></div>
    <span style="font-size:11px;color:var(--muted);white-space:nowrap">${label}: ${(pct*100).toFixed(0)}%</span>
  </div>`;
}
async function loadGeneralization(){
  const ld=document.getElementById("genLoading");
  ld.classList.add("show");
  try{
    const d=await getJSON("/api/generalization");
    const sum=d.summary||{};
    const dist=d.stage_distribution||{};
    // Stat cards
    const cards=[
      {icon:"📖",label:"Total active",val:num(sum.total_active_schemas),accent:"var(--green)"},
      {icon:"🌐",label:"Promoted",val:num(sum.promoted_schemas),sub:"stage ≥ 1",accent:"var(--amber)"},
      {icon:"✨",label:"Global",val:num(sum.global_schemas),sub:"stage 3",accent:"var(--green)"},
      {icon:"🗺",label:"Known scopes",val:num(sum.total_known_scopes),sub:num(sum.total_scope_kinds)+" kinds",accent:"var(--cyan)"},
    ];
    document.getElementById("genStatGrid").innerHTML=cards.map(c=>
      `<div class="stat-card" style="--accent:${c.accent}">
        <div class="sc-icon">${c.icon}</div>
        <div class="sc-label">${esc(c.label)}</div>
        <div class="sc-value">${esc(String(c.val))}</div>
        <div class="sc-sub">${esc(c.sub||"")}</div>
      </div>`
    ).join("");
    // Stage distribution visual
    const totalActive=Math.max(1,sum.total_active_schemas);
    let distHtml='<div style="margin-bottom:14px">';
    [0,1,2,3].forEach(st=>{
      const n=dist[st]||0;const pct=Math.round(n/totalActive*100);
      distHtml+=`<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        ${genBadge(st)}
        <div class="gen-bar-track" style="flex:1"><div class="gen-bar" style="width:${pct}%;background:${GEN_COLORS[st]}"></div></div>
        <span style="font-size:12px;color:var(--muted);width:40px;text-align:right">${num(n)}</span>
      </div>`;
    });
    distHtml+='</div>';
    // Promoted list
    const items=d.top_promoted||[];
    if(!items.length){
      document.getElementById("genPromotedList").innerHTML=distHtml+emptyState("No promoted memories yet. Memories promote as they are recalled across multiple scopes.","🌐");
    } else {
      let listHtml=distHtml;
      items.forEach(m=>{
        listHtml+=`<div style="background:var(--panel2);border:1px solid var(--line);border-radius:var(--radius-sm);padding:10px 14px;margin-bottom:8px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            ${genBadge(m.stage)}
            <code style="font-size:11px;color:var(--muted)">${esc(m.id)}</code>
            <span style="font-size:11px;color:var(--muted)">origin: ${esc(m.scope||"—")}</span>
          </div>
          <div style="font-size:13px;line-height:1.5;margin-bottom:8px">${esc(m.content)}</div>
          ${genBreadthBar(m.scope_breadth_pct||0,"scope breadth")}
          ${genBreadthBar(m.scope_kind_breadth_pct||0,"kind breadth")}
          <div style="font-size:11px;color:var(--muted);margin-top:4px">
            ${m.distinct_scope_count} scope${m.distinct_scope_count!==1?"s":""} · 
            ${m.distinct_scope_kind_count} kind${m.distinct_scope_kind_count!==1?"s":""} · 
            ${m.cross_scope_recall_count} cross-scope recall${m.cross_scope_recall_count!==1?"s":""}
          </div>
        </div>`;
      });
      document.getElementById("genPromotedList").innerHTML=listHtml;
    }
    // Scope registry
    const reg=d.scope_registry||[];
    if(!reg.length){
      document.getElementById("genScopeRegistry").innerHTML=emptyState("No scopes registered yet. Scopes are recorded automatically when sessions start.","🗺");
    } else {
      document.getElementById("genScopeRegistry").innerHTML=reg.map(r=>`
        <div class="scope-reg-card">
          <div>
            <div class="scope-reg-id">${esc(r.scope_id)}</div>
            <div class="scope-reg-meta">${r.scope_kind||"generic"} · last active ${fmtDate(r.last_active_ts)}</div>
          </div>
          <div style="text-align:right;font-size:12px;color:var(--muted)">
            <div>${num(r.session_count)} session${r.session_count!==1?"s":""}</div>
            <div>${num(r.recall_count)} recall${r.recall_count!==1?"s":""}</div>
          </div>
        </div>`).join("");
    }
  }finally{ld.classList.remove("show");}
}

// ── INIT ──
loadStatus();
setInterval(loadStatus,REFRESH_MS);
</script>
</body>
</html>'''
