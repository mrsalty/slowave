"""Family 5 — Multi-hop coactivation chain scenarios.

These extend the single-hop coactivation tests with chains A↔B, B↔C
where A and C are never co-mentioned. A pure FAISS retriever cannot
bridge the gap because the query embedding only matches one end of
the chain. Only iterative spreading activation over the prototype
graph can complete the path A → B → C in two hops.

The point of these scenarios is to *fail* under the current
top-k-cosine retrieval and to start passing once
`RetrievalPipeline` performs multi-step graph propagation.
"""
from __future__ import annotations
from tests.temporal_eval.harness import ScenarioResult, TemporalHarness, keyword_hit


def run_all(h: TemporalHarness) -> list[ScenarioResult]:
    results = []

    # ------------------------------------------------------------------ CH-1
    # Two-hop chain: knee-injury ↔ running plan, running plan ↔ marathon.
    # Knee-injury and marathon are never mentioned together.
    # Query about marathon should surface the knee-injury constraint via the
    # intermediate "running plan" prototype.
    for _ in range(4):
        h.session([
            ("user", "Because of my knee injury I follow an adapted running plan."),
            ("assistant", "Adapted running plans are essential after knee injuries."),
        ], consolidate=False)
        h.advance(1, replay=True)

    for _ in range(4):
        h.session([
            ("user", "My running plan is geared toward finishing a marathon this autumn."),
            ("assistant", "A marathon-focused running plan should build mileage gradually."),
        ], consolidate=False)
        h.advance(1, replay=True)

    result = h.query("what should I keep in mind preparing for my marathon", top_k=8)
    hyp = " ".join(ep["content_text"] for ep in result.episode_texts)
    has_knee = keyword_hit(hyp, "knee")
    hit = has_knee
    results.append(ScenarioResult(
        scenario_id="CH-1",
        description="Chain: knee↔plan, plan↔marathon. Query 'marathon' should "
                    "surface the knee constraint via two-hop graph propagation.",
        component="chain",
        expected_keyword="knee",
        hypothesis=hyp[:400],
        hit=hit,
        detail={"has_knee": has_knee, "rag_should_miss": True},
    ))

    # ------------------------------------------------------------------ CH-2
    # Three-hop chain to make the test sharper:
    #   migraines ↔ caffeine, caffeine ↔ coffee, coffee ↔ Italy
    # Query "trip to Italy" should retrieve the migraine constraint via three
    # hops. A FAISS-only retriever has no chance; even single-hop graph
    # expansion is not enough.
    for _ in range(3):
        h.session([
            ("user", "When my migraines flare up, caffeine actually helps."),
            ("assistant", "Caffeine can constrict blood vessels and ease migraines."),
        ], consolidate=False)
        h.advance(1, replay=True)

    for _ in range(3):
        h.session([
            ("user", "Most of my caffeine intake comes from strong coffee."),
            ("assistant", "Coffee is a reliable source of caffeine for most people."),
        ], consolidate=False)
        h.advance(1, replay=True)

    for _ in range(3):
        h.session([
            ("user", "I'm planning a coffee tour in Italy next month."),
            ("assistant", "Italy has wonderful coffee culture, especially in the north."),
        ], consolidate=False)
        h.advance(1, replay=True)

    result = h.query("any health considerations for my Italy trip", top_k=10)
    hyp = " ".join(ep["content_text"] for ep in result.episode_texts)
    has_migraine = keyword_hit(hyp, "migraine")
    has_caffeine = keyword_hit(hyp, "caffeine")
    hit = has_migraine
    results.append(ScenarioResult(
        scenario_id="CH-2",
        description="Three-hop chain: migraine↔caffeine, caffeine↔coffee, "
                    "coffee↔Italy. Query 'Italy trip health' should surface migraines.",
        component="chain",
        expected_keyword="migraine",
        hypothesis=hyp[:400],
        hit=hit,
        detail={
            "has_migraine": has_migraine,
            "has_caffeine": has_caffeine,
            "rag_should_miss": True,
        },
    ))

    return results
