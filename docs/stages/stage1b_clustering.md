# Stage 1b: prototype clustering and the cap on graph noise

Branch: `feat/spreading-activation`

Follow-up to `stage1_spreading_activation.md`. Stage 1 showed that
spreading activation works on a constructed scenario (PC-2) but
contributes zero on LoCoMo because the replay engine clustered all 419
episodes into one super-prototype. This document follows that thread to
its honest conclusion: **fixing the clustering does not, by itself,
make graph-based retrieval helpful on LoCoMo**. The architectural
mechanism needs a query-conditional gate that we do not yet have.

## What was tried

### 1. Prototype-granularity diagnostic

New `scripts/proto_threshold_sweep.py`. On LoCoMo conv-26:

```
threshold   prototypes  edges   largest cluster
   0.65            1       0      419 / 419   (degenerate — Stage-0 default)
   0.75            6      30      402 / 419   (still degenerate)
   0.85           55     701      144 / 419   (reasonable)
   0.90          128    1920       63 / 419   (saturates max_protos)
   0.95          128    1836       33 / 419
```

`0.65` produced no graph at all. `0.85` produces 55 prototypes with 701
edges — a real graph for spreading to traverse.

### 2. Defaults raised + CLI knob exposed

- `tests/temporal_eval/harness.py` and `tests/integration/locomo_eval.py`
  now default `assignment_threshold=0.85`, `sample_size=2048`,
  `max_prototypes_per_replay=128`.
- `locomo_eval.py` gains `--assignment-threshold` and `--max-prototypes`.

### 3. Spreading noise cap

After raising the threshold, **spreading actively hurt LoCoMo**:

```
threshold=0.85  no spread :  64.3%   F1 0.596
threshold=0.85  spread on :  54.3%   F1 0.514   ← −10pp vs cosine
threshold=0.92  spread on :  61.8%
threshold=0.95  spread on :  51.8%
```

To preserve the PC-2 win without breaking LoCoMo:

- `spread_episode_weight` dropped from `0.5` → `0.25`.
- New `spread_score_ceiling = 0.9` clamps every graph-harvested score
  to `0.9 * worst_cosine_top_k_score` so graph candidates fill gaps
  *below* cosine candidates, never displace them.
- Diversity-by-prototype cap now exempts cosine-direct episodes.


## Net result

With caps in place LoCoMo conv-26 = **59.8%** — better than uncapped
spread (54.3%) but still **−4.5pp below cosine baseline** (64.3%). And
the cap *blocks the very lift Stage 1 produced* — PC-2 regresses back
to a miss on the internal harness.

| Bench | Stage 0 | Stage 1 (uncapped) | Stage 1b (cap + threshold) |
|---|---|---|---|
| Internal scenarios | 9/13 | 9/13 (PC-2 +, D-3 −) | 9/13 (D-3 +, PC-2 −) |
| LoCoMo conv-26 | 64.3% | 64.3% (no graph at t=0.65) | 59.8% (real graph + cap) |

No setting of these two knobs helps both benchmarks simultaneously.

## Why

LoCoMo conversational data has near-uniform embedding similarity:
every prototype is moderately related to every other prototype. Once
the graph carries real edges, spreading propagates activation almost
everywhere, and harvested episodes are not more relevant than the
cosine candidates they would displace.

PC-2 has the opposite property: the cue cosine-matches one cluster but
the answer lives in a *semantically orthogonal* cluster reachable only
through a coactivation edge. There, spreading does precisely the right
thing.

**The mechanism does not currently know which kind of situation it is
in.** Capped spreading is safe but useless on LoCoMo; uncapped
spreading is helpful on PC-2 but actively harmful on LoCoMo.

## What would actually unlock this

1. **Query-conditional activation gate.** Spread only if the cosine
   top-k is dominated by a single prototype (i.e. "I have one strong
   match"); otherwise stay cosine-only. Cheap to try.

2. **Schemas as priors (Stage 2 of the original roadmap).** Schemas
   are the only mechanism that can encode "X is the *kind* of thing
   the user is asking about" and bias propagation without dragging in
   every adjacent prototype.

3. **Replay-as-self-supervised-retrieval (Stage 5).** Generate
   synthetic queries from prototypes during sleep, observe what
   spreading does, and *learn* the propagation policy that recovers
   source episodes. The brain mechanism that actually closes the loop.

## Recommendation

Spreading stays in the code, ablation-toggleable
(`RetrievalConfig.use_spreading=False` reverts cleanly). Defaults are
conservative so the pipeline does not regress on LoCoMo. Both the
internal and public benchmark confirm: the architectural lift from
clustering + spreading alone is zero or negative on the benchmarks we
have.

**Stage 2 (schemas as priors) is the right next step.** It targets the
exact failure mode here — graph-blind propagation activating
everything — by giving spread a content-aware prior.

## Files changed

```
slowave/latent/retrieval.py             spread_score_ceiling + cosine-exempt diversity cap
scripts/proto_threshold_sweep.py         new diagnostic
tests/integration/locomo_eval.py         --assignment-threshold, --max-prototypes
tests/temporal_eval/harness.py           default threshold 0.85
docs/stages/stage1b_clustering.md    this file
data/temporal_eval_stage1_t0.85_capped_no_llm.json
data/locomo/runs/stage1_replay_t0.85_*.json
```
