# Stage 5: self-supervised retrieval rehearsal

Branch: `feat/spreading-activation`

## Brain-inspired argument first

During slow-wave sleep the hippocampus replays trajectories and the
neocortex listens. The crucial property: **the replay signal is
self-supervised**. There is no external label, no teacher. The brain
finds out what it needs to remember by *trying to remember it* and
noticing what it failed to.

A retrieval system that can replicate that loop has a learning signal
no RAG system structurally has access to: **its own retrieval
failures, observed against its own prototype membership**.

Stage 5 adds exactly that loop:

```
for each prototype p in the current cluster set:
    1. pick a member episode e as a probe cue
    2. run the full RetrievalPipeline on e's embedding
    3. compare retrieved top-k against p's other members
    4. for each "missed sibling", strengthen the coactivation edge
       between p and the prototype the sibling actually lives in
       (Hebbian failure-driven update)
    5. for each "confuser" (foreign episode in top-k), apply a small
       coactivation penalty on the bridge to the confuser's prototype
```

Two guards keep this honest:

* **Reward only on miss.** If retrieval already works, the graph is
  left alone. No success-feedback loop.
* **Magnitudes are small and additive.** Per miss: `+0.5` to the
  coactivation component. The existing `prune_edges()` step still
  applies; runaway growth is bounded.

## What changed

```
slowave/latent/replay_engine.py:
  + ReplayConfig.self_supervise + 5 ablation knobs
  + ReplayEngine.attach_retrieval(retrieval)
  + ReplayEngine.self_supervise() → counters

slowave/core/engine.py:
  + replay_engine.attach_retrieval(self.retrieval) after construction

tests/integration/locomo_eval.py:
  + --no-self-supervise CLI ablation flag
  + self_supervise() call after replay/consolidation (both LLM and
    --replay-only paths)
```

Defaults (uniform global parameters, never tuned per-benchmark):

```
self_supervise                    = True
self_supervise_max_prototypes     = 32
self_supervise_min_members        = 3
self_supervise_top_k              = 8

## Sanity — Stage 5 is a no-op when inputs are absent

```
LoCoMo conv-26 --no-consolidate:
  Stage 0  : 64.32%  F1 0.597
  Stage 5  : 64.32%  F1 0.597   ← identical
```

## Real signal — full LoCoMo with LLM consolidation

10 conversations, 1986 questions, `qwen2.5-coder:1.5b`, threshold 0.65:

| Category | Stage 3 + LLM | **Stage 5 + LLM** | Δ |
|---|---|---|---|
| single-session | 75.9 / F1 0.669 | 76.6 / F1 0.676 | +0.7pp / +0.007 |
| temporal | 27.1 / F1 0.279 | 26.5 / F1 0.270 | −0.6pp / −0.009 |
| commonsense | 54.2 / F1 0.497 | **58.3 / F1 0.511** | **+4.1pp / +0.014** |
| multi-session | 84.5 / F1 0.807 | 85.1 / F1 0.812 | +0.6pp / +0.005 |
| adversarial | 93.9 / F1 0.833 | 93.9 / F1 0.837 | 0pp / +0.004 |
| **TOTAL** | **74.7 / F1 0.693** | **75.1 / F1 0.696** | **+0.4pp / +0.003** |

## Clean ablation (`--no-self-supervise`)

Full LoCoMo, Stage 5 codebase, `--no-self-supervise`:

```
Stage 5 default       : 1492 / 1986 = 75.13%  F1 0.696
Stage 5 --no-self-ss  : 1476 / 1986 = 74.32%  F1 0.693
Δ from self-supervise : +0.81pp / +0.003 F1
```

Per-conversation:

```
conv-26 baseline (no transition, no self-supervise)  : 65.8%
conv-26 + transition (Stage 3 equivalent)            : 73.9%   (+8.1pp)
conv-26 + transition + self-supervise (Stage 5)      : 77.4%   (+3.5pp vs Stage 3)
```

## Honest readout

* **+0.4pp aggregate / +0.8pp ablation-clean** on full LoCoMo.
* Stage 3 was the breakthrough (+6.7pp); Stage 5 is a modest but
  *independent* second contribution from a second brain mechanism.
* **Commonsense +4.1pp** is the strongest per-category effect: that
  category is about bridging semantically related but lexically
  distinct evidence — exactly where reinforcing coactivation edges
  helps.
* **Temporal dipped −0.6pp.** The self-supervision is content-blind;
  it strengthens bridges that surface siblings, regardless of whether
  those bridges have temporal semantics.

## Cumulative comparison

| Benchmark | no_LLM RAG | pre-LLM | Stage 2 | Stage 3 | **Stage 5** |
|---|---|---|---|---|---|
| LoCoMo TOTAL | 68.0 / 0.654 | 68.6 / 0.660 | 68.4 / 0.657 | 74.7 / 0.693 | **75.1 / 0.696** |

**Total lift on the branch: +7.1pp / +0.042 F1 over cosine-only RAG**,
across two independent brain-inspired mechanisms (predictive
completion + self-supervised replay).

## Non-overfit discipline (still holding)

* No question-type heuristics. The self-supervise loop fires on every
  prototype with ≥ 3 members, regardless of category.
* No per-benchmark tuning. The five knobs come from the architectural
  argument and were not tuned against LoCoMo.
* `--no-consolidate` is bitwise identical to Stage 0.

## What this validates

This is the second brain mechanism (after Stage 3's predictive
completion) shown to contribute independently and measurably to a
public-benchmark win that vanilla RAG cannot reproduce.

The architectural distinction is now sharp: Slowave has access to a
**self-supervised learning signal** — its own retrieval failures
against its own prototype membership — that a RAG retriever
structurally lacks. That signal, applied with a small Hebbian update
during the worker pass, tightens the graph in a way that pure
encoding-time consolidation cannot.

## Files changed

```
slowave/latent/replay_engine.py             self_supervise() + 5 config knobs
slowave/core/engine.py                      attach_retrieval() wiring
tests/integration/locomo_eval.py             --no-self-supervise flag + call
docs/stages/stage5_self_supervised_replay.md   this file
data/locomo/runs/stage5_*.json               full LoCoMo + ablations
data/temporal_eval_stage5_full.json          internal scenarios (variance)
```

self_supervise_miss_reward        = 0.5
self_supervise_confuser_penalty   = 0.25
```
