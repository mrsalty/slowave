# 07 — Temporal Context & Anchor Estimation

## Overview

Two independent mechanisms give recall a sense of time. **Multi-scale sinusoidal encoding** (Stage 7, `TemporalContext`) turns any Unix timestamp into a deterministic, unit-norm vector so that "closeness in time" becomes a plain cosine similarity — computed on demand from each episode's stored `ts`, not persisted as its own vector. **Temporal anchor estimation** (Stage 10, `TemporalProbe`) infers *which* moment a query is actually asking about — "now" by default, or a past instant implied by phrases like "last month" — using embedding-space similarity against a fixed set of probe phrases, with zero regex and zero extra LLM calls. The anchor feeds the Stage 7 encoder as the query side of the cosine comparison; the two mechanisms compose but can be enabled/measured independently.

## Data Flow

```
event.ts (01-ingestion.md)                             query text
      │                                                       │
      ▼                                                       ▼
EpisodicMemory.ts (stored, raw int, unchanged)      TextEncoder.encode(query) → q
      │                                                       │
      │                              ┌────────────────────────┴────────────────────────┐
      │                              ▼                                                  ▼
      │                 TemporalProbe.estimate_anchor(q)                    RetrievalPipeline.retrieve(q)
      │                 (Stage 10 — 12 pre-embedded probes,                  cosine / spread / predictive
      │                  12 dot products, no re-embedding)                   candidate pool assembly
      │                              │                                                  │
      │                              ▼                                                  │
      │                 anchor_ts  (= now_ts, or now_ts + Δ                              │
      │                    when a past probe wins the dead-zone gate)                    │
      │                              │                                                  │
      │                              └───────────────────┬──────────────────────────────┘
      │                                                  ▼
      │                       TemporalContext.encode(anchor_ts) → q_temporal   (Stage 7)
      │                                                  │
      └──────────────────────────────────────────────────▼
                       TemporalContext.encode_many(candidate.ts) → cos(q_temporal, ·) = temporal_bonus
                                                  │
                                                  ▼
                       final_score = merged_score + temporal_weight · temporal_bonus + …
                                     (RetrievalPipeline._final_score — additive re-rank only,
                                      never a filter: candidates not already in merged_score
                                      never receive a temporal_bonus lookup)
```

## Mathematical Formulation

### Phase 1: Multi-Scale Sinusoidal Temporal Encoding (Stage 7)

For a Unix timestamp \( t \), produce a \( d_t \)-dimensional vector:

\[
\mathbf{v} = \bigoplus_{s \in \mathcal{S}} \big[\sin(\omega_s \cdot t), \cos(\omega_s \cdot t)\big], \qquad \omega_s = \frac{2\pi}{T_s}
\]

Where \( \mathcal{S} \) is the fixed 7-scale set (`TemporalContextConfig.scales_seconds`):

| Scale | Period \( T_s \) (s) |
|-------|----------------------|
| Minute | 60 |
| Hour | 3,600 |
| Day | 86,400 |
| Week | 604,800 |
| Month (approx.) | 2,592,000 |
| Year | 31,536,000 |
| Decade | 315,360,000 |

Total dimension \( d_t = 2 \cdot |\mathcal{S}| = 14 \). The vector is L2-normalized at encoding time (`TemporalContext.encode`), not merely before comparison:

\[
\mathbf{t} = \frac{\mathbf{v}}{\|\mathbf{v}\|_2}
\]

**Similarity:**

\[
\cos(\mathbf{t}_1, \mathbf{t}_2) = \langle \mathbf{t}_1, \mathbf{t}_2 \rangle \in [-1, 1]
\]

Two timestamps close on **any** scale (e.g. same time-of-day, different day) retain positive similarity; two timestamps far apart on every scale trend toward zero. `encode_many` is the vectorized batch form used at retrieval time (one call per query, over the whole candidate set); `now()` is `encode(int(time.time()))`.

**Logical concept**: the sinusoidal basis is a fixed, zero-training fingerprint of "when" — no learned parameters, so it never drifts and never needs retraining as the corpus grows. If `scales_seconds` were reduced to a single scale, the encoding would only distinguish coarse-grained time bands at that one period and lose all resolution at every other band (e.g. day-only would treat 2am and 11pm on the same day as identical but "yesterday, same time" as maximally different).

### Phase 2: Temporal Anchor Estimation (Stage 10)

**Step 1 — Probe similarity.** A fixed set of 12 natural-language phrases is embedded once at `TemporalProbe.__init__` time (same encoder as episodes), L2-normalized, and stacked into \( \mathbf{P} \in \mathbb{R}^{12 \times d} \) (`_TEMPORAL_PROBES`, `slowave/latent/temporal.py`):

| # | Probe Phrase | Displacement |
|---|-------------|-------------|
| 0 | "right now, today, at the moment" | 0 |
| 1 | "yesterday, the day before" | −1 day |
| 2 | "a few days ago, several days ago" | −4 days |
| 3 | "last week, a week ago" | −7 days |
| 4 | "two weeks ago, a fortnight ago" | −14 days |
| 5 | "last month, a month ago, recently" | −30 days |
| 6 | "two months ago, a couple of months ago" | −60 days |
| 7 | "three months ago, several months ago" | −90 days |
| 8 | "six months ago, half a year ago" | −180 days |
| 9 | "last year, a year ago" | −365 days |
| 10 | "two years ago" | −730 days |
| 11 | "a long time ago, years ago, long ago" | −1,095 days |

There is no minute- or hour-scale probe — the finest past probe is "yesterday" (−1 day). A query is normalized internally (`q / \|q\|`) regardless of whether the caller already normalized it:

\[
\mathbf{s} = \mathbf{P} \cdot \hat{\mathbf{q}} \in \mathbb{R}^{12}
\]

**Step 2 — Dead-zone gate.** Let \( s_0 \) be the "now" probe's similarity. If no past probe beats it by at least `atemporal_margin`, the query carries no reliable temporal signal and the function returns immediately:

\[
\max_{i \in \{1,\dots,11\}} s_i \; - \; s_0 \; < \; \theta_{\text{atm}} \;\implies\; \text{return } t_{\text{now}}
\]

**Step 3 — Softmax with temperature** (over **all 12** probes, including "now"):

\[
w_i = \frac{\exp(s_i / T)}{\sum_{j=0}^{11} \exp(s_j / T)}
\]

(Implementation shifts \( s_i \) by \( \max_j s_j \) before exponentiating — standard numerical stabilization, does not change \( w_i \).)

**Step 4 — Weighted displacement:**

\[
\Delta = \sum_{i=0}^{11} w_i \cdot d_i, \qquad \text{anchor\_ts} = t_{\text{now}} + \operatorname{round}(\Delta)
\]

Because \( d_0 = 0 \) and every other \( d_i \le 0 \), \( \Delta \) is a convex combination that always lands in \( [\min_i d_i, 0] \) — the "now" probe's residual softmax weight can only pull the anchor *toward* the present, never push it past the single most extreme matched probe.

**Logical concept**: rather than parsing "last month" with a brittle rule-set, the encoder that already embeds episodes is reused to embed 12 static landmark phrases once; a query's temporal intent is read off as cosine similarity to those landmarks. The dead-zone gate (Step 2) is what keeps atemporal queries ("previous conversation", "what's my cat's name") from being misinterpreted as past-anchored — without it, every query would receive *some* nonzero displacement since softmax always assigns positive weight to something. `atemporal_margin=0.12` and `softmax_temperature=0.05` were calibrated against LongMemEval oracle queries with the `bge-small-en-v1.5` encoder (code comment, `temporal.py:242-249`): atemporal queries measured margin ∈ [−0.01, 0.11], genuine temporal queries measured margin ∈ [0.15, 0.33] — a clean separation in that one calibration run, not an architectural constant. A different encoder is not guaranteed to reproduce the same separation.

**Fixed 2026-07-09**: the `TemporalProbe` docstring (`temporal.py:209-213`) previously stated *"Default 0.1 is gently peaked"*, inconsistent with the constructor's actual default `softmax_temperature: float = 0.05`. Corrected to match; no behavior change.

### Phase 3: Integration in Retrieval

When `anchor_ts` differs from `now_ts`, the query-side temporal vector uses the anchor instead of the current time:

\[
\mathbf{t}_q = \begin{cases} \text{TemporalContext.encode}(\text{anchor\_ts}) & \text{temporal\_anchor\_ts is set} \\ \text{TemporalContext.now}() & \text{otherwise} \end{cases}
\]

For every episode \( m \) already present in the merged cosine/spread/predictive candidate pool (never for episodes outside it — see Invariant 3):

\[
\text{temporal\_bonus}(m) = \cos(\mathbf{t}_q, \mathbf{t}_m), \qquad \text{final\_score}(m) \mathrel{+}= \alpha_t \cdot \text{temporal\_bonus}(m)
\]

`RetrievalService.recall()` (`slowave/core/services/retrieval.py:143-157`) calls `estimate_anchor()` **unconditionally** on every recall — independent of `RetrievalConfig.use_temporal` — and only when the returned anchor differs from `now_ts` does it clone the retrieval config via `dataclasses.replace(cfg, temporal_anchor_ts=anchor_ts)` and build a fresh `RetrievalPipeline` for that one query. If `use_temporal=False`, this extra work still happens but is inert: `RetrievalPipeline.retrieve()` gates the entire temporal-bonus block on `self.cfg.use_temporal`.

## Configuration

### `TemporalContextConfig` (`slowave/latent/temporal.py`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `scales_seconds` | `tuple[int, ...]` | `(60, 3600, 86400, 604800, 2592000, 31536000, 315360000)` | The 7 time scales; embedding dim = \( 2 \times \) len(scales_seconds) |

### `TemporalProbe` Constructor (`slowave/latent/temporal.py`) — plain `__init__` kwargs, not a dataclass

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `encode_fn` | `Callable[[str], np.ndarray]` | (required) | Text encoder — same one used for episodes |
| `probes` | `tuple[tuple[str, int], ...]` | `_TEMPORAL_PROBES` (12 entries, table above) | Probe phrase → displacement-seconds |
| `softmax_temperature` \( T \) | `float` | `0.05` | Softmax sharpness — low T ≈ winner-takes-all, high T ≈ centre-of-mass of all probes |
| `atemporal_margin` \( \theta_{\text{atm}} \) | `float` | `0.12` | Dead-zone margin (see Step 2 above) |

**Not exposed anywhere.** `SlowaveEngine.__init__` constructs the probe as `TemporalProbe(self.encoder.encode)` (`engine.py:234`) — every argument except `encode_fn` is the hardcoded class default. There is no `TemporalProbeConfig` dataclass, no field on `SlowaveConfig`, and no CLI flag on any eval script that can override `softmax_temperature`, `atemporal_margin`, or the probe set. This is the mirror image of `RetrievalConfig.use_temporal`/`temporal_weight` below, which are fully wired end to end (constructor → `SlowaveConfig.retrieval` → `--no-temporal` CLI flag in `longmemeval_eval.py`).

### `RetrievalConfig` (temporal-relevant fields; full dataclass documented in `06-retrieval.md`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `use_temporal` | `bool` | `True` | Gates the entire temporal-bonus block in `RetrievalPipeline.retrieve()` |
| `temporal_weight` \( \alpha_t \) | `float` | `0.25` | Weight of temporal cosine in the final additive score |
| `temporal_anchor_ts` | `int \| None` | `None` | Explicit query anchor (Unix ts); set per-query by `RetrievalService` from `TemporalProbe.estimate_anchor()`, never by direct user input today |

## Key Invariants

1. **Sinusoidal encoding is deterministic and stateless** — `encode(ts)` called twice with the same `ts` returns bit-identical output; there are no learned parameters anywhere in Stage 7.
2. **Temporal similarity is bounded**: \( \cos(\mathbf{t}_1, \mathbf{t}_2) \in [-1, 1] \), and \( \cos(\mathbf{t}, \mathbf{t}) = 1 \) for any timestamp encoded against itself.
3. **The temporal bonus only re-ranks a pool that already exists — it never expands it.** `temporal_bonus_by_id` is only ever looked up for `int(m.id)` where `m` is drawn from `episodes = self.episodic.get_many(all_episode_ids)`, and `all_episode_ids = list(merged_score.keys())` is fixed *before* the temporal block runs (`retrieval.py:325-341`). An episode with perfect temporal proximity but zero cosine/spread/predictive evidence is never retrieved.
4. **The dead-zone gate preserves legacy behaviour exactly for atemporal queries** — `estimate_anchor()` returns `now_ts` unchanged whenever the best past-probe margin is below `atemporal_margin`, independent of `softmax_temperature`.
5. **Softmax averaging can only pull the anchor toward "now", never past the single most extreme matched probe** — since `d_0 = 0` and all other displacements are non-positive, the weighted-mean displacement is bounded in \( [\min_i d_i, 0] \) (a convex-combination property, not encoder-specific).
6. **Probe embeddings are computed exactly once per `TemporalProbe` instance** — `__init__` embeds and caches `_probe_matrix`; `estimate_anchor()` performs only 12 dot products, no re-embedding, no I/O.
7. **Anchor estimation runs on every `recall()` call regardless of `use_temporal`** — the gate that makes it a no-op lives in `RetrievalPipeline`, not in `RetrievalService`; disabling `use_temporal` does not skip the 12 probe dot products.

## Implementation Files

| File | What It Implements |
|------|-------------------|
| `slowave/latent/temporal.py` | `TemporalContext` / `TemporalContextConfig` — Stage 7 sinusoidal encoding, `encode`/`encode_many`/`now`/`cosine` |
| `slowave/latent/temporal.py` | `TemporalProbe` — Stage 10 anchor estimation, `_TEMPORAL_PROBES` compass table, `estimate_anchor()` |
| `slowave/latent/retrieval.py` | `RetrievalConfig` — `use_temporal`, `temporal_weight`, `temporal_anchor_ts` fields |
| `slowave/latent/retrieval.py` | `RetrievalPipeline.retrieve()` — temporal-bonus computation and additive score merge (lines ~328-347, ~477) |
| `slowave/core/services/retrieval.py` | `RetrievalService.recall()` — calls `estimate_anchor()` per query, conditionally rebuilds the pipeline with an anchored config |
| `slowave/core/engine.py` | `SlowaveEngine.__init__` — constructs the single `TemporalProbe` instance (lines ~227-236), all-defaults |
| `tests/unit/test_retrieval_pipeline_plumbing.py` | SP-2: proves the Stage 7 temporal bonus changes episode ranking under a controlled anchor |

## Diagnostic Hooks

| Metric | What It Measures | How to Instrument |
|--------|-----------------|-------------------|
| `anchor_fired_rate` | Fraction of queries where `estimate_anchor()` returns something other than `now_ts` — i.e. the dead-zone gate did *not* short-circuit. This is the module's central "is Stage 10 doing anything?" question, and **no instrumentation for it exists today** — `RetrievalService.recall()` computes `anchor_ts` but never records whether it changed. | Add a counter/log in `RetrievalService.recall()` at `if anchor_ts != now_ts:` (`services/retrieval.py:146`) |
| `anchor_displacement_distribution` | Histogram of `anchor_ts - now_ts` across a benchmark run — which probes are actually winning in practice | Same call site; log `anchor_ts - now_ts` when it fires |
| `temporal_bonus_contribution` | Mean/percentile of `temporal_weight * temporal_bonus` relative to `merged_score` for episodes in the final head — is the additive term large enough to ever flip a ranking? | `EpisodeDiagnostic.temporal_bonus` already exists (`slowave/latent/types.py:53`) and is populated per-episode when `diagnose=True`; not yet aggregated into `QueryDiagnostics` or any eval script's summary JSON |
| `temporal_only_saves` | Fraction of the final head that would drop out if `use_temporal=False` — mirrors `graph_only_saves` in `QueryDiagnostics` (`06-retrieval.md`), but no equivalent field exists for temporal | Would require a same-query dual-run (temporal on/off) diff, analogous to how `graph_only_saves` is computed |

## Parameter Sensitivity

| Parameter | Direction | Effect | Sweep Range |
|-----------|-----------|--------|-------------|
| `use_temporal` | on/off | Only boolean flag in this module. Removes the entire Stage 7 additive term; `longmemeval_eval.py --no-temporal` already wires this | on, off |
| `temporal_weight` | ↑ | Larger additive bonus — recency/anchor proximity can outrank progressively larger cosine deficits | 0.0, 0.10, 0.25, 0.40, 0.60 |
| `softmax_temperature` | ↓ | Sharper anchor selection (single dominant probe wins, less blending toward "now") | 0.02, 0.05, 0.10, 0.20 |
| `atemporal_margin` | ↑ | Fewer queries treated as temporally anchored — more conservative, more false negatives on genuinely temporal phrasing | 0.05, 0.08, 0.12, 0.18, 0.25 |
| `scales_seconds` composition | — | Removing a scale loses resolution at that time band; no sweep exists, structural choice | N/A — not a scalar to grid-search |

## Known Failure Modes

| Symptom | Likely Cause | Diagnostic Signal |
|---------|-------------|-------------------|
| Recency dominates an on-topic but older memory | `temporal_weight` too high relative to the cosine deficit between competing episodes | `EpisodeDiagnostic.temporal_bonus` comparable in magnitude to `cosine_score` for the swapped pair |
| "Last month" and "two months ago" queries return the same anchor | `softmax_temperature` too high (flat weights) blends adjacent probes toward their centroid; probes 5 and 6 are only 30 days apart in raw displacement, easily blended | `anchor_displacement_distribution` clusters near a single mode regardless of query wording |
| An unambiguous past-tense query still recalls only "now" | `atemporal_margin` calibrated on a different encoder than the one in use — the [−0.01, 0.11] vs [0.15, 0.33] separation from `bge-small-en-v1.5` may not hold for another model | `anchor_fired_rate` near 0% on a benchmark category known to contain many temporal questions (e.g. LongMemEval `temporal-reasoning`, LoCoMo category 2) |
| Changing `softmax_temperature`/`atemporal_margin` in an experiment has no effect | These are not `SlowaveConfig` fields — a script that only touches `RetrievalConfig` or `SlowaveConfig` never reaches `TemporalProbe`'s constructor at all | Grep the experiment's config construction for `TemporalProbe(` — if absent, the sweep is a no-op |
| No visibility into whether Stage 10 ever fires in production | `anchor_fired_rate` is not instrumented (see Diagnostic Hooks) | N/A until instrumented — this is the PROGRESS.md "key question" for this module |

## Relationship to Other Modules

| Module | Relationship |
|--------|-------------|
| `01-ingestion.md` | Upstream — `event_append`'s `ts` (defaults to ingestion-time `time.time()`) becomes `EpisodicMemory.ts`, the raw input to Stage 7 encoding |
| `06-retrieval.md` | Owns `RetrievalConfig` (shared dataclass); `06-retrieval.md` documents the full field set and the merged-score pipeline this module's additive bonus plugs into |
| `05-consolidation.md` | Unrelated timestamp mechanism, same domain — `LatentSchemaBuilder` computes a plain arithmetic `mean_ts`/`span_ts` per prototype (no sinusoidal encoding) for the geometric judge's recency gate (`min_time_delta_to_supersede_s`). The two temporal representations do not share code. |
| `08-feedback.md` | `FeedbackEvent.temporal_error` is a distinct concept (world-model/transition-prediction error), unrelated to this module's anchor estimation or sinusoidal encoding despite the shared word "temporal" |
