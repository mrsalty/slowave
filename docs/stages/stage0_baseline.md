# Stage 0 baseline for spreading-activation work

Branch: `feat/spreading-activation`

## Goal of Stage 0

Establish a benchmark that **can fail under cosine-only retrieval** so the
brain-inspired components actually have something to optimise against.
LongMemEval and LoCoMo have been shown to be insensitive to salience,
graph and replay, so the temporal-eval scenarios are extended in-place.

## What was added

Two new scenario families in `tests/temporal_eval/scenarios/`:

| Family | File | Tests |
|---|---|---|
| `chain` | `chain.py` | Multi-hop coactivation (2-hop CH-1, 3-hop CH-2). Cue and answer never co-occur in any session; only iterative graph propagation can bridge. |
| `completion` | `completion.py` | Pattern completion. `PC-*` split entity from attribute across sessions. `PR-*` split sequence steps across sessions in fixed order so only a learned transition can predict the next step. |

The runner `run_temporal_eval.py` now executes six families:
`decay, reinforcement, coactivation, chain, completion, supersession`.

## Stage 0 baseline (no_llm ablation, cosine-only retrieval)

```
Component       Hits   Notes
--------------  -----  -----------------------------------------
decay           3/3    Salience-floor + recency disambiguation
reinforcement   2/2    Recall reinforcement
coactivation    2/2    Single-hop; likely passes via cosine glue
chain           1/2    CH-1 fails honestly (2-hop bridge needed)
completion      1/4    PC-2, PR-1, PR-2 fail honestly
--------------  -----
TOTAL           9/13 = 69.2%
```

Raw run: `data/temporal_eval_stage0_baseline.json`.

The failing four scenarios — **CH-1, PC-2, PR-1, PR-2** — are the
discriminative set. Pure cosine cannot solve them because the query
cosine-matches only one side of the bridge and the answer-side
episodes contain none of the query terms.

`no_graph` returns identical numbers to `no_llm`, confirming the
diagnosis: the prototype graph is built but never consulted at recall.

## Targets after Stage 1 (spreading activation in RetrievalPipeline)

| Scenario | Stage 0 | Stage 1 target |
|---|---|---|
| CH-1 (knee↔plan↔marathon) | miss | hit (2-hop bridge) |
| CH-2 (3-hop) | hit | keep (or strengthen) |
| PC-1 | hit | keep |
| PC-2 (Stratus) | miss | hit (coactivation bridge) |
| PR-1 (standup→on-call) | miss | hit (transition edge surfaces continuation) |
| PR-2 (deploy→smoke→#releases) | miss | hit (multi-step transition) |

Stage 1 success criterion: score ≥ 12/13 *and* `no_graph` drops
back to ≤ 9/13, demonstrating that the lift comes from the graph
and not from incidental cosine.
