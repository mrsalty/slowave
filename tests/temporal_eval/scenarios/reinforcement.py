"""Family 2 — Recall reinforcement scenarios.

These test whether memories that have been recalled repeatedly rank higher
than equally relevant but never-recalled memories. Pure FAISS cannot
distinguish them; reinforcement is the only mechanism that can.
"""
from __future__ import annotations
from tests.temporal_eval.harness import ScenarioResult, TemporalHarness, keyword_hit


def run_all(h: TemporalHarness) -> list[ScenarioResult]:
    results = []

    # ------------------------------------------------------------------ R-1
    # Two equally relevant memories injected on the same day.
    # Memory A is repeatedly retrieved on days 1-5.
    # Memory B is never retrieved.
    # On day 10, a query asking about topic A should rank A higher.
    h.session([("user", "I use PostgreSQL for all my backend projects.")], consolidate=False)
    h.session([("user", "I use Redis for caching in all my backend projects.")], consolidate=False)
    h.advance(1, replay=False)
    # Reinforce the Postgres memory by repeated retrieval
    h.reinforce("PostgreSQL database backend", n=5)
    h.advance(9)
    result = h.query("What database does the user use for backend projects?", top_k=6)
    hyp_texts = [ep["content_text"] for ep in result.episode_texts]
    # Postgres should appear before Redis in the ranked results
    hyp = " ".join(hyp_texts)
    postgres_rank = next((i for i, t in enumerate(hyp_texts) if "PostgreSQL" in t or "Postgres" in t), 999)
    redis_rank    = next((i for i, t in enumerate(hyp_texts) if "Redis" in t), 999)
    hit = postgres_rank < redis_rank
    sal_pg = h.salience_of("PostgreSQL")
    sal_rd = h.salience_of("Redis")
    results.append(ScenarioResult(
        scenario_id="R-1",
        description="PostgreSQL (recalled 5x) vs Redis (never recalled). PostgreSQL should rank higher.",
        component="reinforcement",
        expected_keyword="PostgreSQL",
        hypothesis=hyp[:400],
        hit=hit,
        detail={
            "postgres_rank": postgres_rank,
            "redis_rank": redis_rank,
            "sal_postgres": round(sal_pg, 4),
            "sal_redis":    round(sal_rd, 4),
        },
    ))

    # ------------------------------------------------------------------ R-2
    # Three memories of the same topic injected at the same time.
    # Memory X is recalled frequently. Y and Z are not.
    # After time passes, X should remain salient while Y and Z decay.
    h.session([("user", "For machine learning I use PyTorch, it is my primary framework.")], consolidate=False)
    h.session([("user", "I have also experimented with TensorFlow for some projects.")], consolidate=False)
    h.session([("user", "I tried JAX once but went back to PyTorch quickly.")], consolidate=False)
    h.advance(1, replay=False)
    # Reinforce PyTorch
    h.reinforce("PyTorch machine learning framework", n=4)
    h.advance(14)  # 2 weeks pass; TF and JAX decay more
    result = h.query("What ML framework does the user prefer?", top_k=6)
    hyp_texts = [ep["content_text"] for ep in result.episode_texts]
    hyp = " ".join(hyp_texts)
    pytorch_rank = next((i for i, t in enumerate(hyp_texts) if "PyTorch" in t), 999)
    tf_rank      = next((i for i, t in enumerate(hyp_texts) if "TensorFlow" in t), 999)
    hit = pytorch_rank < tf_rank
    results.append(ScenarioResult(
        scenario_id="R-2",
        description="PyTorch (recalled 4x) vs TensorFlow/JAX (not recalled). After 14 days PyTorch should rank first.",
        component="reinforcement",
        expected_keyword="PyTorch",
        hypothesis=hyp[:400],
        hit=hit,
        detail={
            "pytorch_rank": pytorch_rank,
            "tf_rank":      tf_rank,
            "sal_pytorch":  round(h.salience_of("PyTorch"), 4),
            "sal_tf":       round(h.salience_of("TensorFlow"), 4),
        },
    ))

    return results
