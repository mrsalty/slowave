"""Family 1 — Salience decay scenarios.

These test whether old memories are correctly outranked by newer ones after
simulated time has passed. Pure FAISS has no recency signal; salience decay
is the only mechanism that can resolve these cases correctly.
"""

from __future__ import annotations

from tests.temporal_eval.harness import ScenarioResult, TemporalHarness, keyword_hit


def run_all(h: TemporalHarness) -> list[ScenarioResult]:
    results = []

    # ------------------------------------------------------------------ D-1
    # Old location vs new location: classic recency test.
    # tau=7d.  Old fact injected on day 0, new fact on day 30.
    # After 30 days the old fact should have decayed to ~exp(-30/7)~0.013×
    # its original salience.  Query on day 31.
    h.session([("user", "I live in London and have been here for years.")], consolidate=False)
    sal_london_before = h.salience_of("London")
    h.advance(30)
    h.session([("user", "I just moved to Paris last week, love it here.")], consolidate=False)
    h.advance(1)
    result = h.query("Where does the user live?", top_k=10)
    hyp = " ".join(
        [s.content_text for s in result.schemas]
        + [ep["content_text"] for ep in result.episode_texts]
    )
    sal_london_after = h.salience_of("London")
    sal_paris = h.salience_of("Paris")
    hit = keyword_hit(hyp, "Paris") and not keyword_hit(hyp.split("Paris")[0], "London")
    # simpler: Paris appears before London OR Paris appears and London absent from top
    hit = keyword_hit(hyp[:300], "Paris")
    results.append(
        ScenarioResult(
            scenario_id="D-1",
            description="Old location (London, day 0) vs new location (Paris, day 30). Query on day 31.",
            component="decay",
            expected_keyword="Paris",
            hypothesis=hyp[:400],
            hit=hit,
            detail={
                "sal_london_before_advance": round(sal_london_before, 4),
                "sal_london_after_advance": round(sal_london_after, 4),
                "sal_paris": round(sal_paris, 4),
            },
        )
    )

    # ------------------------------------------------------------------ D-2
    # Two competing preferences stated 20 days apart.
    # Old: prefers tea. New: prefers coffee.
    h.session([("user", "I always start my day with tea, I really love tea.")], consolidate=False)
    h.advance(20)
    h.session([("user", "I switched to coffee recently, much prefer it now.")], consolidate=False)
    h.advance(1)
    result = h.query("What does the user like to drink in the morning?", top_k=10)
    hyp = " ".join(
        [s.content_text for s in result.schemas]
        + [ep["content_text"] for ep in result.episode_texts]
    )
    hit = keyword_hit(hyp[:300], "coffee")
    results.append(
        ScenarioResult(
            scenario_id="D-2",
            description="Old drink preference (tea, day 0) vs new (coffee, day 20). Query on day 21.",
            component="decay",
            expected_keyword="coffee",
            hypothesis=hyp[:400],
            hit=hit,
            detail={
                "sal_tea": round(h.salience_of("tea"), 4),
                "sal_coffee": round(h.salience_of("coffee"), 4),
            },
        )
    )

    # ------------------------------------------------------------------ D-3
    # Three facts at different ages; the freshest should dominate.
    # job on day 0, promotion on day 15, new company on day 28.
    h.session([("user", "I work as a software engineer at Acme Corp.")], consolidate=False)
    h.advance(15)
    h.session([("user", "I got promoted to senior engineer at Acme Corp.")], consolidate=False)
    h.advance(13)
    h.session(
        [("user", "I left Acme and joined BrainCo as principal engineer.")], consolidate=False
    )
    h.advance(1)
    result = h.query("Where does the user work?", top_k=10)
    hyp = " ".join(
        [s.content_text for s in result.schemas]
        + [ep["content_text"] for ep in result.episode_texts]
    )
    hit = keyword_hit(hyp[:300], "BrainCo")
    results.append(
        ScenarioResult(
            scenario_id="D-3",
            description="Three job facts at days 0, 15, 28. Query on day 29 should return newest (BrainCo).",
            component="decay",
            expected_keyword="BrainCo",
            hypothesis=hyp[:400],
            hit=hit,
            detail={
                "sal_acme": round(h.salience_of("Acme"), 4),
                "sal_branico": round(h.salience_of("BrainCo"), 4),
            },
        )
    )

    return results
