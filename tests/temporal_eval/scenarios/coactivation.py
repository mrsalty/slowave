"""Family 3 — Graph coactivation scenarios.

These test whether the prototype graph surface related memories via graph
expansion at recall time. Pure FAISS cannot do this; the query embedding
must semantically match the memory directly. Graph expansion allows
associated-but-not-directly-similar memories to be retrieved.
"""
from __future__ import annotations
from tests.temporal_eval.harness import ScenarioResult, TemporalHarness, keyword_hit


def run_all(h: TemporalHarness) -> list[ScenarioResult]:
    results = []

    # ------------------------------------------------------------------ C-1
    # Python and deployment are discussed together in many sessions.
    # SQLite and Python are discussed together too.
    # A query about deployment should surface Python AND SQLite via graph,
    # even though the query text does not mention Python or SQLite.
    for _ in range(5):
        h.session([
            ("user", "How do I deploy my Python application to production?"),
            ("assistant", "You can use Docker to containerize your Python app."),
        ], consolidate=False)
        h.advance(1, replay=True)

    for _ in range(4):
        h.session([
            ("user", "I use SQLite with my Python scripts for lightweight storage."),
            ("assistant", "SQLite is great for Python applications that need simple persistence."),
        ], consolidate=False)
        h.advance(1, replay=True)

    # Now query about deployment — should surface Python context via coactivation
    result = h.query("deployment production server", top_k=8)
    hyp = " ".join(ep["content_text"] for ep in result.episode_texts)
    # Graph expansion should have pulled in Python/SQLite neighbors
    has_python = keyword_hit(hyp, "Python")
    has_sqlite = keyword_hit(hyp, "SQLite")
    hit = has_python or has_sqlite
    results.append(ScenarioResult(
        scenario_id="C-1",
        description="Deployment + Python co-discussed 5x. SQLite + Python 4x. "
                    "Query 'deployment' should surface Python/SQLite via graph expansion.",
        component="coactivation",
        expected_keyword="Python",
        hypothesis=hyp[:400],
        hit=hit,
        detail={"has_python": has_python, "has_sqlite": has_sqlite},
    ))

    # ------------------------------------------------------------------ C-2
    # Health topics and sleep are repeatedly discussed together.
    # Productivity and sleep are also discussed together.
    # A query about productivity (no mention of sleep) should surface sleep
    # context via the graph.
    for _ in range(4):
        h.session([
            ("user", "I have been trying to improve my sleep schedule for my health."),
            ("assistant", "Good sleep is crucial for overall health and recovery."),
        ], consolidate=False)
        h.advance(1, replay=True)

    for _ in range(4):
        h.session([
            ("user", "Sleep quality really affects my productivity and focus at work."),
            ("assistant", "Yes, sleep and productivity are tightly linked."),
        ], consolidate=False)
        h.advance(1, replay=True)

    result = h.query("how to improve productivity and focus", top_k=8)
    hyp = " ".join(ep["content_text"] for ep in result.episode_texts)
    hit = keyword_hit(hyp, "sleep")
    results.append(ScenarioResult(
        scenario_id="C-2",
        description="Sleep+health co-discussed 4x. Sleep+productivity 4x. "
                    "Query 'productivity focus' should surface sleep via graph.",
        component="coactivation",
        expected_keyword="sleep",
        hypothesis=hyp[:400],
        hit=hit,
        detail={},
    ))

    return results
