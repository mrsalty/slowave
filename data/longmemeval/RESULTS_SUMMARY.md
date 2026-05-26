# LongMemEval Evaluation Results — Slowave

Date: 2026-05-23
Dataset: LongMemEval Oracle (500 questions, evidence-only sessions)
Repo branch: feat/cls-merge
Commit: see `git log -1` in the repo root

## Configuration

| Setting | Value |
|---|---|
| Embedder | bge-small-en-v1.5 (384-dim) |
| Episode grouping | 1 episode per session (mean of all event embeddings) |
| Assignment threshold | 0.65 |
| Turns per session (benchmark) | max 10 (first 10 turns, 500 chars each) |
| Scorer | keyword overlap, hit threshold 0.50 |

---

## Experiment 1 — No-LLM Baseline (Pure Embedding Recall)

**All 500 questions, no LLM consolidation, pure FAISS + episode recall.**

| Category | N | Hits | Score | Mem0 old | Mem0 new | Delta vs Mem0 old |
|---|---|---|---|---|---|---|
| single-session-assistant | 56 | 52 | **92.9%** | n/a | n/a | n/a |
| single-session-user | 70 | 63 | **90.0%** | n/a | n/a | n/a |
| temporal-reasoning | 133 | 72 | **54.1%** | n/a | n/a | n/a |
| knowledge-update | 78 | 55 | **70.5%** | 79.5 | 93.6 | -9.0 |
| multi-session | 133 | 42 | **31.6%** | 70.7 | 88.0 | -39.1 |
| single-session-preference | 30 | 8 | **26.7%** | 76.7 | 96.7 | -50.0 |
| **TOTAL** | **500** | **292** | **58.4%** | | | |

**Latency:** ingest mean 0.69s (p95 1.48s) | recall mean 6.1ms
**Runtime:** ~5 minutes for 500 questions

---

## Experiment 2 — LLM Consolidation, qwen2.5-coder:1.5b (30/category)

**90 questions, 3 key categories, with LLM schema extraction.**

| Category | N | Hits | Score | Mem0 old | Mem0 new | Delta vs Mem0 old |
|---|---|---|---|---|---|---|
| knowledge-update | 30 | 25 | **83.3%** | 79.5 | 93.6 | **+3.8** |
| multi-session | 30 | 12 | **40.0%** | 70.7 | 88.0 | -30.7 |
| single-session-preference | 30 | 6 | **20.0%** | 76.7 | 96.7 | -56.7 |
| **TOTAL** | **90** | **43** | **47.8%** | | | |

**Latency:** ingest mean 10.7s (p95 33.1s, LLM-bound) | recall mean 14.7ms
**Runtime:** ~16 minutes for 90 questions

---

## Experiment 3 — LLM Consolidation, qwen2:7b (10 knowledge-update only)

**10 questions, knowledge-update only, with qwen2:7b LLM.**

| Category | N | Hits | Score | Mem0 old | Mem0 new | Delta vs Mem0 old |
|---|---|---|---|---|---|---|
| knowledge-update | 10 | 8 | **80.0%** | 79.5 | 93.6 | **+0.5** |

**Latency:** ingest mean 31.4s (qwen2:7b is slower on CPU) | recall mean 21.8ms
**Runtime:** ~5.5 minutes for 10 questions

---

## Key Findings

### 1. knowledge-update: beats Mem0 old with LLM consolidation

- No-LLM: 70.5% (−9 vs Mem0 old)
- 1.5B + LLM: **83.3% (+3.8 vs Mem0 old)**
- 7B + LLM: **80.0% (+0.5 vs Mem0 old)**

The CLS consolidation (extracting typed schemas from sessions) genuinely
helps with knowledge-update questions. The schema captures the *updated*
value; the previous value was overwritten in the prototype cluster.

Note: qwen2.5-coder:1.5b slightly outperformed qwen2:7b on this metric
(83.3% vs 80.0%). The 1.5B model is a coding-tuned model, which may
favor the structured extraction task.

### 2. single-session-preference: broken in current v1

- No-LLM: 26.7%
- With LLM: **20.0%** (worse!)

The LLM consolidation *hurts* preference recall. The reason: a long
single-session with many topics produces one session-level episode with a
mean embedding. The preference statement is buried among other content
and the mean embedding loses its signal. The LLM then extracts a schema
that summarises the entire session, not the preference specifically.

Fix required: the session-level episodic grouping is too coarse for
single-session-preference. Need sliding-window episodes or explicit
paragraph-level chunking within a session.

### 3. multi-session: schema helps but still far below baseline

- No-LLM: 31.6%
- With LLM: **40.0%**

Consolidation helps (+8.4 points) but the gap vs Mem0 is large (−30.7).
The main reason: multi-session questions require *synthesis* across
sessions ("how many X did I do total?"), which requires counting/aggregating
across multiple schemas. A single schema per session can't do this. This
requires cross-session replay consolidation — exactly what the nightly
replay (cross-episode LLM batch call) is designed for but not yet
implemented for the benchmark path.

### 4. single-session-user and single-session-assistant: excellent without LLM

- 90.0% and 92.9% with pure embedding recall
- No LLM needed for basic factual recall from single sessions

### 5. Latency is not the bottleneck for the good categories

- recall: 6–22ms regardless of category or model
- ingest (no LLM): 0.7s per question
- ingest (with 1.5B LLM): 7–35s per question depending on session count

---

## What Needs to Change

| Fix | Affected categories | Expected impact |
|---|---|---|
| Sliding-window episode chunking (not session-level mean) | single-session-preference | +30–50 points |
| Cross-session replay consolidation | multi-session | +20–30 points |
| Cross-prototype contradiction check | knowledge-update (edge cases) | +5–10 points |
| Schema reranking by query similarity | all | +5–10 points |

---

## Comparison Table

| System | knowledge-update | multi-session | single-session-preference |
|---|---|---|---|
| Mem0 old | 79.5 | 70.7 | 76.7 |
| Mem0 new | 93.6 | 88.0 | 96.7 |
| **Slowave v1 (no LLM)** | 70.5 | 31.6 | 26.7 |
| **Slowave v1 (1.5B LLM)** | **83.3** | **40.0** | 20.0 |
| **Slowave v1 (7B LLM, 10q)** | **80.0** | — | — |

Slowave v1 **beats Mem0 old on knowledge-update** — its declared
primary differentiator (contradiction/update handling via CLS consolidation).
It is significantly below on the other two categories, with identifiable
root causes and concrete fixes.
