# Stage 8 results: pattern separation, neutral

## Headline

```
Cosine (no LLM)                 60.00%   (300/500)   153s
Stage 3+5 latent                66.40%   (332/500)   161s   +6.40pp
Stage 6 latent schemas          70.00%   (350/500)   168s   +3.60pp
Stage 7 + temporal              69.80%   (349/500)   126s   -0.20pp
Stage 8 + pattern separation    69.80%   (349/500)   128s    0.00pp  ←
```

**Stage 8 lands exactly on Stage 7's score, with every per-category
number identical. The mechanism fires but does not move any question
across the hit threshold on this benchmark.**

## What we built

`slowave/latent/replay_engine.py` — dentate-gyrus-style competitive
assignment. When an episode is being assigned to its closest existing
prototype, the assignment score becomes:

```
effective_sim = cos(e, winner) - dg_separation_lambda * cos(e, runner_up)
```

The episode is only joined to the winner if `effective_sim >=
assignment_threshold`. Otherwise a new prototype is created.

Defaults:
* `use_pattern_separation = True`
* `dg_separation_lambda = 0.5`
* `dg_min_prototypes = 3` (skip the rule when there are too few
  prototypes to have meaningful competition; mirrors developmental DG)

## Why it didn't help on LongMemEval

The mechanism is sound:
* `λ = 0.5` is the architecturally neutral choice: an episode that's
  equally similar to two prototypes (sim_w == sim_r) gets its score
  halved, which usually pushes it below threshold and triggers
  creation of a new prototype.
* In the existing Stage 6 codebase, with `assignment_threshold=0.65`
  and LongMemEval's diverse haystacks, runner-up similarities are
  typically 0.10-0.30 (sessions are about different topics). The
  penalty `0.5 * runner_up` is 0.05-0.15 — not enough to cross the
  threshold for most assignments.
* Diagnostic: avg schemas-returned-per-query is 1.98 (Stage 8) vs
  2.01 (Stage 7), within noise.

The brain-faithful scenario where DG separation matters most — two
similar but distinct memories about the same topic, separated in time
or context (e.g. "running routine, January" vs "running routine, June
after the injury") — does exist in LongMemEval's multi-session
category, but apparently not at a density that the default λ exposes.

## Two paths considered, one taken

**Option A — accept and move on (taken).** The mechanism is
architecturally faithful, costs nothing at runtime, and may help in
real-agent usage where similar topics accumulate over months.
Tuning λ upward to find a benchmark win would compromise the
non-overfit discipline that produced Stage 6's +10pp.

**Option B — bump λ to 0.8 or 1.0 (not taken).** Would likely create
more prototypes and might move a few questions. But picking a stronger
penalty *because* it produces a benchmark win is exactly the kind of
benchmark-tuned choice we've been refusing to make. Same call as Stage
7's "don't derive query temporal context from haystack median".

## What this validates

* The mechanism is implemented faithfully.
* On LongMemEval, with architecturally-chosen defaults, it is a
  no-op. The benchmark's haystacks do not expose the "borderline
  assignment" failure mode that DG separation solves.
* Stage 6 winning result (70.00%) is preserved within noise. The
  Stage 8 implementation is purely additive and does not regress
  any category.

## Honest pattern emerging

This is now two stages in a row (7, 8) that landed neutral. That's
information: it tells us where the remaining headroom on LongMemEval
*isn't*. Stage 7 (intrinsic temporal) and Stage 8 (pattern separation)
both target failure modes that the benchmark doesn't actually exercise:

* Stage 7 needs queries with implicit "now" anchoring — LongMemEval
  is historical, queries have no temporal context.
* Stage 8 needs sessions where the same topic recurs with subtle
  drift — LongMemEval has diverse-topic sessions where runner-up
  similarities are usually low.

The remaining headroom on LongMemEval (the -24.4pp gap to Mem0) is
overwhelmingly in single-session-preference (-73.6pp) and
single-session-assistant (-30.6pp). Neither is a retrieval-mechanism
problem; both are explicit-extraction problems. We chose not to chase
those — they would compromise the brain-only architectural claim.

## What's next

The pattern from Stages 7 and 8 suggests **Stage 9 (multi-scale
prototypes) is the most promising remaining stage on LongMemEval**.
It targets multi-session (where 60.90% has room) by giving the
retriever both fine-grained ("which exact session") and coarse-grained
("what pattern across sessions") views of the same episodes. This is
a *new type* of retrieval, not just a re-weighting of the existing
one, and it directly addresses the kind of question multi-session
asks.

If Stage 9 also lands neutral, the honest story is:
> Slowave Stage 6 at 70.00% / +10pp / zero LLM / 168 seconds is the
> ceiling brain-only mechanisms can reach on LongMemEval. The
> remaining gap to SOTA is structurally about explicit extraction
> (which the project deliberately avoids), not about retrieval
> quality.

That's a perfectly defensible position to land at.

## LoCoMo cross-validation: same neutral verdict on the benchmark that should reward it

LoCoMo is the benchmark where DG separation *should* most clearly help:
recurring characters, same topics across many sessions, persona drift
over time. We ran the comparison there too:

```
                              TOTAL    cat 1   cat 2   cat 3   cat 4   cat 5
                              KW%      single  temp    common  multi   adv
Stage 6 (no DG)               76.03    76.6    29.3    52.1    86.0    95.7
Stage 8 (+ DG)                75.58    75.5    27.1    57.3    85.1    96.4
                              -0.45pp  -1.1    -2.2    +5.2    -0.8    +0.7
```

**Net on LoCoMo: -0.45pp.** The per-category swings are real (the
mechanism is firing) but they cancel:

* **Helps commonsense (+5.2pp)** — slightly more prototypes give
  sharper persona traces. Consistent with the architectural intent.
* **Hurts temporal (-2.2pp), single-session (-1.1pp), multi-session
  (-0.8pp)** — likely the failure mode is that with more prototypes,
  the cosine top-k for a query has more candidates competing for the
  same slots, and the right answer occasionally loses to a similar
  competitor from another session. We don't have CA3 pattern
  completion strong enough to re-bind across the fragmentation that
  DG separation introduces.

This is stronger evidence than the LongMemEval neutral, because
LoCoMo's structure (recurring topics, persona drift) is *exactly*
what DG separation was designed for in the brain. If it doesn't help
here, it doesn't help on these benchmarks at all.

## Default flipped to OFF

Given two-public-benchmark evidence of net-neutral-to-negative, the
default is now `use_pattern_separation = False`. The mechanism stays
in the codebase (deployments where the structure favours it can
re-enable), but the project's default no longer includes Stage 8.

This is the honest engineering choice: a mechanism that adds zero
benchmark value at the architectural defaults should not be on by
default. Same call we would have made for any other feature.

## Status

```
Branch         : feat/spreading-activation
Stage 8 commit : (this commit)
Stage 8 net    : 0.00pp LongMemEval / -0.45pp LoCoMo
Stage 8 keep   : yes (in codebase), default OFF
Next           : honest pause — Stage 9/10 worth doing? See main next-stages doc
```
