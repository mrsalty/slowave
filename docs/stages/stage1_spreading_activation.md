# Stage 1: spreading activation in `RetrievalPipeline`

Branch: `feat/spreading-activation`

## What changed

Three retrieval-side changes, all behind `RetrievalConfig` flags so they
ablate cleanly:

1. **Spreading activation** (`RetrievalPipeline._spread`). Query cosine
   seeds a sparse activation pattern over the prototype graph; iterative
   propagation along `prototype_edges` weights for `spread_steps`
   iterations gives every prototype a final activation; graph-harvested
   episodes are scored by parent-prototype activation * salience.

2. **Reverse lookup** (`SemanticStore.episodes_for_prototypes`). New
   helper to fetch episodes for a set of activated prototypes — the
   reverse of the existing `prototype_for_episode`.

3. **Diversity-by-prototype** (`RetrievalConfig.diversity_per_prototype`).
   After the final ranker, no single prototype may occupy more than
   `diversity_per_prototype` of the head slots. Forces graph-harvested
   episodes from other prototypes to surface above same-prototype
   cosine-duplicates that would otherwise saturate the top-k.

Plus a small safety fix: recall reinforcement now applies **only** to
cosine-direct episodes, not graph-harvested ones. This prevents a
graph-feeds-itself feedback loop.

Default config (active on `use_spreading=True`):

```
spread_steps             = 2
spread_decay             = 0.5
spread_activation_floor  = 1e-3
episodes_per_prototype   = 6
spread_episode_weight    = 0.5
salience_gate            = True
diversity_per_prototype  = 2

## Results — internal scenario harness

| Family | Stage 0 (cosine-only) | Stage 1 (spreading on) | Δ |
|---|---|---|---|
| decay | 3/3 | 2/3 | **−1** (D-3) |
| reinforcement | 2/2 | 2/2 | 0 |
| coactivation | 2/2 | 2/2 | 0 |
| chain | 1/2 | 1/2 | 0 |
| completion | 1/4 | **2/4** | **+1** (PC-2) |
| **TOTAL** | **9/13** | **9/13** | 0 |

`no_graph` baseline returns to 9/13 (= Stage 0) — confirms the lift on
PC-2 comes from spreading, not from incidental cosine reordering.

### What moved

* **PC-2 (Stratus / RAM cross-session)** — a real win. The config detail
  ("16 GB JVM") and the entity ("Stratus") were injected in different
  sessions; pure FAISS retrieves only the config-side episodes;
  spreading activation pulls the entity-side episodes in via the
  prototype graph. This is the first scenario in the harness that
  genuinely requires a brain-inspired mechanism to solve.

### What did not move (and why)

* **D-3 (BrainCo recency)** regressed. The three job-fact episodes
  cluster into the same prototype during replay. The graph activates
  *all* episodes in that cluster uniformly, and salience inside the
  cluster favours the older Acme episode because the novelty-salience
  signal at insertion time is low for repeated job concepts. Fix
  requires per-class decay (Stage 4), not retrieval tuning.

* **PR-1, PR-2 (predictive completion)** still miss. They require the
  transition model to be queried *at recall time* — currently
  `TransitionModel.predict` is only used at encode time for novelty
  surprise. Stage 3.

* **CH-1 (2-hop chain)** still misses. Edge weights are dominated by

## Results — LoCoMo conv-26 (1 conversation, 199 questions)

Three runs on the same conversation:

| Run | Mode | Total | Temporal | F1 |
|---|---|---|---|---|
| `stage0_branch_smoke_1conv.json` | no_llm, no replay | 64.3% | 5.4% | 0.597 |
| `stage1_branch_smoke_1conv.json` | no_llm, no replay (Stage 1 code) | 64.3% | 5.4% | 0.597 |
| `stage1_replay_only_1conv.json` | no_llm, **replay on**, spreading on | 64.3% | 5.4% | 0.597 |

**Spreading activation contributes zero on LoCoMo.** Root cause measured
directly on conv-26:

```
episodes:    419
prototypes:    1       ← all episodes collapse into a single cluster
edges:         0       ← no graph for spreading to traverse
```

The replay engine's online k-means with `assignment_threshold=0.65`
collapses an entire LoCoMo conversation into one prototype. With one
prototype there is no graph to spread over; retrieval necessarily falls
back to cosine-only behaviour. This is the next architectural bottleneck
and it is upstream of Stage 1 — not something Stage 1 can fix.

## Conclusion

Stage 1 ships behind ablation flags. It produces:

* A clean, working spreading-activation pipeline with merge / diversity
  / no-feedback-loop properties that survive contact with scenarios.
* A confirmed genuine win on PC-2 (pattern completion that cosine
  cannot do).
* A confirmed regression (D-3) that pinpoints a real interaction with
  novelty-salience worth fixing in Stage 4 (per-class decay).
* A confirmed null result on LoCoMo with root cause identified
  (degenerate prototype clustering, 1 prototype across 419 episodes).

The honest takeaway: spreading activation works as designed, but its
useful range is gated by (a) prototype clustering quality and (b) the
transition model not participating at recall. **The next investment with
the highest expected impact on a public benchmark is fixing prototype
granularity** — almost certainly via tighter `assignment_threshold` or a
proper k-means split-and-merge replay step, not via more retrieval-side
work.

## Files changed

```
slowave/latent/retrieval.py                    rewritten — RetrievalPipeline + RetrievalConfig
slowave/latent/semantic_store.py               + episodes_for_prototypes()
tests/temporal_eval/harness.py                  no_graph ablation also turns off spreading
tests/integration/locomo_eval.py                + --replay-only flag for clean Stage-N ablation
docs/stages/stage1_spreading_activation.md                this file
data/temporal_eval_stage1_no_llm.json           internal harness numbers
data/locomo/runs/stage1_*.json                  LoCoMo measurements
```

  centroid `w_similarity`; the coactivation channel is too weak to
  bridge without LLM-built schemas. Stage 2.

```
