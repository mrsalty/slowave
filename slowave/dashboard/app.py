"""Local Slowave dashboard.

Dependency-free MVP: stdlib HTTP server + SQLite read APIs + a small embedded UI.
The dashboard is local-only by default and read-only unless future actions are
explicitly enabled.
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
        server_version = "slowave-dashboard/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # keep terminal quiet
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib API
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
                else:
                    self._send_json({"error": "not found", "path": path}, status=HTTPStatus.NOT_FOUND)
            except Exception as e:
                self._send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self) -> None:  # noqa: N802 - stdlib API
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8") if length else "{}"
                payload = json.loads(body or "{}")
                if path == "/api/recall":
                    self._send_json(_recall_payload(db_path, payload))
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
    return {
        "id": f"sch_{int(row['id'])}",
        "schema_id": int(row["id"]),
        "label": content if len(content) <= 80 else content[:77] + "...",
        "content": content,
        "project": row["project"],
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
    }


def _status_payload(db_path: str) -> dict[str, Any]:
    exists = os.path.exists(db_path)
    db_file = Path(db_path)
    conn = _connect(db_path) if exists else None
    try:
        stats = {}
        schema_health = {}
        projects: list[dict[str, Any]] = []
        recent_sessions: list[dict[str, Any]] = []
        if conn is not None:
            stats = {
                "sessions": _table_count(conn, "sessions"),
                "raw_events": _table_count(conn, "raw_events"),
                "episodes": _table_count(conn, "episodic_memories"),
                "episode_texts": _table_count(conn, "episode_text"),
                "prototypes": _table_count(conn, "semantic_prototypes"),
                "schemas": _table_count(conn, "schemas"),
                "edges": _table_count(conn, "prototype_edges"),
                "schema_relations": _table_count(conn, "schema_relations"),
                "schema_evidence": _table_count(conn, "schema_evidence"),
            }
            schema_health = _schema_health(conn)
            projects = [
                {"project": r["project"], "sessions": int(r["n"])}
                for r in conn.execute(
                    "SELECT COALESCE(project, '(none)') AS project, COUNT(*) AS n "
                    "FROM sessions GROUP BY COALESCE(project, '(none)') ORDER BY n DESC"
                ).fetchall()
            ]
            recent_sessions = [dict(r) for r in conn.execute(
                """
                SELECT s.id, s.agent, s.project, s.started_ts, s.ended_ts,
                       COUNT(re.id) AS events,
                       COUNT(DISTINCT et.episode_id) AS episodes
                FROM sessions s
                LEFT JOIN raw_events re ON re.session_id = s.id
                LEFT JOIN episode_text et ON et.session_id = s.id
                GROUP BY s.id
                ORDER BY s.started_ts DESC
                LIMIT 8
                """
            ).fetchall()]
        processes = _slowave_processes()
        return {
            "db_path": db_path,
            "db_exists": exists,
            "db_size_bytes": db_file.stat().st_size if exists else 0,
            "wal_size_bytes": Path(db_path + "-wal").stat().st_size if Path(db_path + "-wal").exists() else 0,
            "shm_size_bytes": Path(db_path + "-shm").stat().st_size if Path(db_path + "-shm").exists() else 0,
            "stats": stats,
            "schema_health": schema_health,
            "projects": projects,
            "recent_sessions": recent_sessions,
            "processes": processes,
            "warnings": _warnings(schema_health, processes),
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
            SELECT project, lower(trim(content_text)) AS norm, COUNT(*) AS n
            FROM schemas
            WHERE status IN ('active', 'needs_review')
            GROUP BY project, lower(trim(content_text))
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
    project = (qs.get("project") or [""])[0]
    q = (qs.get("q") or [""])[0].strip().lower()
    args: list[Any] = []
    sql = "SELECT * FROM schemas WHERE 1=1"
    if status in VALID_SCHEMA_STATUSES:
        sql += " AND status = ?"
        args.append(status)
    if project:
        sql += " AND project = ?"
        args.append(project)
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
    project = (qs.get("project") or [""])[0]
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
    if project:
        sql += " AND project = ?"
        args.append(project)
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


def _recall_payload(db_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    top_k = max(1, min(20, int(payload.get("top_k") or 5)))
    evidence = bool(payload.get("evidence", True))
    from dataclasses import asdict as _asdict

    from slowave.core.config import SlowaveConfig
    from slowave.core.engine import SlowaveEngine
    from slowave.llm.base import LLMBackendConfig
    from slowave.symbolic.encoder import EncoderConfig

    eng = SlowaveEngine(
        SlowaveConfig(
            db_path=db_path,
            dim=384,
            encoder=EncoderConfig(),
            llm=LLMBackendConfig(),
            disable_llm=True,
            schema_mode="latent",
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
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Slowave Dashboard</title>
<style>
:root{--bg:#0b1020;--panel:#121a2d;--panel2:#17213a;--text:#e8eefc;--muted:#9aa8c7;--line:#2a375a;--green:#47d16c;--amber:#f2bd4b;--red:#ff647c;--blue:#60a5fa;--purple:#b084f5;--gray:#778199;}
*{box-sizing:border-box} body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text)}
header{padding:16px 22px;border-bottom:1px solid var(--line);display:flex;gap:14px;align-items:center;justify-content:space-between;background:#0d1426;position:sticky;top:0;z-index:10}
h1{font-size:20px;margin:0}.sub{color:var(--muted);font-size:12px}.tabs{display:flex;gap:8px;flex-wrap:wrap}.tab{border:1px solid var(--line);background:var(--panel);color:var(--text);padding:8px 10px;border-radius:8px;cursor:pointer}.tab.active{background:var(--blue);border-color:var(--blue);color:#061223}
main{padding:18px;max-width:1500px;margin:0 auto}.section{display:none}.section.active{display:block}.grid{display:grid;gap:14px}.cards{grid-template-columns:repeat(auto-fit,minmax(155px,1fr))}.card,.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}.card .k{color:var(--muted);font-size:12px}.card .v{font-size:28px;font-weight:700;margin-top:4px}.warn{background:#2a1e12;border-color:#62410e;color:#ffd991}.ok{background:#102417;border-color:#1d6533;color:#b6f4c4}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}tr:hover{background:#17213a}.pill{display:inline-block;border-radius:999px;padding:2px 7px;font-size:11px;border:1px solid var(--line);margin:1px}.activeP{background:#12341f;color:#bff7c9}.needs_reviewP{background:#3a2b10;color:#ffe1a3}.contradictedP{background:#3c1420;color:#ffb4c1}.supersededP{background:#27223a;color:#d6c6ff}.archivedP{background:#202638;color:#bec7dc}.muted{color:var(--muted)}
.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}.controls input,.controls select,.controls button,textarea{background:#0d1426;border:1px solid var(--line);color:var(--text);border-radius:8px;padding:8px}.controls button,button.primary{cursor:pointer;background:var(--blue);color:#061223;border:0;font-weight:700}button.secondary{background:var(--panel2);color:var(--text);border:1px solid var(--line)}
.graphWrap{display:grid;grid-template-columns:minmax(650px,1fr) 380px;gap:14px}.graphBox{height:720px;background:#071020;border:1px solid var(--line);border-radius:12px;position:relative;overflow:hidden}svg{width:100%;height:100%}.side{height:720px;overflow:auto}.node{cursor:pointer;stroke:#e8eefc;stroke-width:1.2}.node.selected{stroke:#fff;stroke-width:3}.edge{stroke-opacity:.78}.edgeLabel{font-size:10px;fill:#b8c4e3;pointer-events:none}.nodeLabel{font-size:10px;fill:#e8eefc;pointer-events:none;text-shadow:0 1px 2px #000}.detail pre{white-space:pre-wrap;background:#0d1426;border:1px solid var(--line);border-radius:8px;padding:10px;color:#cbd7f5;overflow:auto}.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:1050px){.graphWrap,.two{grid-template-columns:1fr}.side{height:auto}.graphBox{height:560px}}
</style>
</head>
<body>
<header><div><h1>Slowave Dashboard</h1><div class="sub" id="dbPath">loading...</div></div><div class="tabs"><button class="tab active" data-tab="overview">Overview</button><button class="tab" data-tab="processes">Processes</button><button class="tab" data-tab="schemas">Schemas</button><button class="tab" data-tab="graph">Schema Graph</button><button class="tab" data-tab="recall">Recall</button><button class="tab" data-tab="db">DB Health</button></div></header>
<main>
<section id="overview" class="section active"><div id="warnings"></div><div class="grid cards" id="cards"></div><div class="two" style="margin-top:14px"><div class="panel"><h3>Recent sessions</h3><div id="recentSessions"></div></div><div class="panel"><h3>Projects</h3><div id="projects"></div></div></div></section>
<section id="processes" class="section"><div class="panel"><h3>Slowave processes</h3><div id="processTable"></div></div></section>
<section id="schemas" class="section"><div class="panel"><div class="controls"><select id="schemaStatus"><option value="">all statuses</option><option>active</option><option>needs_review</option><option>contradicted</option><option>superseded</option><option>archived</option></select><input id="schemaQ" placeholder="search schema text"/><input id="schemaLimit" type="number" value="100" min="1" max="500"/><button onclick="loadSchemas()">Load</button></div><div id="schemaTable"></div></div></section>
<section id="graph" class="section"><div class="controls"><input id="graphProject" placeholder="project filter optional"/><input id="graphLimit" type="number" value="120" min="1" max="300"/><label><input type="checkbox" class="gstat" value="active" checked/> active</label><label><input type="checkbox" class="gstat" value="needs_review" checked/> review</label><label><input type="checkbox" class="gstat" value="contradicted" checked/> contradicted</label><label><input type="checkbox" class="gstat" value="superseded" checked/> superseded</label><label><input type="checkbox" class="gstat" value="archived"/> archived</label><button onclick="loadGraph()">Refresh graph</button></div><div class="panel" style="margin-bottom:14px"><div class="controls" style="margin-bottom:0"><b>Minimum salience</b><span id="graphMinSalienceLabel" class="pill">0.00</span><input id="graphMinSalience" type="range" value="0" min="0" max="25" step="0.1" oninput="syncSalienceSlider()" style="min-width:320px;flex:1"/><span class="muted">max observed: <span id="graphObservedMaxSalienceLabel">25.00</span></span><button class="secondary" onclick="resetSalienceSlider()">Reset</button></div></div><div class="graphWrap"><div class="graphBox"><svg id="schemaGraph"></svg></div><div class="panel side detail"><h3>Schema detail</h3><div id="graphDetail" class="muted">Click a node to inspect schema, evidence and relations.</div></div></div></section>
<section id="recall" class="section"><div class="panel"><h3>Recall playground</h3><textarea id="recallQuery" rows="4" style="width:100%" placeholder="Ask what Slowave should remember..."></textarea><div class="controls"><input id="recallTopK" type="number" value="5" min="1" max="20"/><label><input id="recallEvidence" type="checkbox" checked/> include evidence</label><button onclick="runRecall()">Run recall</button></div><div id="recallResults"></div></div></section>
<section id="db" class="section"><div class="panel"><h3>Database health</h3><button class="secondary" onclick="loadDbHealth()">Refresh</button><div id="dbHealth"></div></div></section>
</main>
<script>
const REFRESH_MS=__REFRESH_MS__; const ALLOW_ACTIONS=__ALLOW_ACTIONS__;
const statusColor={active:'#47d16c',needs_review:'#f2bd4b',contradicted:'#ff647c',superseded:'#b084f5',archived:'#778199'};
const relColor={reinforces:'#47d16c',refines:'#60a5fa',contradicts:'#ff647c',supersedes:'#f59e0b',related_to:'#778199',part_of:'#2dd4bf'};
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function fmtBytes(n){n=Number(n||0); if(n<1024)return n+' B'; if(n<1048576)return (n/1024).toFixed(1)+' KB'; return (n/1048576).toFixed(1)+' MB';}
function fmtTs(ts){if(!ts)return '—'; return new Date(Number(ts)*1000).toLocaleString();}
function age(s){s=Number(s||0); if(s<60)return s+'s'; if(s<3600)return Math.floor(s/60)+'m'; if(s<86400)return Math.floor(s/3600)+'h'; return Math.floor(s/86400)+'d';}
async function getJSON(url){const r=await fetch(url); return await r.json();}
async function postJSON(url,obj){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)}); return await r.json();}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.tab).classList.add('active'); if(b.dataset.tab==='processes')loadProcesses(); if(b.dataset.tab==='schemas')loadSchemas(); if(b.dataset.tab==='graph')loadGraph(); if(b.dataset.tab==='db')loadDbHealth();});
async function loadStatus(){const d=await getJSON('/api/status'); window.lastStatus=d; initSalienceSliders(d); document.getElementById('dbPath').textContent=d.db_path; const s=d.stats||{}, h=d.schema_health||{}; const cards=[['DB size',fmtBytes(d.db_size_bytes)],['WAL',fmtBytes(d.wal_size_bytes)],['Sessions',s.sessions],['Raw events',s.raw_events],['Episodes',s.episodes],['Prototypes',s.prototypes],['Schemas',s.schemas],['Active',h.active_schemas],['Needs review',h.needs_review_schemas],['Relations',s.schema_relations],['MCP processes',(d.processes||[]).filter(p=>p.kind==='mcp').length],['Edges',s.edges]]; document.getElementById('cards').innerHTML=cards.map(([k,v])=>`<div class="card"><div class="k">${esc(k)}</div><div class="v">${esc(v??0)}</div></div>`).join(''); document.getElementById('warnings').innerHTML=(d.warnings||[]).length?`<div class="panel warn"><b>Warnings</b><ul>${d.warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul></div>`:`<div class="panel ok">No dashboard health warnings.</div>`; document.getElementById('recentSessions').innerHTML=table(['session','project','agent','started','ended','events','episodes'],(d.recent_sessions||[]).map(r=>[r.id,r.project||'',r.agent,fmtTs(r.started_ts),r.ended_ts?fmtTs(r.ended_ts):'open',r.events,r.episodes])); document.getElementById('projects').innerHTML=table(['project','sessions'],(d.projects||[]).map(r=>[r.project,r.sessions]));}
async function loadProcesses(){const d=await getJSON('/api/processes'); document.getElementById('processTable').innerHTML=table(['pid','kind','ppid','stat','age','rss','orphan','command','parent'],(d.processes||[]).map(p=>[p.pid,p.kind,p.ppid,p.stat,age(p.age_seconds),fmtBytes(p.rss_kb*1024),p.orphaned?'yes':'no',p.command,p.parent_command||'']));}
function pill(status){return `<span class="pill ${esc(status)}P">${esc(status)}</span>`}
async function loadSchemas(){const st=document.getElementById('schemaStatus').value; const q=encodeURIComponent(document.getElementById('schemaQ').value); const lim=document.getElementById('schemaLimit').value; const d=await getJSON(`/api/schemas?limit=${lim}&status=${encodeURIComponent(st)}&q=${q}`); document.getElementById('schemaTable').innerHTML=table(['id','status','salience','class','project','supports','content'],(d.schemas||[]).map(s=>[`sch_${s.schema_id}`,pill(s.status),s.salience.toFixed(3),s.schema_class||'',s.project||'',s.support_count,esc(s.content)]),true);}
function table(head, rows, raw=false){if(!rows.length)return '<div class="muted">No rows.</div>'; return `<table><thead><tr>${head.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${raw?c:esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`}
function initSalienceSliders(status){initSalienceSlider(status);} 
function initSalienceSlider(status){if(window.salienceSliderInitialized)return; const maxSal=Number(status?.schema_health?.active_salience?.max||25); const upper=Math.max(1, Math.ceil(maxSal)); const minEl=document.getElementById('graphMinSalience'); if(!minEl)return; minEl.max=String(upper); document.getElementById('graphObservedMaxSalienceLabel').textContent=maxSal.toFixed(2); window.salienceSliderInitialized=true; syncSalienceSlider(false);} 
function syncSalienceSlider(autoLoad=true){const minEl=document.getElementById('graphMinSalience'); const min=Number(minEl.value); document.getElementById('graphMinSalienceLabel').textContent=min.toFixed(2); clearTimeout(window.salienceLoadTimer); if(autoLoad) window.salienceLoadTimer=setTimeout(loadGraph,250);} 
function resetSalienceSlider(){const minEl=document.getElementById('graphMinSalience'); minEl.value='0'; syncSalienceSlider();}
async function loadGraph(){const sts=[...document.querySelectorAll('.gstat:checked')].map(x=>x.value).join(','); const lim=document.getElementById('graphLimit').value; const proj=encodeURIComponent(document.getElementById('graphProject').value); const minSal=encodeURIComponent(document.getElementById('graphMinSalience').value); const d=await getJSON(`/api/graph/schemas?limit=${lim}&statuses=${sts}&project=${proj}&min_salience=${minSal}`); drawGraph(d);}
function drawGraph(g){const svg=document.getElementById('schemaGraph'); svg.innerHTML='<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#9aa8c7"/></marker></defs>'; const w=svg.clientWidth||900,h=svg.clientHeight||700,cx=w/2,cy=h/2; const nodes=g.nodes||[], edges=g.edges||[]; const byId=Object.fromEntries(nodes.map((n,i)=>[n.id,n])); nodes.forEach((n,i)=>{const a=2*Math.PI*i/Math.max(1,nodes.length); const radius=Math.min(w,h)*0.38*(0.55+0.45*((i%7)/7)); n.x=cx+Math.cos(a)*radius; n.y=cy+Math.sin(a)*radius;}); for(let iter=0;iter<80;iter++){nodes.forEach(n=>{n.vx=(n.vx||0)*0.75;n.vy=(n.vy||0)*0.75}); for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){let a=nodes[i],b=nodes[j],dx=a.x-b.x,dy=a.y-b.y,d=Math.sqrt(dx*dx+dy*dy)+.01,force=850/(d*d); a.vx+=dx/d*force;b.vx-=dx/d*force;a.vy+=dy/d*force;b.vy-=dy/d*force;} edges.forEach(e=>{let a=byId[e.source],b=byId[e.target]; if(!a||!b)return; let dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)+.01,force=(d-170)*.002; a.vx+=dx/d*force;b.vx-=dx/d*force;a.vy+=dy/d*force;b.vy-=dy/d*force;}); nodes.forEach(n=>{n.x=Math.max(30,Math.min(w-30,n.x+n.vx));n.y=Math.max(30,Math.min(h-30,n.y+n.vy));});}
 edges.forEach(e=>{let a=byId[e.source],b=byId[e.target]; if(!a||!b)return; const line=document.createElementNS('http://www.w3.org/2000/svg','line'); line.setAttribute('x1',a.x);line.setAttribute('y1',a.y);line.setAttribute('x2',b.x);line.setAttribute('y2',b.y);line.setAttribute('class','edge');line.setAttribute('stroke',relColor[e.relation]||'#778199');line.setAttribute('stroke-width',String(1+2*(e.confidence||.5)));line.setAttribute('marker-end','url(#arrow)'); svg.appendChild(line); const t=document.createElementNS('http://www.w3.org/2000/svg','text'); t.setAttribute('x',(a.x+b.x)/2);t.setAttribute('y',(a.y+b.y)/2);t.setAttribute('class','edgeLabel');t.textContent=e.relation; svg.appendChild(t);});
 nodes.forEach(n=>{const r=7+Math.min(22,Math.sqrt(Math.max(0,n.salience))*4); const c=document.createElementNS('http://www.w3.org/2000/svg','circle'); c.setAttribute('cx',n.x);c.setAttribute('cy',n.y);c.setAttribute('r',r);c.setAttribute('fill',statusColor[n.status]||'#778199');c.setAttribute('class','node'); c.onclick=()=>selectNode(n,c); svg.appendChild(c); const lab=document.createElementNS('http://www.w3.org/2000/svg','text'); lab.setAttribute('x',n.x+r+3);lab.setAttribute('y',n.y+3);lab.setAttribute('class','nodeLabel');lab.textContent=`sch_${n.schema_id}`; svg.appendChild(lab);}); if(!nodes.length)document.getElementById('graphDetail').innerHTML='<div class="muted">No graph nodes for selected filters.</div>';}
async function selectNode(n,el){document.querySelectorAll('.node').forEach(x=>x.classList.remove('selected')); el.classList.add('selected'); const d=await getJSON(`/api/schemas/${n.schema_id}`); const s=d.schema||n; document.getElementById('graphDetail').innerHTML=`<h3>sch_${s.schema_id}</h3><p>${pill(s.status)} <span class="pill">salience ${Number(s.salience).toFixed(3)}</span> <span class="pill">${esc(s.schema_class||'schema')}</span></p><p>${esc(s.content)}</p><h4>Facets</h4><pre>${esc(JSON.stringify(s.facets,null,2))}</pre><h4>Tags</h4><p>${(s.tags||[]).map(t=>`<span class="pill">${esc(t)}</span>`).join('')||'<span class="muted">none</span>'}</p><h4>Evidence</h4>${table(['episode','event','weight','quote'],(d.evidence||[]).map(e=>[e.episode_id?`epi_${e.episode_id}`:'',e.raw_event_id?`evt_${e.raw_event_id}`:'',e.weight,e.quote||'']))}<h4>Outgoing</h4>${table(['to','relation','confidence','reason'],(d.outgoing||[]).map(e=>[`sch_${e.dst_schema_id}`,e.relation,e.confidence,e.reason||'']))}<h4>Incoming</h4>${table(['from','relation','confidence','reason'],(d.incoming||[]).map(e=>[`sch_${e.src_schema_id}`,e.relation,e.confidence,e.reason||'']))}`;}
async function runRecall(){const query=document.getElementById('recallQuery').value; const top_k=document.getElementById('recallTopK').value; const evidence=document.getElementById('recallEvidence').checked; document.getElementById('recallResults').innerHTML='<div class="muted">Running recall; encoder may take a moment...</div>'; const d=await postJSON('/api/recall',{query,top_k,evidence}); if(d.error){document.getElementById('recallResults').innerHTML=`<div class="panel warn">${esc(d.error)}</div>`;return;} document.getElementById('recallResults').innerHTML=`<h4>Schemas</h4>${table(['id','status','salience','content'],(d.schemas||[]).map(s=>[`sch_${s.id}`,s.status,Number(s.salience).toFixed(3),s.content_text]))}<h4>Episodes</h4>${table(['id','salience','content'],(d.episodes||[]).map(e=>[`epi_${e.id}`,Number(e.salience).toFixed(3),e.content_text]))}<h4>Raw events</h4>${table(['id','type','content'],(d.raw_events||[]).map(e=>[`evt_${e.id}`,e.type,e.content]))}`;}
async function loadDbHealth(){const d=await getJSON('/api/db/health'); document.getElementById('dbHealth').innerHTML=`<h4>Pragmas</h4><pre>${esc(JSON.stringify(d.pragmas,null,2))}</pre><h4>Integrity</h4><pre>${esc(JSON.stringify(d.integrity_check,null,2))}</pre><h4>Foreign keys</h4><pre>${esc(JSON.stringify(d.foreign_key_check,null,2))}</pre><h4>Tables</h4>${table(['name','type','count'],(d.tables||[]).map(t=>[t.name,t.type,t.count??'']))}`;}
loadStatus(); setInterval(loadStatus, REFRESH_MS);
</script>
</body></html>'''
