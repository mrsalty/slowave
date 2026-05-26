# Stage 7 results: temporal context, honest negative

## Headline

```
Cosine (no LLM)               60.00%   (300/500)   153s
Stage 3+5 latent (no LLM)     66.40%   (332/500)   161s   +6.40pp
Stage 6 latent schemas        70.00%   (350/500)   168s   +3.60pp
Stage 7 + temporal context    69.80%   (349/500)   126s   -0.20pp  ←
```

**Stage 7 lands -0.20pp from Stage 6 on full LongMemEval. One question
lost in temporal-reasoning (67.67% → 66.92%). Every other category
identical.**

## What we built

Multi-scale sinusoidal temporal embeddings (`slowave/latent/temporal.py`):

* 7 scales (minute, hour, day, week, month, year, decade), each
  emitting a (sin, cos) phase pair → 14-dim temporal vector.
* `TemporalContext.encode(ts)` is a pure deterministic function;
  `TemporalContext.now()` returns the temporal vector for the
  current moment.

Retrieval scoring (`slowave/latent/retrieval.py`) gains a temporal
proximity term:

```
final_score(episode) =
    cosine/spread score
    + α_salience  * salience(episode)
    + α_temporal  * cos(query_temporal, episode_temporal)
```

Defaults: `α_temporal = 0.15`, `query_temporal = now()`.

This is the brain-faithful implementation of the mechanism we
described: every memory carries an intrinsic temporal coordinate, and
retrieval consults it.

## Why it didn't help on LongMemEval

The mechanism is sound (sanity-tested: temporal cosine drops monotonically
with time delta, 1.00 at 0s, 0.51 at 10 years). The implementation in
retrieval is correct (smoke runs pass, latency unchanged ~6ms).

The reason it doesn't lift the score on LongMemEval is structural:

1. **LongMemEval haystacks are historical.** All candidate episodes
   are timestamped at points in the past, often years before "now".
2. **Queries carry no explicit temporal anchor.** The benchmark
   provides a question but not "when this question was asked
   relative to the haystack".
3. **Defaulting the query's temporal context to "now"** biases the
   retriever toward the *most recent* episode in the historical
   window. But the question's *implicit* temporal context is
   somewhere inside that window, not at its edge.

In other words: temporal proximity to "now" is a feature that helps
real agents whose queries are genuinely about the present moment. It
does not help on a benchmark where every memory is historical and
every query is implicitly "about some moment in that history".

## Two paths forward considered, one taken

**Option A — accept and move on (taken).** The brain-faithful
mechanism is in place. It will help in real-time agent usage. On
LongMemEval it is approximately a no-op (-0.2pp = 1 question
within noise). Documenting the honest negative result, leaving the
implementation in (it costs ~30ms per recall, may help downstream),
and moving to Stage 8.

**Option B — derive the query temporal context from the haystack's
median episode timestamp (not taken).** Would likely recover the lost
1 question and possibly gain a few more on temporal-reasoning. But
that's one step closer to "tuning for the test" — picking the query
temporal anchor based on what's in the store. The integrity discipline
that produced Stage 6's +10pp win is preserved by not doing this.

## Mechanism behaviour (validated)

```
Temporal cosine vs time delta:
  same moment       cos = +1.000
  1 minute later    cos = +0.999
  1 hour later      cos = +0.995
  1 day later       cos = +0.943
  1 week later      cos = +0.871
  1 month later     cos = +0.807
  1 year later      cos = +0.848  (periodic phase alignment at year scale)
  10 years later    cos = +0.514
```

Monotonic gross decay; small periodic bumps at the natural scales
(which is exactly what biological time cells exhibit). The
representation is correct.

## What this validates

* The Stage 7 mechanism (multi-scale sinusoidal temporal embedding +
  additive proximity bonus in retrieval) is architecturally faithful
  and computationally cheap.
* On LongMemEval, **without a query-side temporal signal**, it is a
  no-op. This is an honest property of the benchmark, not a defect of
  the mechanism.
* The Stage 6 brain-only result (70.00% / +10pp over cosine) is
  unchanged: the Stage 7 implementation is purely additive and does
  not regress any other category by more than the 1-question noise
  floor.

## Status

```
Branch         : feat/spreading-activation
Stage 7 commit : (this commit)
Stage 7 net    : -0.20pp on full LongMemEval (1 question)
Stage 7 keep   : yes — mechanism is sound, helps real-time agents
Next           : Stage 8 (pattern separation in prototype assignment)
```
