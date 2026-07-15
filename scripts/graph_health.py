#!/usr/bin/env python3
"""Graph health measurement script for Slowave.

Read-only SQLite queries against ~/.slowave/slowave.db.
Usage: python scripts/graph_health.py [--db PATH]

Reports: S1-S5 (schema), partial P/E/C metrics, supplementary observations.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

DEFAULT_DB = os.path.expanduser("~/.slowave/slowave.db")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def s1_status_distribution(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM schemas GROUP BY status ORDER BY cnt DESC"
    ).fetchall()
    return {r["status"]: r["cnt"] for r in rows}


def s2_relation_distribution(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT relation, COUNT(*) as cnt FROM schema_relations GROUP BY relation ORDER BY cnt DESC"
    ).fetchall()
    return {r["relation"]: r["cnt"] for r in rows}


def s3_degree_stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("""SELECT s.id, COUNT(sr2.relation) as degree
           FROM schemas s
           LEFT JOIN (
               SELECT src_schema_id as sid, relation FROM schema_relations
               UNION ALL
               SELECT dst_schema_id as sid, relation FROM schema_relations
           ) sr2 ON s.id = sr2.sid
           GROUP BY s.id""").fetchall()
    degrees = [r["degree"] for r in rows]
    isolates = sum(1 for d in degrees if d == 0)
    top = sorted(degrees, reverse=True)[:10]
    return {
        "n_schemas": len(degrees),
        "isolates": isolates,
        "isolate_pct": round(100.0 * isolates / len(degrees), 1) if degrees else 0,
        "mean_degree": round(sum(degrees) / len(degrees), 1) if degrees else 0,
        "median_degree": sorted(degrees)[len(degrees) // 2] if degrees else 0,
        "max_degree": max(degrees) if degrees else 0,
        "top10": top,
    }


def s5_salience_stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT salience FROM schemas").fetchall()
    vals = sorted(r["salience"] for r in rows)
    n = len(vals)
    ceiling_breaches = sum(1 for v in vals if v > 20.0)
    return {
        "n": n,
        "min": round(vals[0], 4),
        "max": round(vals[-1], 4),
        "mean": round(sum(vals) / n, 4),
        "median": round(vals[n // 2], 4),
        "q1": round(vals[n // 4], 4),
        "q3": round(vals[3 * n // 4], 4),
        "ceiling_breaches": ceiling_breaches,
    }


def episode_stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) as cnt, AVG(salience) as avg_s, MIN(salience) as min_s, "
        "MAX(salience) as max_s, AVG(recalled_count) as avg_rc, MAX(recalled_count) as max_rc "
        "FROM episodic_memories"
    ).fetchone()
    return {
        "count": row["cnt"],
        "avg_salience": round(row["avg_s"] or 0, 4),
        "min_salience": round(row["min_s"] or 0, 4),
        "max_salience": round(row["max_s"] or 0, 4),
        "avg_recalled": round(row["avg_rc"] or 0, 2),
        "max_recalled": row["max_rc"] or 0,
    }


def session_stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) as total, "
        "COUNT(CASE WHEN ended_ts IS NULL THEN 1 END) as open_sessions "
        "FROM sessions"
    ).fetchone()
    return {"total": row["total"], "open": row["open"]}


def worker_run_stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) as total, AVG(duration_ms) as avg_d, MAX(duration_ms) as max_d, "
        "SUM(prototypes_processed) as proto, SUM(episodes_processed) as ep, "
        "SUM(schemas_created) as sc, SUM(schemas_decayed) as sd "
        "FROM worker_runs"
    ).fetchone()
    return {
        "total_runs": row["total"],
        "avg_duration_ms": round(row["avg_d"] or 0, 0),
        "max_duration_ms": row["max_d"] or 0,
        "prototypes_processed": row["proto"] or 0,
        "episodes_processed": row["ep"] or 0,
        "schemas_created": row["sc"] or 0,
        "schemas_decayed": row["sd"] or 0,
    }


def supplementary(conn: sqlite3.Connection) -> dict:
    labile = conn.execute("SELECT COUNT(*) FROM schemas WHERE is_labile=1").fetchone()[0]
    gen_stages = dict(
        conn.execute(
            "SELECT generalization_stage, COUNT(*) FROM schemas "
            "GROUP BY generalization_stage ORDER BY generalization_stage"
        ).fetchall()
    )
    proto_scales = dict(
        conn.execute("SELECT scale, COUNT(*) FROM semantic_prototypes GROUP BY scale").fetchall()
    )
    top_scopes = conn.execute(
        "SELECT scope_id, COUNT(*) as cnt FROM schemas "
        "WHERE scope_id IS NOT NULL GROUP BY scope_id ORDER BY cnt DESC LIMIT 5"
    ).fetchall()
    return {
        "labile_count": labile,
        "generalization_stages": {str(k): v for k, v in gen_stages.items()},
        "prototype_scales": proto_scales,
        "top_scopes": [(r["scope_id"], r["cnt"]) for r in top_scopes],
    }


def main():
    db_path = DEFAULT_DB
    if "--db" in sys.argv:
        idx = sys.argv.index("--db")
        db_path = sys.argv[idx + 1]

    if not Path(db_path).exists():
        print(f"ERROR: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = _connect(db_path)
    start = time.time()

    print("=" * 60)
    print("Slowave Graph Health — Measurement Report")
    print(f"DB: {db_path}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Schema metrics
    status = s1_status_distribution(conn)
    total_schemas = sum(status.values())
    superseded_pct = round(100.0 * status.get("superseded", 0) / total_schemas, 1)

    print(f"\n─── Schema Graph (n={total_schemas}) ───")
    print(f"  S1 Status: {json.dumps(status)}")
    print(f"     → Superseded ratio: {superseded_pct}%")

    relations = s2_relation_distribution(conn)
    total_rels = sum(relations.values())
    print(f"  S2 Relations ({total_rels} edges): {json.dumps(relations)}")

    degree = s3_degree_stats(conn)
    print(
        f"  S3 Degree: {degree['isolates']} isolates ({degree['isolate_pct']}%), "
        f"mean={degree['mean_degree']}, max={degree['max_degree']}"
    )

    salience = s5_salience_stats(conn)
    print(
        f"  S5 Salience: min={salience['min']}, max={salience['max']}, "
        f"mean={salience['mean']}, median={salience['median']}"
    )
    print(f"     → Ceiling breaches (>20): {salience['ceiling_breaches']}")

    # Prototype
    proto = proto_edge_stats(conn)
    n_proto = conn.execute("SELECT COUNT(*) FROM semantic_prototypes").fetchone()[0]
    proto_d = round(100.0 * proto["count"] / max(1, n_proto * (n_proto - 1)), 2)
    print(f"\n─── Prototype Graph (n={n_proto}) ───")
    print(f"  Edges: {proto['count']}, density={proto_d}%")
    print(
        f"  Weights: avg={proto['avg_weight']}, min={proto['min_weight']}, "
        f"max={proto['max_weight']}"
    )

    # Episode
    ep = episode_stats(conn)
    ratio = round(ep["count"] / max(1, total_schemas), 2)
    print(f"\n─── Episode Graph (n={ep['count']}) ───")
    print(
        f"  E1 Salience: avg={ep['avg_salience']}, "
        f"range=[{ep['min_salience']}, {ep['max_salience']}]"
    )
    print(f"  E1 Recalled: avg={ep['avg_recalled']}, max={ep['max_recalled']}")
    print(f"  E2 Episodes-per-schema: {ratio}")

    # Cross-cutting
    sess = session_stats(conn)
    wr = worker_run_stats(conn)
    schema_d = round(100.0 * total_rels / max(1, total_schemas * (total_schemas - 1)), 3)
    print(f"\n─── Cross-Cutting ───")
    print(f"  C1 Schema graph density: {schema_d}%")
    print(
        f"  C2 Worker runs: {wr['total_runs']}, "
        f"avg={wr['avg_duration_ms']}ms, max={wr['max_duration_ms']}ms"
    )
    print(
        f"     → schemas_created={wr['schemas_created']}, "
        f"schemas_decayed={wr['schemas_decayed']}"
    )
    print(f"  Sessions: {sess['total']} total, {sess['open']} open")

    # Supplementary
    sup = supplementary(conn)
    print(f"\n─── Supplementary ───")
    print(f"  Labile schemas: {sup['labile_count']}")
    print(f"  Generalization stages: {json.dumps(sup['generalization_stages'])}")
    print(f"  Prototype scales: {json.dumps(sup['prototype_scales'])}")
    print(f"  Top scopes: {sup['top_scopes']}")

    elapsed = round(time.time() - start, 3)
    print(f"\n{'=' * 60}")
    print(f"Completed in {elapsed}s")
    print(f"{'=' * 60}")

    conn.close()


if __name__ == "__main__":
    main()


def proto_edge_stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) as cnt, AVG(weight) as avg_w, MIN(weight) as min_w, MAX(weight) as max_w FROM prototype_edges"
    ).fetchone()
    return {
        "count": row["cnt"],
        "avg_weight": round(row["avg_w"], 4),
        "min_weight": round(row["min_w"], 4),
        "max_weight": round(row["max_w"], 4),
    }
