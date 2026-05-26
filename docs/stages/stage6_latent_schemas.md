# Stage 6 results: latent schemas beat the LLM pipeline

Three-way LongMemEval comparison on identical 180 questions (30 per
category, all 6 categories). Same code, same dataset, same scorer.

## Headline

```
Configuration               Score    Time      vs cosine baseline
────────────────────────────────────────────────────────────────────
no-LLM (cosine baseline)    60.6%    37.0s     baseline
Stage 3+5 latent (no LLM)   66.1%    39.6s     +5.5pp
Stage 6 LATENT SCHEMAS      68.3%    42.2s     +7.7pp    ← winner
LLM (qwen2.5-coder:1.5b)    61.1%    ~6 hours  +0.5pp
```

**Stage 6 beats the LLM-augmented pipeline by +7.2pp while running 500×
faster, on the exact same questions, with zero LLM calls.**

## Per-category breakdown

| Category | cosine | Stage 3+5 | Stage 6 | Δ vs cosine | Δ vs S3+5 |
|---|---|---|---|---|---|
| knowledge-update | 63.3% | 90.0% | **93.3%** | **+30.0pp** | +3.3pp |
| multi-session | 50.0% | 53.3% | **60.0%** | **+10.0pp** | **+6.7pp** |
| temporal-reasoning | 63.3% | 66.7% | **70.0%** | **+6.7pp** | +3.3pp |
| single-session-assistant | 73.3% | 73.3% | 73.3% | 0 | 0 |
| single-session-user | 93.3% | 93.3% | 93.3% | 0 | 0 |
| single-session-preference | 20.0% | 20.0% | 20.0% | 0 | 0 |
| **TOTAL** | **60.6%** | **66.1%** | **68.3%** | **+7.7pp** | **+2.2pp** |

## Where the lift comes from

Stage 6 adds three things on top of Stage 3+5:

1. **`LatentSchema` records** — every prototype now has a first-class
   geometric fingerprint (centroid + facet axes + temporal anchor +
   confidence + central-member text). The schema store now contains
   these, which means the retrieval pipeline can rerank with them.

2. **Geometric contradiction detection** — when a new schema's centroid
   is close to an existing one but their facet axes disagree, the
   newer one supersedes the older one. This appears to be cleaning up
   the multi-session retrieval surface (the biggest single-category
   delta, +6.7pp).

3. **Temporal anchors on schemas** — `mean_ts` and `ts_span_s` are now
   carried on every schema. The retriever doesn't yet *use* them
   explicitly (that's Stage 7), but they're present in the `facets`
   dict and the FAISS ranker is benefiting from the cleaner schema
   geometry. +3.3pp on temporal-reasoning is consistent with that.

## What it validates

The Stage 6 architectural claim was:

> Memory consolidation is a latent geometric process. LLM-extracted
> text schemas are not necessary; pure prototype geometry suffices.

**The data supports it.** Brain-only beats the small-LLM pipeline by
+7.2pp on the same questions. The LLM was structurally a noise source
in this regime, exactly as the previous three-way analysis predicted.

## Full LongMemEval (500 questions) — confirmed

The 30-per-category result above is reproduced cleanly at full
benchmark scale:

```
Configuration               Score        Time     vs cosine
────────────────────────────────────────────────────────────────
no-LLM (cosine baseline)    60.00%       153s     baseline
Stage 3+5 latent            66.40%       161s     +6.40pp
Stage 6 LATENT SCHEMAS      70.00%       168s     +10.00pp
```

**Stage 6 lift over cosine RAG is +10.00pp on the full 500 questions.**

Per-category (full benchmark):

| Category | cosine | S3+5 | **S6** | Δ vs cos | Δ vs S3+5 |
|---|---|---|---|---|---|
| knowledge-update (n=78) | 66.67 | 84.62 | **92.31** | **+25.64** | **+7.69** |
| multi-session (n=133) | 51.13 | 55.64 | **60.90** | **+9.77** | **+5.26** |
| temporal-reasoning (n=133) | 54.89 | 63.91 | **67.67** | **+12.78** | +3.76 |
| single-sess-assistant (n=56) | 66.07 | 66.07 | 66.07 | 0 | 0 |
| single-sess-user (n=70) | 91.43 | 91.43 | 91.43 | 0 | 0 |
| single-sess-preference (n=30) | 20.00 | 20.00 | 20.00 | 0 | 0 |
| **TOTAL (n=500)** | **60.00** | **66.40** | **70.00** | **+10.00** | **+3.60** |

Headline: **Stage 6 hits 70.00% on full LongMemEval with zero LLM calls
in 168 seconds.** Competitive with the paper's strongest dense
retriever baselines (flat-Stella ~65-70%), gap to Mem0 SOTA is -24.4pp.

## Honest caveats

* **180-question subset was representative.** Full-benchmark numbers
  shifted only marginally (Stage 6: 68.3% → 70.0%, Stage 3+5: 66.1% →
  66.4%, cosine: 60.6% → 60.0%). Trends and per-category dynamics
  identical.
* **Single-session-preference still 20%.** The meta-cognition gap is
  independent of consolidation mechanism. Stages 7-10 won't help here
  either; this category is structurally out of reach for retrieval.
* **No frontier-LLM comparison yet.** We tested against qwen2.5-coder:1.5b.
  Whether a stronger LLM (Claude Haiku via OpenRouter) would invert the
  result is still open. The right comparison to run next.
* **Stage 6 doesn't yet use the temporal axis at retrieval.** The
  schemas carry `mean_ts`/`ts_span_s` but the retriever doesn't consult
  them. Stage 7 is the next obvious step.

## Speed comparison

| Mode | Ingest per question | Full 180-q run |
|---|---|---|
| cosine baseline | 0.20s | 37s |
| Stage 3+5 latent | 0.22s | 40s |
| **Stage 6 latent schemas** | **0.23s** | **42s** |
| LLM qwen2.5-coder:1.5b | 16-25s | ~6 hours |

Stage 6 ingest is essentially the cost of replay + SVD. The
schema-extraction LLM call (the slow part of the previous architecture)
is gone.

## Reproduction

```bash
# All three runs, ~2 minutes each
.venv/bin/python tests/integration/longmemeval_eval.py \
  --no-consolidate \
  --categories knowledge-update single-session-preference multi-session \
               single-session-user single-session-assistant temporal-reasoning \
  --limit 30 \
  --out data/longmemeval/runs/stage6_no_llm.json

.venv/bin/python tests/integration/longmemeval_eval.py \
  --no-consolidate --replay-only \
  --categories knowledge-update single-session-preference multi-session \
               single-session-user single-session-assistant temporal-reasoning \
  --limit 30 \
  --out data/longmemeval/runs/stage6_replay_only.json

.venv/bin/python tests/integration/longmemeval_eval.py \
  --schema-mode latent \
  --categories knowledge-update single-session-preference multi-session \
               single-session-user single-session-assistant temporal-reasoning \
  --limit 30 \
  --out data/longmemeval/runs/stage6_latent.json
```

## Next

* **Full 500-question LongMemEval** with Stage 6 to lock in the
  headline number.
* **Stage 7 — temporal context vectors** (the brain-faithful version:
  every memory carries an intrinsic time coordinate, not a parsed-date
  query filter).
* **A/B against a frontier LLM via OpenRouter** to test the
  "small LLMs are noise" hypothesis at higher model quality.
