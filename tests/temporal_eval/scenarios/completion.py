"""Family 6 — Pattern completion scenarios.

Hippocampal pattern completion: a partial cue activates a stored pattern
that the cue itself does not literally contain. Two variants tested here:

  PC-* : partial-detail completion (one salient attribute should
         retrieve an episode that does not mention the query's keywords).
  PR-* : predictive completion (the cue is the start of a recurring
         sequence; the answer is the typical continuation, which the
         transition model should provide once wired into recall).

Under the current FAISS-only retrieval these should largely miss; the
target is that they start passing once spreading activation and the
transition model are routed into the retrieval pipeline.
"""

from __future__ import annotations

from tests.temporal_eval.harness import ScenarioResult, TemporalHarness, keyword_hit


def run_all(h: TemporalHarness) -> list[ScenarioResult]:
    return _partial_cue(h) + _predictive(h)


def _partial_cue(h: TemporalHarness) -> list[ScenarioResult]:
    """Cue and target are introduced in DIFFERENT sessions so the micro/macro
    episode window cannot glue them together. Cosine on the query will only
    match one side; only graph coactivation can pull the other side in.
    """
    results: list[ScenarioResult] = []

    # PC-1: project name and visual identity introduced in separate sessions.
    # Sessions establishing the project name (no logo mention).
    for _ in range(3):
        h.session(
            [
                ("user", "Project Helios kicked off this quarter."),
                ("assistant", "Sounds exciting — what's the scope of Helios?"),
                ("user", "I'm leading the backend for Helios."),
            ],
            consolidate=False,
        )
        h.advance(1, replay=True)
    # Sessions establishing the visual identity (no project name).
    for _ in range(3):
        h.session(
            [
                ("user", "We finalised the visual identity — it's an orange logo."),
                ("assistant", "An orange logo is a strong, warm choice."),
            ],
            consolidate=False,
        )
        h.advance(1, replay=True)

    result = h.query("which project has the orange logo", top_k=8)
    hyp = " ".join(ep["content_text"] for ep in result.episode_texts)
    results.append(
        ScenarioResult(
            scenario_id="PC-1",
            description="Project name ('Helios') and visual identity ('orange logo') "
            "introduced in separate sessions. Cosine on 'orange logo' "
            "matches identity episodes only; graph coactivation must "
            "bridge to surface Helios.",
            component="completion",
            expected_keyword="Helios",
            hypothesis=hyp[:400],
            hit=keyword_hit(hyp, "Helios"),
            detail={"rag_should_miss": True},
        )
    )

    # PC-2: server entity and config decision in separate sessions.
    for _ in range(3):
        h.session(
            [
                ("user", "I provisioned the Stratus server today, it's online."),
                ("assistant", "Glad Stratus is up — anything blocking?"),
            ],
            consolidate=False,
        )
        h.advance(1, replay=True)
    for _ in range(3):
        h.session(
            [
                ("user", "Standard practice: allocate 16GB of RAM for the JVM."),
                ("assistant", "16GB is a reasonable heap size for that workload."),
            ],
            consolidate=False,
        )
        h.advance(1, replay=True)

    result = h.query("how much RAM do I usually give to the JVM", top_k=6)
    hyp = " ".join(ep["content_text"] for ep in result.episode_texts)
    results.append(
        ScenarioResult(
            scenario_id="PC-2",
            description="Config decision and server entity in separate sessions. "
            "Cosine on 'RAM JVM' matches config episodes; graph "
            "coactivation must surface 'Stratus'.",
            component="completion",
            expected_keyword="Stratus",
            hypothesis=hyp[:400],
            hit=keyword_hit(hyp, "Stratus"),
            detail={"rag_should_miss": True},
        )
    )

    return results


def _predictive(h: TemporalHarness) -> list[ScenarioResult]:
    """The sequence steps are split across SEPARATE sessions so the query
    cosine-matches only the cue step. Only a learned transition (replay
    builds proto_t -> proto_{t+1} edges) or the transition model called at
    recall time can surface the next step.
    """
    results: list[ScenarioResult] = []

    # PR-1: cue step ("standup") and continuation ("on-call review") in
    # separate sessions, but always in the SAME ORDER day-by-day so the
    # replay transition counter can learn the edge.
    for _ in range(5):
        h.session(
            [
                ("user", "Just finished the Monday standup, kicking off the day."),
                ("assistant", "Good — anything blocking the team?"),
            ],
            consolidate=False,
        )
        h.advance(0.01, replay=True)  # same day, ordered
        h.session(
            [
                ("user", "Reviewing the on-call queue as usual."),
                ("assistant", "Triaging on-call is a solid routine."),
            ],
            consolidate=False,
        )
        h.advance(7, replay=True)  # one week to next standup

    result = h.query("what do I usually do right after the Monday standup", top_k=8)
    hyp = " ".join(ep["content_text"] for ep in result.episode_texts)
    results.append(
        ScenarioResult(
            scenario_id="PR-1",
            description="Standup and on-call review in SEPARATE sessions, repeated "
            "5x in order. Cosine on 'after standup' matches standup "
            "episodes only; transition edges or model must surface "
            "the on-call continuation.",
            component="completion",
            expected_keyword="on-call",
            hypothesis=hyp[:400],
            hit=keyword_hit(hyp, "on-call") or keyword_hit(hyp, "on call"),
            detail={"rag_should_miss": True, "needs_transition_model": True},
        )
    )

    # PR-2: three-step routine (deploy -> smoke -> #releases) spread over
    # three sessions per cycle.
    for _ in range(4):
        h.session(
            [
                ("user", "Pushing the new release to production now."),
                ("assistant", "Roger, deploy in flight."),
            ],
            consolidate=False,
        )
        h.advance(0.01, replay=True)
        h.session(
            [
                ("user", "Deploy succeeded, kicking off the smoke tests."),
                ("assistant", "Watching the smoke test dashboard."),
            ],
            consolidate=False,
        )
        h.advance(0.01, replay=True)
        h.session(
            [
                ("user", "Smoke tests green, posting in #releases channel."),
                ("assistant", "Notification routine wrapped."),
            ],
            consolidate=False,
        )
        h.advance(3, replay=True)

    result = h.query("what comes right after the smoke tests pass", top_k=8)
    hyp = " ".join(ep["content_text"] for ep in result.episode_texts)
    notify = (
        keyword_hit(hyp, "#releases")
        or keyword_hit(hyp, "releases channel")
        or (keyword_hit(hyp, "post") and keyword_hit(hyp, "channel"))
    )
    results.append(
        ScenarioResult(
            scenario_id="PR-2",
            description="Predictive completion: after smoke tests, expected next "
            "step is posting in the #releases channel.",
            component="completion",
            expected_keyword="#releases",
            hypothesis=hyp[:400],
            hit=notify,
            detail={"rag_should_miss": False, "needs_transition_model": True},
        )
    )

    return results
