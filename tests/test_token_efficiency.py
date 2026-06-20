"""
Slowave Token Efficiency Benchmark -- Reliable Version
=======================================================

Measures whether Slowave context_brief() saves tokens vs two realistic
baselines, while simultaneously verifying retrieval quality.

What makes this test credible:
  - Uses the real paraphrase-multilingual-MiniLM-L12-v2 ONNX encoder (real semantic filtering)
  - 20 diverse memories (preferences, facts, decisions, lessons)
  - 20 realistic sessions each with a distinct query and a verifiable
    expected keyword that MUST appear in the brief if retrieval is working
  - Measures BOTH token cost AND recall quality per session
  - Reports: per-session table, crossover point, honest verdict

Baselines:
  A. History Replay -- full transcript of all prior session events accumulated
     and re-injected at each new session. Grows linearly with session count.
  B. Static Knowledge Doc -- all project context in one markdown file, injected
     every session regardless of relevance. Constant cost, never adapts.

Slowave:
  context_brief(query=...) -- semantically filtered, salience-ranked,
  hard-capped at 1800 chars.

Run:
  .venv/bin/python -m pytest tests/test_token_efficiency.py -v -s
  .venv/bin/python tests/test_token_efficiency.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine

# --------------------------------------------------------------------------
# Shared encoder
# --------------------------------------------------------------------------

_ENCODER = None


def _get_encoder():
    global _ENCODER
    if _ENCODER is None:
        from slowave.core.config import EncoderConfig
        from slowave.symbolic.encoder import TextEncoder
        _ENCODER = TextEncoder(EncoderConfig())
    return _ENCODER


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _tmp_engine() -> tuple[SlowaveEngine, str]:
    """Fresh engine backed by the real semantic encoder."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    cfg = SlowaveConfig(db_path=tmp.name)
    return SlowaveEngine(cfg, shared_encoder=_get_encoder()), tmp.name


def _cleanup(path: str) -> None:
    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            os.remove(p)


def _tokens(text: str) -> int:
    """Rough token estimate: len(text) // 4.  GPT-style, +-15%."""
    return max(1, len(text) // 4)


# --------------------------------------------------------------------------
# Scenario data
# --------------------------------------------------------------------------
# Each memory has a unique keyword.
# Each session has a query and an expected_keyword -- the keyword that should
# appear in the Slowave brief when that query is issued.

MEMORIES: list[dict[str, str]] = [
    {"content": "Alice prefers Python over Java for all backend services.", "type": "preference", "keyword": "Python"},
    {"content": "Alice uses dark mode in all editors and terminals.", "type": "preference", "keyword": "dark mode"},
    {"content": "Alice drinks espresso every morning before coding.", "type": "preference", "keyword": "espresso"},
    {"content": "Alice prefers async/await over callbacks for async Python code.", "type": "preference", "keyword": "async"},
    {"content": "Alice uses vim keybindings in all IDEs and editors.", "type": "preference", "keyword": "vim"},
    {"content": "The project uses PostgreSQL 15 as the primary database.", "type": "fact", "keyword": "PostgreSQL"},
    {"content": "The API is deployed on AWS us-east-1 behind an ALB.", "type": "fact", "keyword": "AWS"},
    {"content": "The codebase is written in Python 3.12 with strict type hints.", "type": "fact", "keyword": "3.12"},
    {"content": "The CI pipeline runs on GitHub Actions with matrix builds.", "type": "fact", "keyword": "GitHub Actions"},
    {"content": "The team follows trunk-based development with feature flags.", "type": "fact", "keyword": "trunk-based"},
    {"content": "The frontend is built with Next.js and deployed on Vercel.", "type": "fact", "keyword": "Vercel"},
    {"content": "Redis 7 is used for session caching and rate limiting.", "type": "fact", "keyword": "Redis"},
    {"content": "We decided to use FastAPI instead of Flask for the new microservice.", "type": "decision", "keyword": "FastAPI"},
    {"content": "We chose SQLAlchemy 2.0 with async support for ORM.", "type": "decision", "keyword": "SQLAlchemy"},
    {"content": "The team decided to adopt OpenTelemetry for distributed tracing.", "type": "decision", "keyword": "OpenTelemetry"},
    {"content": "We decided to use Terraform for all infrastructure provisioning.", "type": "decision", "keyword": "Terraform"},
    {"content": "Always add database indexes before running load tests in production.", "type": "lesson", "keyword": "indexes"},
    {"content": "Never store secrets in environment variables committed to git.", "type": "lesson", "keyword": "secrets"},
    {"content": "Writing tests before any refactoring prevents regressions.", "type": "lesson", "keyword": "refactoring"},
    {"content": "Always use connection pooling when deploying to AWS Lambda.", "type": "lesson", "keyword": "pooling"},
]

SESSIONS: list[dict[str, Any]] = [
    {
        "query": "I am about to refactor the authentication module using our web framework",
        "expected_keyword": "FastAPI",
        "events": [
            {"type": "user_message", "content": "Starting the auth module refactoring today."},
            {"type": "assistant_message", "content": "I will help plan the auth refactoring."},
            {"type": "user_message", "content": "The current implementation uses JWT tokens for stateless auth."},
            {"type": "assistant_message", "content": "JWT is solid. We should add refresh token rotation."},
            {"type": "user_message", "content": "Also need rate limiting on the login endpoint."},
            {"type": "assistant_message", "content": "Redis would work well for rate limiting."},
        ],
    },
    {
        "query": "Planning a database schema migration",
        "expected_keyword": "PostgreSQL",
        "events": [
            {"type": "user_message", "content": "We need to migrate the users table to add a new column."},
            {"type": "assistant_message", "content": "What type and constraints should the column have?"},
            {"type": "user_message", "content": "A nullable JSONB column for user preferences."},
            {"type": "assistant_message", "content": "JSONB is efficient for semi-structured data."},
            {"type": "user_message", "content": "Should we add an index on the JSONB column?"},
            {"type": "assistant_message", "content": "Yes, a GIN index enables fast key lookups in JSONB."},
        ],
    },
    {
        "query": "Setting up deployment for a new service on our cloud provider",
        "expected_keyword": "AWS",
        "events": [
            {"type": "user_message", "content": "How should we deploy the new notification service?"},
            {"type": "assistant_message", "content": "Let us containerise it with Docker first."},
            {"type": "user_message", "content": "We need it to scale automatically under load."},
            {"type": "assistant_message", "content": "ECS Fargate with auto-scaling fits our current setup."},
            {"type": "user_message", "content": "What region should we target?"},
            {"type": "assistant_message", "content": "Stay consistent with the stack, us-east-1."},
        ],
    },
    {
        "query": "Adding a security scan step to the continuous integration pipeline",
        "expected_keyword": "GitHub Actions",
        "events": [
            {"type": "user_message", "content": "We need to add a security scan step to CI."},
            {"type": "assistant_message", "content": "We can add a Trivy scan step to the existing workflow."},
            {"type": "user_message", "content": "Should it block the build on critical findings?"},
            {"type": "assistant_message", "content": "Yes, fail on CRITICAL severity and above."},
            {"type": "user_message", "content": "We also want to cache pip dependencies."},
            {"type": "assistant_message", "content": "The actions/cache step handles requirements.txt well."},
        ],
    },
    {
        "query": "Reviewing a backend pull request for the Python service",
        "expected_keyword": "Python",
        "events": [
            {"type": "user_message", "content": "Can you review this PR? It adds a new API endpoint."},
            {"type": "assistant_message", "content": "I will check the logic and test coverage."},
            {"type": "user_message", "content": "The endpoint handles file uploads asynchronously."},
            {"type": "assistant_message", "content": "Async file handling is good. Check memory usage."},
            {"type": "user_message", "content": "Tests are missing for the error path."},
            {"type": "assistant_message", "content": "Add a test for 413 Payload Too Large."},
        ],
    },
    {
        "query": "Deploying the Next.js frontend to production",
        "expected_keyword": "Vercel",
        "events": [
            {"type": "user_message", "content": "The frontend build is passing CI. Ready to deploy."},
            {"type": "assistant_message", "content": "Push to main to trigger the production deployment."},
            {"type": "user_message", "content": "Should we add a preview deploy for PRs?"},
            {"type": "assistant_message", "content": "Yes, preview URLs are created automatically for each PR."},
            {"type": "user_message", "content": "Can we set environment variables per branch?"},
            {"type": "assistant_message", "content": "Yes, via the project settings dashboard."},
        ],
    },
    {
        "query": "Designing a caching layer for the API to reduce response times",
        "expected_keyword": "Redis",
        "events": [
            {"type": "user_message", "content": "API response times are slow for expensive queries."},
            {"type": "assistant_message", "content": "Cache those queries with a TTL."},
            {"type": "user_message", "content": "We need per-user cache invalidation."},
            {"type": "assistant_message", "content": "Use key namespacing with user ID prefixes."},
            {"type": "user_message", "content": "What TTL makes sense for user profile data?"},
            {"type": "assistant_message", "content": "5 to 15 minutes depending on update frequency."},
        ],
    },
    {
        "query": "Writing infrastructure as code for a new staging environment",
        "expected_keyword": "Terraform",
        "events": [
            {"type": "user_message", "content": "We need to spin up a staging environment."},
            {"type": "assistant_message", "content": "Let us parameterise the existing IaC modules."},
            {"type": "user_message", "content": "The staging DB should be smaller than production."},
            {"type": "assistant_message", "content": "Set instance_class=db.t3.medium for staging."},
            {"type": "user_message", "content": "We also need a separate VPC for staging."},
            {"type": "assistant_message", "content": "Add a new VPC module instance with a staging CIDR block."},
        ],
    },
    {
        "query": "Setting up distributed tracing across microservices",
        "expected_keyword": "OpenTelemetry",
        "events": [
            {"type": "user_message", "content": "We need to trace requests across auth and user services."},
            {"type": "assistant_message", "content": "Instrument both services with the same tracer."},
            {"type": "user_message", "content": "What backend should we use for trace storage?"},
            {"type": "assistant_message", "content": "Jaeger or Tempo both work well with OTLP exporters."},
            {"type": "user_message", "content": "Does it work with our Python code?"},
            {"type": "assistant_message", "content": "Yes, opentelemetry-sdk has async Python support."},
        ],
    },
    {
        "query": "Pre-load-test checklist, checking database query performance",
        "expected_keyword": "indexes",
        "events": [
            {"type": "user_message", "content": "Preparing to run load tests on the API."},
            {"type": "assistant_message", "content": "Enable slow query logging first."},
            {"type": "user_message", "content": "EXPLAIN ANALYZE is showing sequential scans."},
            {"type": "assistant_message", "content": "Add missing indexes before the full load test."},
            {"type": "user_message", "content": "Which queries hit the users table most?"},
            {"type": "assistant_message", "content": "Email and status lookups, both need indexes."},
        ],
    },
    {
        "query": "Rotating API secrets and credentials after a security audit",
        "expected_keyword": "secrets",
        "events": [
            {"type": "user_message", "content": "We need to rotate the API keys after the security audit."},
            {"type": "assistant_message", "content": "Use AWS Secrets Manager for automated rotation."},
            {"type": "user_message", "content": "Some secrets are still in the old .env file."},
            {"type": "assistant_message", "content": "Migrate them to Secrets Manager immediately."},
            {"type": "user_message", "content": "Should we scan git history for leaked keys?"},
            {"type": "assistant_message", "content": "Yes, run trufflehog to scan the history."},
        ],
    },
    {
        "query": "Refactoring synchronous blocking code to async patterns",
        "expected_keyword": "async",
        "events": [
            {"type": "user_message", "content": "The ingestion pipeline is blocking the event loop."},
            {"type": "assistant_message", "content": "Wrap sync calls with asyncio.to_thread."},
            {"type": "user_message", "content": "Some third-party libs are sync-only."},
            {"type": "assistant_message", "content": "Use run_in_executor for those."},
            {"type": "user_message", "content": "How do we test async code in pytest?"},
            {"type": "assistant_message", "content": "Use pytest-asyncio with async test functions."},
        ],
    },
    {
        "query": "Upgrading the ORM to use async sessions",
        "expected_keyword": "SQLAlchemy",
        "events": [
            {"type": "user_message", "content": "We need to upgrade from SQLAlchemy 1.4 to 2.0."},
            {"type": "assistant_message", "content": "The migration guide covers most breaking changes."},
            {"type": "user_message", "content": "Our models use the old declarative API."},
            {"type": "assistant_message", "content": "DeclarativeBase replaces declarative_base() in 2.0."},
            {"type": "user_message", "content": "Do we need to change session management?"},
            {"type": "assistant_message", "content": "Yes, AsyncSession is the preferred pattern in 2.0."},
        ],
    },
    {
        "query": "Starting the workday and planning morning tasks",
        "expected_keyword": "espresso",
        "events": [
            {"type": "user_message", "content": "Just had my morning coffee. What should I tackle first?"},
            {"type": "assistant_message", "content": "The auth PR is waiting for review."},
            {"type": "user_message", "content": "Also the pipeline is flaky today."},
            {"type": "assistant_message", "content": "The integration test flakiness needs a fix first."},
            {"type": "user_message", "content": "I will start with the PR review."},
            {"type": "assistant_message", "content": "Good call. Reviewer feedback is already there."},
        ],
    },
    {
        "query": "Discussing git branching and merge strategy with the team",
        "expected_keyword": "trunk-based",
        "events": [
            {"type": "user_message", "content": "The team is debating Gitflow vs trunk-based development."},
            {"type": "assistant_message", "content": "We already decided trunk-based with feature flags."},
            {"type": "user_message", "content": "Some developers keep long-lived feature branches."},
            {"type": "assistant_message", "content": "They need to align with the team decision."},
            {"type": "user_message", "content": "Should we add a branch protection rule?"},
            {"type": "assistant_message", "content": "Yes, require PR review and CI to pass before merge."},
        ],
    },
    {
        "query": "Investigating Lambda connection timeout errors hitting the database",
        "expected_keyword": "pooling",
        "events": [
            {"type": "user_message", "content": "Lambda functions are timing out connecting to PostgreSQL."},
            {"type": "assistant_message", "content": "Lambda cold starts exhaust DB connections quickly."},
            {"type": "user_message", "content": "We have 200 Lambda instances running concurrently."},
            {"type": "assistant_message", "content": "Use RDS Proxy to pool and reuse connections."},
            {"type": "user_message", "content": "Is PgBouncer an option?"},
            {"type": "assistant_message", "content": "RDS Proxy integrates better with IAM auth on AWS."},
        ],
    },
    {
        "query": "Planning a large-scale refactoring sprint for the payment module",
        "expected_keyword": "refactoring",
        "events": [
            {"type": "user_message", "content": "We are planning a two-week refactoring sprint."},
            {"type": "assistant_message", "content": "What is the scope of the work?"},
            {"type": "user_message", "content": "The payment module needs the most attention."},
            {"type": "assistant_message", "content": "Start with characterisation tests before touching code."},
            {"type": "user_message", "content": "Test coverage is very poor in that module."},
            {"type": "assistant_message", "content": "Writing tests before any changes is critical."},
        ],
    },
    {
        "query": "Adding type annotations to legacy Python codebase",
        "expected_keyword": "Python",
        "events": [
            {"type": "user_message", "content": "We want to add type hints to the old utility modules."},
            {"type": "assistant_message", "content": "Run mypy in strict mode to find what is missing."},
            {"type": "user_message", "content": "Some modules use Python 2 style type comments."},
            {"type": "assistant_message", "content": "pyupgrade can automatically convert those annotations."},
            {"type": "user_message", "content": "Should we use TypedDict for config objects?"},
            {"type": "assistant_message", "content": "Yes for config; dataclasses are better for mutable state."},
        ],
    },
    {
        "query": "Configuring a new developer machine with preferred editor settings",
        "expected_keyword": "dark mode",
        "events": [
            {"type": "user_message", "content": "Setting up a new dev machine. What should I install?"},
            {"type": "assistant_message", "content": "Start with pyenv for Python version management."},
            {"type": "user_message", "content": "I prefer the terminal over GUI apps."},
            {"type": "assistant_message", "content": "tmux plus Wezterm is a solid terminal setup."},
            {"type": "user_message", "content": "Any theme recommendations?"},
            {"type": "assistant_message", "content": "Catppuccin Mocha or Tokyo Night suit a dark environment."},
        ],
    },
    {
        "query": "Sprint planning for a new service built with our Python web framework",
        "expected_keyword": "FastAPI",
        "events": [
            {"type": "user_message", "content": "We need to plan the next sprint for the new API service."},
            {"type": "assistant_message", "content": "What features are blocked on the new service?"},
            {"type": "user_message", "content": "The notification and search endpoints are both needed."},
            {"type": "assistant_message", "content": "Both can be separate routers in the same monorepo."},
            {"type": "user_message", "content": "How should we handle API versioning?"},
            {"type": "assistant_message", "content": "Prefix routes with /v1/ and group with APIRouter."},
        ],
    },
]

def _build_static_doc() -> str:
    """All project memories as a markdown knowledge file.

    Represents the static-doc baseline: everything dumped once into a
    markdown file (like CLAUDE.md) and injected every session.
    """
    by_type: dict[str, list[str]] = {}
    for m in MEMORIES:
        by_type.setdefault(m["type"], []).append(m["content"])
    lines = ["# Project & Developer Context\n"]
    for t, items in sorted(by_type.items()):
        lines.append("\n## " + t.title() + "s")
        for item in items:
            lines.append("- " + item)
    return "\n".join(lines)



# --------------------------------------------------------------------------
# Main benchmark function
# --------------------------------------------------------------------------


def run_token_efficiency_test() -> dict[str, Any]:
    """Run the benchmark and return a results dict (CONFIRMED/PARTIAL/REFUTED)."""
    engine, db_path = _tmp_engine()
    static_doc = _build_static_doc()
    static_tokens = _tokens(static_doc)

    try:
        for mem in MEMORIES:
            engine.remember(content=mem["content"], type=mem["type"])
        engine.consolidate_once()

        history_transcript = ""
        per_session: list[dict[str, Any]] = []

        for idx, sess in enumerate(SESSIONS):
            sid = engine.session_start(agent="benchmark")
            for evt in sess["events"]:
                engine.event_append(session_id=sid, type=evt["type"], content=evt["content"])
            engine.session_end(sid)

            for evt in sess["events"]:
                history_transcript += evt["type"] + ": " + evt["content"] + "\n"
            history_tok = _tokens(history_transcript)

            brief = engine.context_brief(query=sess["query"], limit=8)
            slowave_tok = _tokens(brief.rendered) if brief.rendered else 1
            kw = sess["expected_keyword"].lower()

            per_session.append({
                "session": idx + 1,
                "query": sess["query"],
                "expected_keyword": sess["expected_keyword"],
                "quality_hit": kw in brief.rendered.lower(),
                "tokens_history": history_tok,
                "tokens_static": static_tokens,
                "tokens_slowave": slowave_tok,
                "brief_items": len(brief.items),
                "brief_rendered": brief.rendered,
            })

        h_list  = [s["tokens_history"]  for s in per_session]
        st_list = [s["tokens_static"]   for s in per_session]
        sw_list = [s["tokens_slowave"]  for s in per_session]
        hits = sum(1 for s in per_session if s["quality_hit"])
        quality_pct = 100.0 * hits / len(per_session)
        avg_h  = sum(h_list)  / len(h_list)
        avg_st = sum(st_list) / len(st_list)
        avg_sw = sum(sw_list) / len(sw_list)
        save_vs_history = 100.0 * (1 - avg_sw / avg_h)  if avg_h  > 0 else 0.0
        save_vs_static  = 100.0 * (1 - avg_sw / avg_st) if avg_st > 0 else 0.0
        crossover = next(
            (s["session"] for s in per_session if s["tokens_history"] > s["tokens_slowave"]),
            None,
        )
        if save_vs_history > 0 and quality_pct >= 70.0:
            verdict = "CONFIRMED"
        elif save_vs_history > 0:
            verdict = "PARTIAL"
        else:
            verdict = "REFUTED"
        vd = ("Slowave %.0f%% token reduction vs history replay, %.0f%% quality."
              ) % (save_vs_history, quality_pct)

        return {
            "timestamp": datetime.now().isoformat(),
            "scenario": {
                "memories_ingested": len(MEMORIES),
                "sessions_simulated": len(SESSIONS),
                "token_estimation": "len(text) // 4  (GPT-style, +-15%)",
                "encoder": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (ONNX, 384-dim)",
                "static_doc_tokens": static_tokens,
            },
            "per_session": per_session,
            "aggregate": {
                "history_replay": {"avg": round(avg_h, 1), "min": min(h_list),
                                   "max": max(h_list), "total": sum(h_list),
                                   "tokens_per_session": h_list},
                "static_doc":     {"avg": round(avg_st, 1), "min": min(st_list),
                                   "max": max(st_list), "total": sum(st_list),
                                   "tokens_per_session": st_list},
                "slowave":        {"avg": round(avg_sw, 1), "min": min(sw_list),
                                   "max": max(sw_list), "total": sum(sw_list),
                                   "tokens_per_session": sw_list},
            },
            "savings": {
                "vs_history_replay": {
                    "avg_reduction_pct": round(save_vs_history, 1),
                    "total_reduction_pct": round(100.0 * (1 - sum(sw_list) / sum(h_list)), 1),
                },
                "vs_static_doc": {
                    "avg_reduction_pct": round(save_vs_static, 1),
                    "total_reduction_pct": round(100.0 * (1 - sum(sw_list) / sum(st_list)), 1),
                },
            },
            "quality": {
                "sessions_checked": len(SESSIONS),
                "keyword_hits": hits,
                "hit_rate_pct": round(quality_pct, 1),
                "note": "Quality = expected keyword present in context_brief() output.",
            },
            "crossover_session": crossover,
            "verdict": verdict,
            "verdict_detail": vd,
            "caveats": [
                "Token counts approximated (len//4, +-15%). Use tiktoken for exact counts.",
                "Quality metric is keyword presence, not LLM-judge semantic correctness.",
                "Synthetic scenario -- real conversation verbosity will vary.",
                "History replay grows linearly; at 20 sessions it is a meaningful comparison.",
                "Static doc generated from same memories -- real docs (CLAUDE.md) vary.",
            ],
        }

    finally:
        engine.close()
        _cleanup(db_path)




# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------


def _print_results(r: dict[str, Any]) -> None:
    h  = r["aggregate"]["history_replay"]
    st = r["aggregate"]["static_doc"]
    sw = r["aggregate"]["slowave"]
    q  = r["quality"]
    sv = r["savings"]
    sc = r["scenario"]
    W  = 70

    print()
    print("=" * W)
    print("  SLOWAVE TOKEN EFFICIENCY BENCHMARK")
    print("  " + str(sc["memories_ingested"]) + " memories x "
          + str(sc["sessions_simulated"]) + " sessions x real semantic encoder")
    print("=" * W)
    print()
    print("  " + "Metric".ljust(30) + "History Replay".rjust(15)
          + "Static Doc".rjust(11) + "Slowave".rjust(9))
    print("  " + "-" * 65)
    print("  " + "Avg tokens / session".ljust(30)
          + str(int(h["avg"])).rjust(15) + str(int(st["avg"])).rjust(11) + str(int(sw["avg"])).rjust(9))
    print("  " + "Min tokens / session".ljust(30)
          + str(h["min"]).rjust(15) + str(st["min"]).rjust(11) + str(sw["min"]).rjust(9))
    print("  " + "Max tokens / session".ljust(30)
          + str(h["max"]).rjust(15) + str(st["max"]).rjust(11) + str(sw["max"]).rjust(9))
    print("  " + "Total (all sessions)".ljust(30)
          + str(h["total"]).rjust(15) + str(st["total"]).rjust(11) + str(sw["total"]).rjust(9))

    hrp = sv["vs_history_replay"]
    sdp = sv["vs_static_doc"]
    print()
    print("  Savings vs history replay :  "
          + ("%.1f" % hrp["avg_reduction_pct"]) + "% avg  ("
          + ("%.1f" % hrp["total_reduction_pct"]) + "% total)")
    print("  Savings vs static doc     :  "
          + ("%.1f" % sdp["avg_reduction_pct"]) + "% avg  ("
          + ("%.1f" % sdp["total_reduction_pct"]) + "% total)")

    xover = r["crossover_session"]
    print()
    if xover:
        print("  Crossover: Slowave < History Replay from session " + str(xover) + " onward.")
    else:
        print("  No crossover -- Slowave was never cheaper than history replay.")

    print()
    print("  Recall quality: "
          + str(q["keyword_hits"]) + "/" + str(q["sessions_checked"])
          + " sessions contained the expected memory  ("
          + ("%.0f" % q["hit_rate_pct"]) + "% hit rate)")

    sep = "-" * W
    print()
    print("  " + sep)
    print("  VERDICT: " + r["verdict"])
    print("  " + r["verdict_detail"])
    print("  " + sep)

    print()
    print("  Per-session detail:")
    print("  " + "#".ljust(4) + "History".rjust(8) + "Static".rjust(8)
          + "Slowave".rjust(8) + "  " + "Hit".rjust(4) + "  Query")
    print("  " + "-" * 4 + "-" * 8 + "-" * 8 + "-" * 8 + "  " + "-" * 4 + "  " + "-" * 44)
    for s in r["per_session"]:
        hit = "OK" if s["quality_hit"] else "MISS"
        print("  " + str(s["session"]).ljust(4)
              + str(s["tokens_history"]).rjust(8)
              + str(s["tokens_static"]).rjust(8)
              + str(s["tokens_slowave"]).rjust(8)
              + "  " + hit.rjust(4)
              + "  " + s["query"][:44])

    print()
    print("  Caveats:")
    for c in r["caveats"]:
        print("    * " + c)
    print()


# --------------------------------------------------------------------------
# Pytest entry point
# --------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.requires_faiss
def test_token_efficiency() -> None:
    """Benchmark Slowave token efficiency vs history replay and static doc."""
    results = run_token_efficiency_test()

    out_path = Path(__file__).parent.parent / "data" / "token_efficiency" / "results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    _print_results(results)
    print("  Full results -> " + str(out_path))
    print()

    verdict = results["verdict"]
    quality = results["quality"]["hit_rate_pct"]
    savings = results["savings"]["vs_history_replay"]["avg_reduction_pct"]

    assert verdict in ("CONFIRMED", "PARTIAL"), (
        "\nVERDICT: " + verdict + "\n" + results["verdict_detail"] + "\n"
        + "Quality: %.0f%%   Savings vs history: %+.1f%%" % (quality, savings)
    )
    assert quality >= 60.0, (
        "Recall quality too low: %.0f%% (threshold 60%%). " % quality
        + "Slowave is not surfacing relevant memories."
    )


# --------------------------------------------------------------------------
# Standalone run
# --------------------------------------------------------------------------

if __name__ == "__main__":
    results = run_token_efficiency_test()
    _print_results(results)
    out_path = Path(__file__).parent.parent / "data" / "token_efficiency" / "results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print("  Full results -> " + str(out_path))
    print()
    sys.exit(0 if results["verdict"] in ("CONFIRMED", "PARTIAL") else 1)

