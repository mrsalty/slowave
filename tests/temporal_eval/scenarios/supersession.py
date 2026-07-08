"""Family 4 — Knowledge update / schema supersession scenarios.

These test whether outdated facts are correctly superseded when a new
contradicting claim is consolidated. Requires LLM consolidation.
Pure episode retrieval cannot suppress old facts; the contradiction judge
and schema status system are needed.
"""

from __future__ import annotations

from tests.temporal_eval.harness import ScenarioResult, TemporalHarness, keyword_hit


def run_all(h: TemporalHarness) -> list[ScenarioResult]:
    results = []

    # ------------------------------------------------------------------ S-1
    # Database preference: Postgres -> SQLite
    h.session(
        [
            ("user", "I use Postgres for all my projects, it is my go-to database."),
            ("assistant", "Postgres is a great choice for reliable relational storage."),
        ]
    )  # LLM consolidates: "user uses Postgres"
    h.advance(14)
    h.session(
        [
            ("user", "I have switched to SQLite now for everything, much simpler."),
            ("assistant", "SQLite is great for lighter workloads. Good choice."),
        ]
    )  # LLM should supersede Postgres schema
    h.advance(1)
    result = h.query("What database does the user use?", top_k=5)
    schema_text = " ".join(s.content_text for s in result.schemas)
    episode_text = " ".join(ep["content_text"] for ep in result.episode_texts)
    hyp = (schema_text + " " + episode_text).strip()
    # Correct: SQLite mentioned, Postgres either absent or marked superseded
    hit = keyword_hit(hyp[:300], "SQLite")
    postgres_in_active_schemas = any(
        "Postgres" in s.content_text and s.status == "active" for s in h.eng.schemas.list(limit=100)
    )
    results.append(
        ScenarioResult(
            scenario_id="S-1",
            description="Day 0: uses Postgres. Day 14: switched to SQLite. "
            "Query on day 15: should return SQLite, Postgres should be superseded.",
            component="supersession",
            expected_keyword="SQLite",
            hypothesis=hyp[:400],
            hit=hit,
            detail={
                "n_schemas": h.n_schemas(),
                "postgres_still_active": postgres_in_active_schemas,
                "schema_text": schema_text[:300],
            },
        )
    )

    # ------------------------------------------------------------------ S-2
    # City of residence update with real time gap.
    h.session(
        [
            ("user", "I live in Berlin, been here for three years."),
            ("assistant", "Berlin is a wonderful city to live in."),
        ]
    )
    h.advance(21)  # 3 weeks
    h.session(
        [
            ("user", "I relocated to Amsterdam last week, it is my new home now."),
            ("assistant", "Amsterdam is a great city! Welcome."),
        ]
    )
    h.advance(1)
    result = h.query("Where does the user live?", top_k=5)
    schema_text = " ".join(s.content_text for s in result.schemas)
    episode_text = " ".join(ep["content_text"] for ep in result.episode_texts)
    hyp = (schema_text + " " + episode_text).strip()
    hit = keyword_hit(hyp[:300], "Amsterdam")
    berlin_active = any(
        "Berlin" in s.content_text and s.status == "active" for s in h.eng.schemas.list(limit=100)
    )
    results.append(
        ScenarioResult(
            scenario_id="S-2",
            description="Day 0: lives in Berlin. Day 21: moved to Amsterdam. "
            "Query on day 22: should return Amsterdam, Berlin should be superseded.",
            component="supersession",
            expected_keyword="Amsterdam",
            hypothesis=hyp[:400],
            hit=hit,
            detail={
                "n_schemas": h.n_schemas(),
                "berlin_still_active": berlin_active,
                "schema_text": schema_text[:300],
            },
        )
    )

    return results
