"""End-to-end acceptance test: full cognitive cycle via CLI blackbox.

Tests the Slowave core-mechanism validation, including the 2026-07-10
"labile" lifecycle (Phase 4's recovery-via-feedback, Phase 4b's scope_id-
independent noise tracking, Phase 5's reconsolidation assertion), using only:
  - subprocess calls to the `slowave` CLI
  - read-only sqlite3 queries for assertions

No Python API imports, no direct DB writes.

Run (progress output requires -s):
    pytest tests/acceptance/test_e2e.py -v -s
    (requires sentence-transformers / FAISS; ~3-5 minutes)
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from typing import Any

import pytest


def _detail(msg: str) -> None:
    """Detail line — only appears when pytest is run with -s."""
    print(f"      {msg}", flush=True)


# ── CLI / DB helpers ──────────────────────────────────────────────────────────

# Use `python -m slowave.cli.main` so the test works regardless of which Python
# binary runs pytest (venv, system, pyenv, etc.) — no hardcoded binary path.
_CMD_PREFIX = [sys.executable, "-m", "slowave.cli.main"]


def _cli(db_path: str, *args: str, check: bool = True) -> dict[str, Any]:
    """Run a slowave CLI command with --json and return parsed output."""
    result = subprocess.run(
        [*_CMD_PREFIX, "--json", *args],
        env={**os.environ, "SLOWAVE_DB": db_path},
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"CLI returned {result.returncode}: {result.stderr.strip()}\n"
            f"Command: slowave --json {' '.join(args)}"
        )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def _query(db_path: str, sql: str, params: tuple = ()) -> list[dict]:
    """Read-only sqlite3 query; returns list of row dicts."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _schema_id_for(db_path: str, snippet: str) -> int | None:
    """Return the integer schema id whose content_text contains *snippet*."""
    rows = _query(db_path, "SELECT id FROM schemas WHERE content_text LIKE ?", (f"%{snippet}%",))
    return rows[0]["id"] if rows else None


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="class")
def db(tmp_path_factory):
    """Isolated filesystem DB shared across all methods in the class.

    Must be a real file (not :memory:) because every CLI subprocess call
    opens its own SQLite connection — an in-memory DB would be a separate
    empty database per call.

    Explicitly deleted on teardown so WAL/SHM files don't accumulate.
    """
    import pathlib
    import tempfile

    # Use a dedicated temp dir so cleanup is a single rmtree.
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="slowave_e2e_"))
    path = str(tmp / "slowave.db")
    yield path
    # Teardown: remove the DB and any SQLite WAL/SHM sidecar files.
    for suffix in ("", "-wal", "-shm"):
        f = pathlib.Path(path + suffix)
        if f.exists():
            f.unlink()
    try:
        tmp.rmdir()
    except OSError:
        pass  # non-empty if something wrote extra files — leave the dir


@pytest.fixture(scope="class")
def cli(db):
    """CLI helper bound to the class-scoped DB."""

    def _run(*args, check=True):
        return _cli(db, *args, check=check)

    return _run


@pytest.fixture(scope="class")
def qdb(db):
    """Query helper bound to the class-scoped DB."""

    def _q(sql, params=()):
        return _query(db, sql, params)

    return _q


# ── dataset ───────────────────────────────────────────────────────────────────
#
# Minimal representative dataset, verbatim text from the v2 validation prompt.
#
# T*  – ranked targets: each must rank #1 for its paired probe query
# D*  – distractors: semantically adjacent noise
# L1  – promotion-ladder seed (API retry backoff)
# S1  – demotion target (team retrospective; surfaces on noise queries)

DATASET_SLOWAVE = {
    "T1": (
        "fact",
        "SessionReaper runs as a daemon thread in the HTTP server, scanning every 60s for sessions idle beyond SLOWAVE_SESSION_IDLE_TIMEOUT (default 3600s) and closing them with outcome=unknown.",
    ),
    "T5": (
        "warning",
        "FAISS index rebuild loads all embeddings into RAM; refresh_indices is O(n) and should not be called per-event, only after consolidation batches.",
    ),
    "T8": (
        "fact",
        "The HTTP MCP daemon binds SLOWAVE_MCP_HOST:SLOWAVE_MCP_HTTP_PORT (default 127.0.0.1:8766) and enforces single-instance via a PID file at SLOWAVE_DAEMON_PID.",
    ),
    "D1": (
        "preference",
        "Matteo prefers black with line-length 100 and isort profile black for all Python formatting in slowave.",
    ),
    "D2": (
        "constraint",
        "The LLM is output-only in slowave; consolidation must never route through an LLM call — memory operations are pure geometry over embeddings.",
    ),
    "D3": (
        "fact",
        "TextEncoder wraps sentence-transformers all-MiniLM-L6-v2 with dim=384 and is lazy-loaded to keep import time low.",
    ),
    "L1": (
        "lesson",
        "API retry loops must use exponential backoff with jitter, starting at 2 seconds and capping at 60 seconds, to avoid thundering-herd retry storms.",
    ),
    "S1": (
        "fact",
        "The team retrospective happens every second Friday and alternates between an online call and the office meeting room.",
    ),
}

DATASET_ALPHA = {
    "A1": (
        "fact",
        "Alpha is a FastAPI monolith with two domains: ingestion and agent; the domains must not import from each other.",
    ),
    "A2": (
        "constraint",
        "Alpha tenant isolation: SQL always uses a :company_id placeholder bound server-side, never an inlined literal.",
    ),
}

SCOPES = [
    "project:slowave",
    "project:alpha",
    "project:beta",
    "project:gamma",
    "project:delta",
    "project:epsilon",
    "project:zeta",
    "project:eta",
    "project:theta",
    "domain:engineering",
]

L1_TEXT = DATASET_SLOWAVE["L1"][1]


# ── test class ────────────────────────────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.requires_faiss
class TestE2E:
    """End-to-end acceptance test.

    Methods run in definition order; each builds on DB state from the previous.
    Run with -s to see progress output.
    """

    # ── Phase 0 ───────────────────────────────────────────────────────────────

    def test_phase0_register_scopes(self, cli, qdb):
        """Register all 10 scopes to freeze the generalization denominator."""
        time.time()

        for scope in SCOPES:
            r = cli("activate", "--query", "register scope", "--scope", scope)
            cli("commit", r["session_id"], "--outcome", "unknown")
            _detail(scope)

        rows = qdb("SELECT COUNT(*) as n, COUNT(DISTINCT scope_kind) as k FROM scope_registry")
        n, k = rows[0]["n"], rows[0]["k"]

        assert n == 10, f"expected 10 scopes, got {n}"
        assert k == 2, f"expected 2 scope kinds (project+domain), got {k}"

    # ── Phase 1 ───────────────────────────────────────────────────────────────

    def test_phase1_inject_dataset(self, cli, db):
        """Inject the validation dataset into project:slowave and project:alpha."""
        time.time()

        r = cli("activate", "--query", "inject dataset", "--scope", "project:slowave")
        sid = r["session_id"]
        for key, (mem_type, content) in DATASET_SLOWAVE.items():
            cli(
                "remember",
                content,
                "--type",
                mem_type,
                "--scope",
                "project:slowave",
                "--session",
                sid,
            )
            _detail(f"project:slowave  {key}  ({mem_type})")
        cli("commit", sid, "--outcome", "success")

        r = cli("activate", "--query", "inject dataset", "--scope", "project:alpha")
        sid = r["session_id"]
        for key, (mem_type, content) in DATASET_ALPHA.items():
            cli(
                "remember",
                content,
                "--type",
                mem_type,
                "--scope",
                "project:alpha",
                "--session",
                sid,
            )
            _detail(f"project:alpha    {key}  ({mem_type})")
        cli("commit", sid, "--outcome", "success")

        rows = _query(db, "SELECT COUNT(*) as n FROM schemas WHERE status='active'")
        assert rows[0]["n"] >= 10

    # ── Phase 2 ───────────────────────────────────────────────────────────────

    def test_phase2_context_ranking(self, cli, db):
        """Probe queries: T1/T5/T8 must each rank #1.  P@1 = 3/3."""
        time.time()

        probes = [
            (
                "T1",
                "The session reaper thread sometimes closes a session that just received an event. Fix the race between touch and reap in slowave/mcp/session_reaper.py",
                "SessionReaper",
            ),
            (
                "T5",
                "FAISS index rebuild is slow on large stores. Profile and optimize refresh_indices in the episodic store",
                "FAISS index rebuild",
            ),
            (
                "T8",
                "The HTTP MCP daemon fails to start when port 8766 is taken; add a clear error and env override docs",
                "HTTP MCP daemon binds",
            ),
        ]
        hits = 0
        for label, query, snippet in probes:
            r = cli(
                "activate",
                "--query",
                query,
                "--scope",
                "project:slowave",
                "--mode",
                "strict_scope",
                "--limit",
                "8",
            )
            sid = r["session_id"]
            schemas = r.get("schemas", [])
            top_id = schemas[0]["id"] if schemas else None
            target_id = _schema_id_for(db, snippet)
            assert target_id is not None, f"{label}: target schema not found in DB"
            hit = top_id == f"sch_{target_id}"
            if hit:
                hits += 1
                cli(
                    "reinforce",
                    r["retrieval_id"],
                    "--feedback",
                    "useful",
                    "--outcome",
                    "success",
                    "--used",
                    f"sch_{target_id}",
                )
            else:
                cli(
                    "reinforce",
                    r["retrieval_id"],
                    "--feedback",
                    "irrelevant",
                    "--outcome",
                    "success",
                )
            cli("commit", sid, "--outcome", "success")
            _detail(
                f"{label}  {'PASS  rank #1' if hit else f'FAIL  top={top_id}  expected=sch_{target_id}'}"
            )

        assert hits == 3, f"P@1 = {hits}/3"

    # ── Phase 3 ───────────────────────────────────────────────────────────────

    def test_phase3_recall(self, cli, db):
        """R1: T8 in top-3.  R2: T1 in top-3 via paraphrase.  R3: A2 absent cross-scope."""
        time.time()

        # R1
        r1 = cli(
            "recall",
            "how is the HTTP daemon port configured",
            "--scope",
            "project:slowave",
            "--top-k",
            "3",
        )
        t8_id = _schema_id_for(db, "SLOWAVE_MCP_HTTP_PORT")
        ids_r1 = [m["id"] for m in r1["memories"]]
        hit_r1 = f"sch_{t8_id}" in ids_r1
        cli(
            "reinforce",
            r1["retrieval_id"],
            "--feedback",
            "useful" if hit_r1 else "irrelevant",
            "--outcome",
            "success",
            *(["--used", f"sch_{t8_id}"] if hit_r1 else []),
        )
        _detail(f"R1  T8 in top-3  {'PASS' if hit_r1 else 'FAIL'}  results={ids_r1}")
        assert hit_r1, f"R1: T8 not in top-3, got {ids_r1}"

        # R2 — paraphrase (near-zero lexical overlap, embedding path)
        r2 = cli(
            "recall",
            "background thread that closes inactive sessions",
            "--scope",
            "project:slowave",
            "--top-k",
            "3",
        )
        t1_id = _schema_id_for(db, "SessionReaper runs as a daemon")
        ids_r2 = [m["id"] for m in r2["memories"]]
        hit_r2 = f"sch_{t1_id}" in ids_r2
        cli(
            "reinforce",
            r2["retrieval_id"],
            "--feedback",
            "useful" if hit_r2 else "irrelevant",
            "--outcome",
            "success",
            *(["--used", f"sch_{t1_id}"] if hit_r2 else []),
        )
        _detail(f"R2  T1 via paraphrase  {'PASS' if hit_r2 else 'FAIL'}  results={ids_r2}")
        assert hit_r2, f"R2: T1 not in top-3 via paraphrase, got {ids_r2}"

        # R3 — cross-scope isolation
        r3 = cli(
            "recall",
            "tenant isolation SQL placeholder company id",
            "--scope",
            "project:beta",
            "--top-k",
            "5",
        )
        a2_id = _schema_id_for(db, "company_id placeholder")
        ids_r3 = [m["id"] for m in r3["memories"]]
        leak = f"sch_{a2_id}" in ids_r3
        cli("reinforce", r3["retrieval_id"], "--feedback", "irrelevant", "--outcome", "success")
        _detail(
            f"R3  A2 absent in project:beta  {'FAIL (leak!)' if leak else 'PASS'}  results={ids_r3}"
        )
        assert not leak, "R3: cross-scope leak — A2 appeared in project:beta recall"

    # ── Phase 4 ───────────────────────────────────────────────────────────────

    def test_phase4_demotion(self, cli, db):
        """S1 (team retrospective) demoted to is_labile; T1 stays clean;
        S1 then recovers via an explicit useful mark (2026-07-10 labile
        lifecycle, recovery channel 1)."""
        time.time()

        s1_id = _schema_id_for(db, "team retrospective")
        assert s1_id is not None

        demotion_queries = [
            "schedule a meeting with the design team next Friday",
            "what day does the team retrospective happen and does it alternate between online and in person",
            "plan the sprint review calendar for this quarter",
            "when is the next team sync and where is it held",
        ]
        irrelevant_marks = 0
        for q in demotion_queries:
            r = cli(
                "activate", "--query", q, "--scope", "project:slowave", "--mode", "strict_scope"
            )
            sid = r["session_id"]
            appeared = any(s["id"] == f"sch_{s1_id}" for s in r.get("schemas", []))
            if appeared:
                cli(
                    "reinforce",
                    r["retrieval_id"],
                    "--feedback",
                    "irrelevant",
                    "--outcome",
                    "unknown",
                    "--irrelevant",
                    f"sch_{s1_id}",
                )
                irrelevant_marks += 1
                _detail(f"S1 appeared → marked irrelevant  ({irrelevant_marks} marks so far)")
            else:
                cli(
                    "reinforce",
                    r["retrieval_id"],
                    "--feedback",
                    "irrelevant",
                    "--outcome",
                    "unknown",
                )
                _detail("S1 already suppressed")
            cli("commit", sid, "--outcome", "unknown")
            if irrelevant_marks >= 3:
                break

        rows = _query(
            db,
            "SELECT is_labile, json_extract(facets_json,'$.context_noise_score') as noise "
            "FROM schemas WHERE id=?",
            (s1_id,),
        )
        nr, noise = rows[0]["is_labile"], float(rows[0]["noise"] or 0)
        _detail(f"S1  is_labile={nr}  noise_score={noise:.3f}  (threshold 0.75)")

        t1_id = _schema_id_for(db, "SessionReaper runs as a daemon")
        t1_row = _query(db, "SELECT is_labile, status FROM schemas WHERE id=?", (t1_id,))[0]
        _detail(f"T1  is_labile={t1_row['is_labile']}  status={t1_row['status']}")

        assert nr == 1, f"S1 is_labile expected 1, got {nr}"
        assert noise >= 0.75, f"S1 noise_score expected ≥0.75, got {noise:.3f}"
        assert t1_row["status"] == "active"
        assert t1_row["is_labile"] == 0

        # Recovery channel 1 (core/08-feedback.md "Labile State &
        # Reconsolidation"): an explicit "useful" mark is direct positive
        # evidence and clears is_labile immediately, independent of
        # scope_id or the noise-count history that set the flag in the
        # first place.
        r_recover = cli(
            "activate", "--query", "unrelated warm-up query", "--scope", "project:slowave"
        )
        cli(
            "reinforce",
            r_recover["retrieval_id"],
            "--feedback",
            "useful",
            "--outcome",
            "success",
            "--used",
            f"sch_{s1_id}",
        )
        cli("commit", r_recover["session_id"], "--outcome", "success")

        nr_recovered = _query(db, "SELECT is_labile FROM schemas WHERE id=?", (s1_id,))[0][
            "is_labile"
        ]
        _detail(f"S1  is_labile after explicit useful mark: {nr_recovered}  (expected 0)")
        assert (
            nr_recovered == 0
        ), f"S1 should recover via explicit useful feedback, got is_labile={nr_recovered}"

    # ── Phase 4b ──────────────────────────────────────────────────────────────

    def test_phase4b_scope_independent_noise_tracking(self, cli, db):
        """Fixed 2026-07-10: context_noise_score no longer requires scope_id.

        `reinforce` has no --scope flag at all — scope is always auto-derived
        from the activate/recall call that produced the retrieval_id being
        replied to. Calling it against a retrieval_id that was never
        registered by activate/recall (as done here) leaves scope_id NULL
        end-to-end, with no way for this CLI command to supply one directly.
        Before the fix, this silently zeroed out noise tracking with no
        error or warning; D2 must now demote exactly like S1 did in Phase 4,
        purely from scope-less feedback. D2 is deliberately left labile
        going into Phase 5, so that phase's consolidation pass has a real
        candidate for Consolidation's reconsolidation channel (recovery
        channel 3) to examine.
        """
        time.time()

        d2_id = _schema_id_for(db, "must never route through an LLM call")
        assert d2_id is not None

        before = _query(
            db,
            "SELECT is_labile, json_extract(facets_json,'$.context_noise_score') as noise "
            "FROM schemas WHERE id=?",
            (d2_id,),
        )[0]
        noise_before = float(before["noise"] or 0)
        _detail(f"D2 before: is_labile={before['is_labile']}  noise={noise_before:.3f}")

        for i in range(3):
            cli(
                "reinforce",
                f"ctx_never_registered_scope_test_{i}",
                "--feedback",
                "irrelevant",
                "--outcome",
                "unknown",
                "--irrelevant",
                f"sch_{d2_id}",
            )
            _detail(f"scope-less irrelevant mark {i + 1}/3 (no prior activate/recall call at all)")

        after = _query(
            db,
            "SELECT is_labile, json_extract(facets_json,'$.context_noise_score') as noise "
            "FROM schemas WHERE id=?",
            (d2_id,),
        )[0]
        noise_after = float(after["noise"] or 0)
        _detail(f"D2 after:  is_labile={after['is_labile']}  noise={noise_after:.3f}")

        assert noise_after > noise_before, (
            "context_noise_score did not move at all from scope-less feedback — "
            "the 2026-07-10 scope_id fix appears to have regressed"
        )
        assert after["is_labile"] == 1, f"D2 is_labile expected 1, got {after['is_labile']}"

    # ── Phase 5 ───────────────────────────────────────────────────────────────

    def test_phase5_consolidation_hygiene(self, cli, db):
        """Two consolidation passes must not create new schemas; max salience ≤ 20;
        reconsolidation examines D2 (left labile by Phase 4b)."""
        time.time()

        before = _query(db, "SELECT COUNT(*) as n FROM schemas WHERE status='active'")[0]["n"]
        _detail(f"schema count before: {before}")

        r1 = cli("consolidate")
        recon = r1.get("reconsolidation", {})
        _detail(f"reconsolidation (pass 1): {recon}")

        cli("consolidate")

        after = _query(db, "SELECT COUNT(*) as n FROM schemas WHERE status='active'")[0]["n"]
        max_sal = _query(db, "SELECT MAX(salience) as m FROM schemas WHERE status='active'")[0]["m"]
        _detail(f"schema count after:  {after}  (delta={after - before:+d})")
        _detail(f"max salience:        {float(max_sal or 0):.2f}")

        assert after == before, f"Schema count changed: {before} → {after}"
        assert float(max_sal or 0) <= 20.0, f"Max salience {max_sal} > 20"

        # Reconsolidation (2026-07-10, core/05-consolidation.md Phase 7): D2
        # was deliberately left labile by Phase 4b so this pass has a real
        # candidate to examine. The specific outcome (restabilized/
        # superseded/contradicted/inconclusive) depends on real embedding
        # similarity to the rest of the seeded dataset and isn't asserted on
        # directly — only that the mechanism actually ran and accounted for
        # whatever it found.
        assert (
            recon.get("examined", 0) >= 1
        ), f"Expected reconsolidation to examine ≥1 labile schema, got {recon}"
        outcomes = {
            k: recon.get(k, 0)
            for k in ("restabilized", "superseded", "contradicted", "inconclusive")
        }
        _detail(f"reconsolidation outcomes: {outcomes}")
        assert (
            sum(outcomes.values()) == recon["examined"]
        ), f"Outcome counts {outcomes} don't sum to examined={recon['examined']}"

    # ── Phase 6 ───────────────────────────────────────────────────────────────

    def test_phase6_promotion_ladder(self, cli, db):
        """L1 climbs stage 0→1→2→3; stage-3 global admission; kind_bonus fires."""
        time.time()

        l1_id = _schema_id_for(db, "exponential backoff with jitter")
        l2_id = _schema_id_for(db, "Database connection pools")

        def stage_info(schema_id):
            rows = _query(
                db,
                "SELECT generalization_stage as s, "
                "json_extract(facets_json,'$.distinct_scope_count') as scopes, "
                "json_extract(facets_json,'$.scope_breadth_pct') as breadth "
                "FROM schemas WHERE id=?",
                (schema_id,),
            )
            return rows[0] if rows else {}

        def remember_l1_in(scopes_list):
            for scope in scopes_list:
                r = cli("activate", "--query", "implement api retry backoff", "--scope", scope)
                sid = r["session_id"]
                cli("remember", L1_TEXT, "--type", "lesson", "--scope", scope, "--session", sid)
                cli("reinforce", r["retrieval_id"], "--feedback", "missing", "--outcome", "unknown")
                cli("commit", sid, "--outcome", "success")
                _detail(f"L1 remembered in {scope}")

        # Step A — stage 1
        remember_l1_in(["project:gamma", "project:delta"])
        cli("consolidate")
        s = stage_info(l1_id)
        _detail(
            f"after gamma+delta           stage={s['s']}  scopes={s['scopes']}  breadth={s['breadth']}"
        )
        assert s["s"] >= 1, f"expected stage≥1, got {s}"

        # Steps B-C — stage 2
        remember_l1_in(["project:epsilon", "project:zeta", "project:eta"])
        cli("consolidate")
        s = stage_info(l1_id)
        _detail(
            f"after epsilon+zeta+eta      stage={s['s']}  scopes={s['scopes']}  breadth={s['breadth']}"
        )
        assert s["s"] >= 2, f"expected stage≥2, got {s}"

        # Steps D-E — stage 3
        remember_l1_in(["project:theta", "project:alpha", "project:beta"])
        cli("consolidate")
        s = stage_info(l1_id)
        _detail(
            f"after theta+alpha+beta      stage={s['s']}  scopes={s['scopes']}  breadth={s['breadth']}"
        )
        assert s["s"] == 3, f"expected stage 3, got {s}"
        assert int(s["scopes"] or 0) >= 8, f"expected ≥8 scopes, got {s['scopes']}"
        assert float(s["breadth"] or 0) >= 0.78, f"expected breadth≥0.78, got {s['breadth']}"

        # Negative control
        if l2_id:
            s2 = stage_info(l2_id)
            _detail(f"L2 control (no cross-scope) stage={s2['s']}  (expected 0)")
            assert s2["s"] == 0, f"L2 should stay stage 0, got {s2}"

        # Stage-3 global admission
        r = cli(
            "activate",
            "--query",
            "what retry strategy should flaky microservice calls use",
            "--scope",
            "domain:engineering",
            "--mode",
            "strict_scope",
        )
        sid = r["session_id"]
        l1_item = next((x for x in r.get("schemas", []) if x["id"] == f"sch_{l1_id}"), None)
        admitted = l1_item is not None
        penalty = "scope_mismatch" in (l1_item or {}).get("reason", "")
        _detail(
            f"stage-3 in domain:engineering  admitted={admitted}  scope_mismatch_penalty={penalty}"
        )
        if admitted:
            cli(
                "reinforce",
                r["retrieval_id"],
                "--feedback",
                "useful",
                "--outcome",
                "success",
                "--used",
                f"sch_{l1_id}",
            )
        cli("commit", sid, "--outcome", "success")
        cli("consolidate")

        assert admitted, "Stage-3 L1 not admitted in domain:engineering"
        assert not penalty, f"Stage-3 L1 should have no scope_mismatch, reason={l1_item['reason']}"

        # kind_bonus
        kinds = _query(
            db,
            "SELECT json_extract(facets_json,'$.distinct_scope_kind_count') as k "
            "FROM schemas WHERE id=?",
            (l1_id,),
        )[0]["k"]
        _detail(f"distinct_scope_kinds={kinds}  (expected 2 for kind_bonus)")
        assert int(kinds or 0) == 2, f"kind_bonus: expected 2 scope kinds, got {kinds}"

    # ── Phase 7 ───────────────────────────────────────────────────────────────

    def test_phase7_decay(self, cli, db):
        """Episodic-summary schemas decay; explicit_remember and recalled schemas are exempt."""
        time.time()

        # Build a derived schema via session events → consolidate
        r = cli("session", "start", "--scope", "project:slowave", "--agent", "decay-test")
        sid = r["session_id"]
        for content in [
            "The staging rack uses purple cable ties to mark decommissioned servers.",
            "Purple cable ties on any rack mean the machine is decommissioned and safe to unplug.",
            "Facilities confirmed: keep using purple ties for decommissioned machines going forward.",
        ]:
            cli("event", "--session", sid, "--type", "user_message", "--content", content)
        cli("session", "end", sid)
        cli("consolidate")

        derived_id = _schema_id_for(db, "purple cable ties")
        explicit_id = _schema_id_for(db, "SessionReaper runs as a daemon")  # T1: recalled in Ph2/3

        assert derived_id is not None, "Derived schema (purple cable ties) not created"
        assert explicit_id is not None, "T1 explicit schema not found"

        # Two warm-up consolidates to absorb the replay boost from the freshly-
        # created derived schema.  Without these, the decay pass replays the new
        # events and boosts salience BEFORE applying decay, producing a net increase
        # instead of a decrease (see sch_38).
        cli("consolidate")
        cli("consolidate")

        sal_d_before = _query(db, "SELECT salience FROM schemas WHERE id=?", (derived_id,))[0][
            "salience"
        ]
        sal_e_before = _query(db, "SELECT salience FROM schemas WHERE id=?", (explicit_id,))[0][
            "salience"
        ]
        _detail(f"derived  (episodic_summary)  salience before: {sal_d_before:.3f}")
        _detail(f"explicit (recalled T1)        salience before: {sal_e_before:.3f}")

        # --decay-idle-days 0 makes all idle schemas immediately eligible.
        # NOTE: every consolidation pass also runs replay + consolidation,
        # which reinforces existing schemas (+salience_delta). The near-
        # duplicate guard in _write_latent_schema calls reinforce_schema
        # on every pass, so the schema *net* salience always increases.
        # What we verify here is that the decay step actually subtracted
        # salience (decayed > 0) and that explicitly-remembered schemas
        # are left untouched.
        result = cli("consolidate", "--decay-idle-days", "0")
        decay_stats = result.get("decay", {})
        _detail(f"decay stats: {decay_stats}")

        sal_d_after = _query(db, "SELECT salience FROM schemas WHERE id=?", (derived_id,))[0][
            "salience"
        ]
        sal_e_after = _query(db, "SELECT salience FROM schemas WHERE id=?", (explicit_id,))[0][
            "salience"
        ]
        _detail(
            f"derived  salience after:  {sal_d_after:.3f}  (delta={sal_d_after - sal_d_before:+.3f})"
        )
        _detail(
            f"explicit salience after:  {sal_e_after:.3f}  (delta={sal_e_after - sal_e_before:+.3f})"
        )

        # The decay step must have acted on at least one schema (the
        # derived episodic-summary schema we created above is eligible).
        assert (
            decay_stats.get("decayed", 0) > 0
        ), f"Expected at least one schema to decay, got decayed={decay_stats.get('decayed', 0)}"
        assert (
            sal_e_after == sal_e_before
        ), f"Explicit/recalled T1 should not decay: {sal_e_before:.3f} → {sal_e_after:.3f}"

    # ── Relations ─────────────────────────────────────────────────────────────

    def test_relations_schema_evidence(self, db):
        """L1 has ≥8 evidence-linked scopes (one per cross-scope remember)."""
        time.time()

        l1_id = _schema_id_for(db, "exponential backoff with jitter")
        assert l1_id is not None

        rows = _query(
            db,
            """
            SELECT DISTINCT ses.scope_id
            FROM schema_evidence se
            JOIN raw_events re ON re.id = se.raw_event_id
            JOIN sessions ses ON ses.id = re.session_id
            WHERE se.schema_id = ? AND ses.scope_id IS NOT NULL
        """,
            (l1_id,),
        )
        scopes = {r["scope_id"] for r in rows}
        _detail(f"L1 evidence-linked scopes ({len(scopes)}): {sorted(scopes)}")

        assert len(scopes) >= 8, f"Expected ≥8 evidence-linked scopes, got {len(scopes)}: {scopes}"

    def test_relations_evidence_credits_consolidation_path_across_scopes(self, cli, qdb, db):
        """Consolidation-path schema_evidence (raw_event_id=NULL, episode_id set)
        must count toward distinct_scope_count -- regression test for the
        2026-07-15 fix to SchemaStore._update_utility_scores's scope-breadth
        query. That query used to INNER JOIN through raw_events only, which
        NULL raw_event_id can never satisfy, silently excluding every evidence
        row the consolidation / near-duplicate-guard path writes (episode_id-
        based, no raw_event_id) from cross-scope credit -- exactly why a
        schema formed purely from ingested session events (never an explicit
        `remember()` call) could never generalize past stage 1 no matter how
        many scopes its episodes actually spanned.

        Story: the exact same fact, ingested as raw session events (not
        `remember()`) in two different scopes. Consolidation forms a schema
        from the first scope's episode; the near-duplicate guard (cos>=0.92,
        reliably cleared here since the text is byte-identical) then
        reinforces that SAME schema with the second scope's episode. Before
        the fix, that second scope's evidence was invisible to
        distinct_scope_count.
        """
        consolidation_fact = (
            "The nightly backup job compresses the SQLite database with zstd "
            "level 19 and uploads it to the offsite bucket before 4am UTC."
        )
        for scope in ("project:gamma", "project:delta"):
            r = cli("session", "start", "--scope", scope, "--agent", "consolidation-evidence-test")
            sid = r["session_id"]
            cli(
                "event", "--session", sid, "--type", "user_message", "--content", consolidation_fact
            )
            cli("session", "end", sid)
            cli("consolidate")
            _detail(f"ingested + consolidated in {scope}")

        schema_id = _schema_id_for(db, "nightly backup job compresses")
        assert schema_id is not None, "consolidation-derived schema not found"

        row = qdb(
            "SELECT json_extract(facets_json,'$.distinct_scope_count') as scopes "
            "FROM schemas WHERE id=?",
            (schema_id,),
        )[0]
        _detail(f"consolidation-path schema distinct_scope_count={row['scopes']}")
        assert (
            int(row["scopes"] or 0) >= 2
        ), f"expected >=2 scopes credited via the episode_id evidence path, got {row['scopes']}"

        # Confirm the credit genuinely came through the NULL-raw_event_id path
        # this test targets -- this schema was created purely from
        # `event`/`session end`, never `remember()`, so a passing assertion
        # above that was secretly satisfied via the raw_event_id path alone
        # would not actually be exercising the fix.
        evidence_rows = qdb(
            "SELECT raw_event_id, episode_id FROM schema_evidence WHERE schema_id=?",
            (schema_id,),
        )
        assert any(
            r["raw_event_id"] is None and r["episode_id"] is not None for r in evidence_rows
        ), "expected at least one NULL-raw_event_id, episode_id-based evidence row"

    def test_relations_cross_scope_isolation(self, db):
        """Stage-0 project:slowave schemas must not have evidence from
        project:alpha, via EITHER evidence path -- the explicit-remember
        raw_event_id join, or the consolidation-path episode_id join (see
        SchemaStore._update_utility_scores's UNION query, extended 2026-07-15
        to also credit the episode_id path; this isolation check must cover
        the same UNION or a leak introduced via the new path would go
        undetected here)."""
        time.time()

        rows = _query(
            db,
            """
            SELECT DISTINCT sch.id, sch.content_text, ev.scope_id
            FROM (
                SELECT se.schema_id AS schema_id, ses.scope_id AS scope_id
                FROM schema_evidence se
                JOIN raw_events re ON re.id = se.raw_event_id
                JOIN sessions ses ON ses.id = re.session_id
                WHERE se.raw_event_id IS NOT NULL
                UNION
                SELECT se.schema_id AS schema_id, ses.scope_id AS scope_id
                FROM schema_evidence se
                JOIN episode_text et ON et.episode_id = se.episode_id
                JOIN sessions ses ON ses.id = et.session_id
                WHERE se.raw_event_id IS NULL AND se.episode_id IS NOT NULL
            ) ev
            JOIN schemas sch ON sch.id = ev.schema_id
            WHERE sch.scope_id = 'project:slowave'
              AND ev.scope_id = 'project:alpha'
              AND sch.generalization_stage = 0
        """,
        )
        if rows:
            for r in rows:
                _detail(
                    f"  LEAK sch_{r['id']}  '{r['content_text'][:60]}...'  from {r['scope_id']}"
                )

        assert len(rows) == 0, (
            f"Cross-scope evidence leak: {len(rows)} stage-0 project:slowave schemas "
            f"have evidence from project:alpha"
        )

    def test_relations_supersession(self, cli, db):
        """Remembering an updated fact in the same scope creates a supersedes edge.

        schema_relations stores (new_id → old_id, relation='supersedes') and the
        old schema is flipped to status='superseded'.
        """
        time.time()

        # Original fact about session timeout
        r = cli("activate", "--query", "session timeout config", "--scope", "project:slowave")
        sid = r["session_id"]
        r_old = cli(
            "remember",
            "The session idle timeout defaults to 3600 seconds and is controlled by the SLOWAVE_SESSION_IDLE_TIMEOUT environment variable.",
            "--type",
            "fact",
            "--scope",
            "project:slowave",
            "--session",
            sid,
        )
        old_id_str = r_old.get("schema_id")  # e.g. "sch_42"
        cli("reinforce", r["retrieval_id"], "--feedback", "missing", "--outcome", "unknown")
        cli("commit", sid, "--outcome", "success")

        assert old_id_str, "Original schema not created"
        old_id = int(old_id_str.lstrip("sch_"))
        _detail(f"original schema: {old_id_str}  status=active")

        # Updated fact — same topic, changed value (3600 → 1800, new env var note)
        r2 = cli(
            "activate", "--query", "session timeout config update", "--scope", "project:slowave"
        )
        sid2 = r2["session_id"]
        r_new = cli(
            "remember",
            "The session idle timeout was changed from 3600 to 1800 seconds; "
            "set SLOWAVE_SESSION_IDLE_TIMEOUT=1800 to apply the new default.",
            "--type",
            "fact",
            "--scope",
            "project:slowave",
            "--session",
            sid2,
        )
        new_id_str = r_new.get("schema_id")
        cli("reinforce", r2["retrieval_id"], "--feedback", "missing", "--outcome", "unknown")
        cli("commit", sid2, "--outcome", "success")

        assert new_id_str, "Updated schema not created"
        new_id = int(new_id_str.lstrip("sch_"))
        _detail(f"updated schema:  {new_id_str}")

        # Check old schema status
        old_status = _query(db, "SELECT status FROM schemas WHERE id=?", (old_id,))
        _detail(f"original schema status: {old_status[0]['status'] if old_status else 'not found'}")

        # Check schema_relations for a supersedes edge
        rel_rows = _query(
            db,
            "SELECT src_schema_id, dst_schema_id, relation FROM schema_relations "
            "WHERE src_schema_id=? AND dst_schema_id=?",
            (new_id, old_id),
        )
        _detail(f"schema_relations rows: {rel_rows}")

        if old_status and old_status[0]["status"] == "superseded":
            assert (
                rel_rows
            ), f"Old schema {old_id_str} is superseded but no schema_relations edge found"
            assert (
                rel_rows[0]["relation"] == "supersedes"
            ), f"Expected relation='supersedes', got '{rel_rows[0]['relation']}'"
        else:
            # Supersession requires cos >= 0.85 between embeddings; if it didn't fire,
            # at minimum verify old schema is still active (no spurious status change).
            assert old_status and old_status[0]["status"] == "active", (
                f"Old schema should be active (supersession did not fire), "
                f"got status={old_status[0]['status'] if old_status else 'missing'}"
            )
            _detail(
                "supersession did not fire (cosine below 0.85 threshold) — old schema still active"
            )

    def test_relations_coactivation(self, cli, db):
        """Consolidation replay must populate prototype_edges with co-activation weights.

        prototype_edges.w_coactivation is updated during ReplayEngine.replay_once() when
        two prototypes co-appear in the same episode. After at least one consolidation
        pass over real episodic content, the table must be non-empty.
        """
        time.time()

        # Build an episode with multiple events so replay has something to process
        r = cli("session", "start", "--scope", "project:slowave", "--agent", "coact-test")
        sid = r["session_id"]
        cli(
            "event",
            "--session",
            sid,
            "--type",
            "user_message",
            "--content",
            "The HTTP daemon uses a PID file and runs on port 8766.",
        )
        cli(
            "event",
            "--session",
            sid,
            "--type",
            "assistant_message",
            "--content",
            "Correct — SLOWAVE_MCP_HTTP_PORT controls the port, SLOWAVE_DAEMON_PID the PID file.",
        )
        cli(
            "event",
            "--session",
            sid,
            "--type",
            "user_message",
            "--content",
            "And the SessionReaper runs in the background checking every 60 seconds.",
        )
        cli("session", "end", sid)

        # Run consolidation — replay_once() builds prototype edges from episodes
        cli("consolidate")

        # After consolidation, prototype_edges should contain entries
        edge_rows = _query(db, "SELECT COUNT(*) as n FROM prototype_edges")
        proto_rows = _query(db, "SELECT COUNT(*) as n FROM semantic_prototypes")
        _detail(f"semantic_prototypes: {proto_rows[0]['n']}")
        _detail(f"prototype_edges:     {edge_rows[0]['n']}")

        if proto_rows[0]["n"] >= 2:
            # If there are prototypes, there should be edges between them
            assert edge_rows[0]["n"] > 0, (
                f"Expected prototype_edges to be populated after consolidation "
                f"({proto_rows[0]['n']} prototypes exist but 0 edges found)"
            )
            # Verify edge structure: weights must be non-negative
            weight_rows = _query(
                db,
                "SELECT MIN(w_coactivation) as min_co, MAX(weight) as max_w "
                "FROM prototype_edges",
            )
            _detail(
                f"edge weights: min_coactivation={weight_rows[0]['min_co']:.4f}  max_weight={weight_rows[0]['max_w']:.4f}"
            )
            assert float(weight_rows[0]["min_co"] or 0) >= 0, "w_coactivation must be non-negative"
            assert float(weight_rows[0]["max_w"] or 0) > 0, "At least one edge must have weight > 0"
        else:
            _detail("fewer than 2 prototypes — edges not expected (latent layer may not have run)")

    def test_relations_part_of_hierarchy(self, cli, qdb):
        """A specific fact can be linked as `part_of` a broader one it's a
        detail of, and recall() surfaces that link even when the caller only
        asked about the broader topic.

        Story: an agent tells Slowave a general fact about a service's retry
        behaviour ("the billing service retries webhooks with backoff"),
        then a more specific detail of the same behaviour ("...using a base
        delay of 2 seconds, capped at 32"), each repeated a few times (this
        is how a fact earns enough evidence to be compared geometrically —
        see backfill_facet_axes). It also tells Slowave a third, unrelated
        fact in a different project. After the next `consolidate` (Slowave's
        background housekeeping), recalling the general topic should surface
        the specific detail too, under `related_memories` -- NOT because it
        matched the query, but because Slowave noticed it's a more specific
        instance of the same thing. The unrelated fact from the other
        project must never show up, proving relation-based surfacing isn't a
        scope leak in disguise.

        Endpoint-driven throughout (remember -> consolidate -> recall); a
        direct DB read is used only as a secondary confirmation of the
        specific relation recorded, never as the pass/fail signal.
        """
        parent_text = (
            "The billing service retries failed webhook deliveries up to 5 times "
            "with exponential backoff before giving up."
        )
        child_text = (
            "Specifically, webhook retries for the billing service use a base delay "
            "of 2 seconds doubling each attempt, capped at 32 seconds."
        )
        unrelated_text = (
            "The internal style guide requires all product screenshots to use the "
            "dark theme for consistency in Alpha's documentation."
        )

        # Repeat each fact so it earns enough evidence to be compared
        # geometrically (backfill_facet_axes needs >=3 supporting episodes).
        for text, scope in (
            (parent_text, "project:slowave"),
            (child_text, "project:slowave"),
            (unrelated_text, "project:alpha"),
        ):
            for _ in range(3):
                cli("remember", text, "--type", "fact", "--scope", scope)

        # Slowave's background housekeeping: computes facet axes for newly-
        # eligible facts and compares them for hierarchy. Both counts are
        # read straight from the endpoint's own response.
        r = cli("consolidate")
        facet_backfill = r.get("facet_backfill", {})
        part_of_backfill = r.get("part_of_backfill", {})
        _detail(f"facet_backfill: {facet_backfill}")
        _detail(f"part_of_backfill: {part_of_backfill}")
        assert (
            facet_backfill.get("backfilled", 0) >= 3
        ), "expected all 3 newly-repeated facts to cross the facet-eligibility threshold"
        assert set(part_of_backfill) >= {
            "compared",
            "created",
            "skipped_no_facets",
        }, "part_of comparison did not run with the expected shape"

        # Ask about the general topic only -- the specific detail must not be
        # required to match the query text itself to surface.
        r_parent = cli(
            "recall",
            "billing service webhook retry backoff delivery",
            "--scope",
            "project:slowave",
            "--top-k",
            "3",
        )
        direct_texts = [m["content_text"] for m in r_parent["memories"]]
        related = r_parent.get("related_memories", [])
        _detail(f"direct recall results: {[t[:60] for t in direct_texts]}")
        _detail(f"related_memories: {[(m['content_text'][:60], m['via']) for m in related]}")

        # Deterministic: the unrelated cross-scope fact must never appear,
        # neither as a direct hit nor riding in via a relation edge.
        all_texts = direct_texts + [m["content_text"] for m in related]
        assert not any(
            "dark theme" in t for t in all_texts
        ), "unrelated cross-scope fact leaked into recall results"

        # Conditional: whether the child actually rides in as `part_of` this
        # run depends on real embedding geometry (same caveat as
        # test_relations_supersession's supersedes check) -- logged either
        # way, required only when it does fire.
        part_of_hits = [m for m in related if "part_of" in m.get("via", [])]
        if part_of_hits:
            assert any(
                "base delay of 2 seconds" in m["content_text"] for m in part_of_hits
            ), "a part_of-linked memory surfaced but wasn't the expected child fact"
            # Secondary confirmation only -- the endpoint result above is
            # already the pass/fail signal.
            rel_rows = qdb(
                "SELECT confidence FROM schema_relations WHERE relation='part_of' "
                "AND src_schema_id IN (SELECT id FROM schemas WHERE content_text LIKE ?)",
                ("%base delay of 2 seconds%",),
            )
            if rel_rows:
                _detail(f"confirmed in DB: part_of confidence={rel_rows[0]['confidence']:.3f}")
        else:
            _detail(
                "no part_of-linked memory surfaced this run "
                "(subspace containment is real-embedding dependent, not guaranteed every run)"
            )

    def test_relations_graph_expansion_respects_cross_scope_isolation(self, cli):
        """A memory linked to another project's memory via schema_relations
        must not leak across projects just because it rode in on a relation
        edge instead of matching the query directly.

        Story: schema_relations edges (part_of especially) are deliberately
        allowed to link memories across projects once there's strong enough
        geometric evidence (see backfill_part_of_edges's stricter cross-scope
        containment bar) -- a relation edge is not itself a scope wall. So
        whenever `recall()` surfaces a related_memories entry, it must still
        respect the same project-isolation rule a directly-matched memory
        would: same project, no project at all (global), or the memory has
        independently earned broad cross-project visibility
        (generalization_stage >= 2 -- see the promotion-ladder phase above).

        Probes broadly across the whole dataset built up by every prior
        phase (not just test_relations_part_of_hierarchy's facts), since
        which relation actually clears the activation threshold to surface
        is real-embedding dependent. Reads scope_id/generalization_stage
        straight off each related_memories entry -- no DB access at all.
        """
        probes = [
            ("webhook retries billing service backoff", "project:slowave"),
            ("session reaper daemon thread configuration", "project:slowave"),
            ("API retry loop backoff jitter", "project:slowave"),
        ]
        found_any = False
        for query, scope in probes:
            r = cli("recall", query, "--scope", scope, "--mode", "strict_scope", "--top-k", "5")
            for m in r.get("related_memories", []):
                found_any = True
                _detail(
                    f"related memory {m['id']}  scope={m['scope_id']}  "
                    f"stage={m['generalization_stage']}  via={m['via']}  (query scope={scope})"
                )
                assert (
                    m["scope_id"] is None
                    or m["scope_id"] == scope
                    or m["generalization_stage"] >= 2
                ), f"cross-project leak via relation-based surfacing: {m}"

        _detail(
            "relation-surfaced memories observed and verified safe this run"
            if found_any
            else "no relation-surfaced memories this run (real-embedding dependent)"
        )

    def test_relations_no_reverse_directional_duplicates(self, qdb):
        """Directional relations (refines/supersedes/part_of) must never exist
        in both directions for the same pair -- regression test for
        add_relation()'s reverse-edge guard (2026-07-15). Unlike the other
        relation tests in this file, this is a deterministic invariant, not
        real-embedding dependent: it must hold no matter which relations the
        rest of the suite happened to produce, so it's asserted unconditionally
        against whatever schema_relations looks like after every prior phase
        has run.

        A directional relation encodes an asymmetric claim (specialization,
        value-update, subspace containment); both directions existing at once
        for the same relation type is a logical contradiction, not two
        independent facts -- e.g. "A refines B" and "B refines A" can't both
        be true. Symmetric relations (reinforces, relates_to) are correctly
        exempt: "A->B" and "B->A" are the same fact there, not a conflict.
        """
        rows = qdb("""
            SELECT a.relation, a.src_schema_id, a.dst_schema_id
            FROM schema_relations a
            JOIN schema_relations b
              ON a.relation = b.relation
             AND a.src_schema_id = b.dst_schema_id
             AND a.dst_schema_id = b.src_schema_id
            WHERE a.relation IN ('refines', 'supersedes', 'part_of')
            """)
        assert rows == [], f"found reverse-direction duplicate directional edges: {rows}"
