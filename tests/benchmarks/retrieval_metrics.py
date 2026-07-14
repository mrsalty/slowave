"""Shared Recall@K / MRR computation for the keyword-overlap benchmark scripts.

Recall@K reflects an actual `recall(top_k=K)` call, not a client-side slice of
a larger call: Slowave's retrieval pipeline scales its embedding/FTS candidate
pool with `top_k` and deduplicates episodes at depth `top_k`, so results at
K=10 are not a strict prefix of results at K=50 (schemas.reinforce() is also
called on every returned schema, which is a second reason not to derive
smaller-K results from a single larger call after the fact).
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

RECALL_KS: tuple[int, ...] = (5, 10, 20, 50)


def _concat_context(schemas: Sequence[Any], episode_texts: Sequence[dict]) -> str:
    sh = " ".join(s.content_text for s in schemas)
    eh = " ".join(ep["content_text"] for ep in episode_texts if ep.get("content_text"))
    return (sh + " " + eh).strip()


def _reciprocal_rank(
    schemas: Sequence[Any],
    episode_texts: Sequence[dict],
    answer: str,
    keyword_score_fn: Callable[[str, str], float],
    hit_threshold: float,
) -> float:
    """Smallest item-prefix (schemas then episodes, existing rank order) that clears the threshold."""
    items = [s.content_text for s in schemas] + [
        ep["content_text"] for ep in episode_texts if ep.get("content_text")
    ]
    acc = ""
    for rank, text in enumerate(items, start=1):
        acc = (acc + " " + text).strip()
        if keyword_score_fn(acc, answer) >= hit_threshold:
            return 1.0 / rank
    return 0.0


def compute_recall_at_k_and_mrr(
    eng: Any,
    query: str,
    answer: str,
    *,
    keyword_score_fn: Callable[[str, str], float],
    hit_threshold: float,
    ks: tuple[int, ...] = RECALL_KS,
    recall_kwargs: dict | None = None,
) -> tuple[dict[str, bool], float]:
    """Return (recall_at_k, mrr_contribution) for one question.

    Calls `eng.recall(query, top_k=K)` once per K, largest first, so the
    biggest/most-comprehensive call runs before recall()'s salience
    reinforcement side effect can bias it. MRR is derived from the
    largest-K call's own ranking (schemas then episodes) rather than a
    separate call, since that's the one call guaranteed to already exist.

    Only the first (largest-K) call refreshes the in-memory FAISS indices
    from SQLite (`recall(refresh=True)`, the default) — that's an O(N)
    full-table rebuild, and nothing is ingested between these back-to-back
    probes of the same question, so the remaining calls pass `refresh=False`
    to skip the redundant rebuild. Callers already do their own recall()
    right before invoking this helper, so in practice even the first call
    here is re-syncing against state that hasn't changed — but keeping one
    "real" refresh makes this helper correct standalone, not dependent on
    caller behavior.
    """
    recall_kwargs = recall_kwargs or {}
    recall_at_k: dict[str, bool] = {}
    mrr_contribution = 0.0
    for i, k in enumerate(sorted(ks, reverse=True)):
        r = eng.recall(query, top_k=k, refresh=(i == 0), **recall_kwargs)
        hyp = _concat_context(r.schemas, r.episode_texts)
        recall_at_k[str(k)] = keyword_score_fn(hyp, answer) >= hit_threshold
        if i == 0:
            mrr_contribution = _reciprocal_rank(
                r.schemas, r.episode_texts, answer, keyword_score_fn, hit_threshold
            )
    return recall_at_k, mrr_contribution


def aggregate_recall_at_k_mrr(
    rows: list[dict[str, bool]],
    mrrs: list[float],
    ks: tuple[int, ...] = RECALL_KS,
) -> tuple[dict[str, float], float]:
    """Turn per-question recall_at_k dicts + mrr contributions into summary numbers."""
    n = len(rows)
    if n == 0:
        return {str(k): 0.0 for k in ks}, 0.0
    recall_pct = {}
    for k in ks:
        key = str(k)
        hits = sum(1 for row in rows if row.get(key))
        recall_pct[key] = round(100 * hits / n, 1)
    mrr = round(sum(mrrs) / len(mrrs), 4) if mrrs else 0.0
    return recall_pct, mrr
