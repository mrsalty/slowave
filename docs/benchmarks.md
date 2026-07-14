# Slowave Benchmarks

> **Alpha-stage results.** Internal runs, not independently verified. Treat as directional.
> Reproduction scripts: [docs/reproducibility.md](reproducibility.md)

**Scoring.** Two independent scorers, tracked separately:
- **Keyword-overlap** — free, zero-cost, always computed. Measures whether rubric tokens appear in retrieved context. Stricter than LLM-judge (no credit for correct semantics with different wording).
- **LLM-judge** (`--judge-model deepseek-v4-flash`) — semantic grading of each rubric nugget as correct/incorrect. Same protocol Mem0 and Zep use. Costs API tokens. Only metric comparable to competitor published numbers.

All Slowave runs: **zero LLM calls for memory operations**, fully local, no API key required (except the optional LLM-judge scoring step).

---

## At a Glance

| Benchmark | n | Keyword | LLM-Judge | What it tests |
|---|---|---|---|---|
| **DMR** | 500 | **99.0%** | — | Wikipedia factual recall. |
| **LongMemEval** | 500 | **87.8%** | **55.8%** | Lifelong assistant memory: facts, updates, preferences, temporal reasoning across sessions. |
| **LoCoMo** | 1,986 | **85.75%** | **69.29%** | Multi-session conversational recall across 10 real dialogues, 5 categories. Primary tuning target. |
| **StaleMemory** | 1,200 | 39.5% | — | Preference drift detection. Unique — no competitor publishes on it. |
| **BEAM** | 700 | — | **41.6%** | Scale + complex reasoning. Measures retrieval + LLM answer-generation as a compound score. |

---

## 🧠 LongMemEval

**What it tests:** 500 questions across 6 categories — remembering facts across sessions, tracking when facts change, recalling preferences, and reasoning about time. The closest thing to a standard benchmark in AI memory.

### Keyword-Overlap Results

| Category | n | Score |
|---|---|---|
| single-session-user | 70 | 95.7% |
| knowledge-update | 78 | 94.9% |
| single-session-assistant | 56 | 92.9% |
| temporal-reasoning | 133 | 88.0% |
| multi-session | 133 | 79.7% |
| single-session-preference | 30 | 76.7% |
| **Overall** | **500** | **87.8%** |

### LLM-Judge Results (deepseek-v4-flash)

| Category | n | Judge Score | Keyword→Judge Δ |
|---|---|---|---|
| single-session-assistant | 56 | 91.1% | −1.8pp |
| single-session-user | 70 | 82.9% | −12.8pp |
| factual_knowledge | — | 77.3% | — |
| knowledge_update | 78 | 73.1% | −21.8pp |
| multi-session | 133 | 42.1% | −37.6pp |
| single-session-preference | 30 | 50.0% | −26.7pp |
| temporal_reasoning | 133 | 31.6% | −56.4pp |
| **Overall** | **500** | **55.8%** | −32.0pp |

**Keyword→judge gap reveals where retrieval works but context quality matters.** Minimal gap on factual recall (assistant 91.1%, user 82.9%) — keyword false positives are rare. Large gaps on temporal reasoning (31.6%) and multi-session (42.1%) — facts are retrieved but the judge requires synthesis from context that lacks pre-computed answers.

---

## 💬 LoCoMo

**What it tests:** 1,986 questions across 10 real multi-session conversations, 5 categories. A broad, realistic conversational recall benchmark.

### Keyword-Overlap Results

| Category | n | Score |
|---|---|---|
| cross-session | 1,257 | 89.3% |
| single-session | 475 | 85.7% |
| temporal | 119 | 57.1% |
| adversarial | 85 | 50.6% |
| commonsense | 50 | 50.0% |
| **Overall** | **1,986** | **85.75%** |

### LLM-Judge Results (deepseek-v4-flash, n=1,540 judged)

| Category | Judge Score | Keyword→Judge Δ |
|---|---|---|
| Factual / trivia | 93.7% | <5pp |
| Overall | 69.29% | −16.46pp |
| event_ordering | 36.5% | −48.9pp |

**Minimal gap on factual recall** — keyword scoring is honest where retrieval is straightforward. **Large gap on temporal/ordering** — facts are present but chronological synthesis requires client-side reasoning.

---

## 📄 DMR

**What it tests:** 500 Wikipedia-page factual recall questions. Simple retrieval — "was this fact stored?" No temporal reasoning, no multi-session, no distractors.

**Result:** 99.0% keyword-overlap. Recall@20 = 99.0%, R@50 = 99.0%, MRR = 0.6778. Near ceiling — the remaining 1% are items that rank below position 50 or have token-mismatch issues. An LLM-judge pass would distinguish true misses from keyword false negatives.

**Role:** Ceiling canary. DMR is the simplest benchmark — if this score drops, something is broken in the retrieval pipeline.

---

## 🔄 StaleMemory

**What it tests:** Does Slowave recall the *current* preference after it silently changes — never re-stated, only implied by a shift in behavior? 1,200 scenarios across 8 coding-assistant attribute types. No other memory system publishes on this benchmark.

| Attribute | Detection | n | Type |
|---|---|---|---|
| programming_language | **100%** | 150 | Distinct keyword |
| naming_convention | **94.0%** | 150 | Distinct keyword |
| output_format | 63.3% | 150 | Mixed |
| tool_preference | 44.7% | 150 | Mixed |
| communication_style | 14.0% | 150 | Abstract |
| error_handling | 0.0% | 150 | Abstract |
| example_scope | 0.0% | 150 | Abstract |
| explanation_approach | 0.0% | 150 | Abstract |
| **Overall** | **39.5%** | **1,200** | |

**Sharp split between concrete and abstract.** Distinct-keyword preferences (language, naming) score 94–100%. Abstract behavioral preferences (style, tone) score 0–14% — there is no keyword to retrieve when the change is expressed through turn length and structure alone. Closing this gap requires an LLM to semantically compare before/after behavior, outside the zero-LLM design boundary.

---

## 🔬 BEAM

**What it tests:** 700 questions across 10 categories — scale (1,700+ message conversations), complex reasoning, knowledge updates, event ordering, summarization. BEAM was designed for LLM-on-write systems and includes an answerer step: an LLM generates an answer from retrieved context, then a judge grades that answer against rubrics.

**Result:** 41.6% judge score (deepseek-v4-flash). Parse-error rate: 4.1%.

### Key Structural Finding: Retrieval Works, Answering Doesn't

| Category | Judge Score | Recall@20 |
|---|---|---|
| knowledge_update | 74.3% | 100% |
| preference_following | 63.9% | 98.6% |
| numerical_precision | 64.8% | 100% |
| abstention | 62.1% | 98.6% |
| instruction_following | 43.7% | 98.6% |
| contradiction_resolution | 34.1% | 100% |
| temporal_reasoning | 35.1% | 100% |
| multi_session_reasoning | 26.5% | 98.6% |
| summarization | 18.0% | 100% |
| event_ordering | 12.1% | 100% |

**Recall@20 is 97–100% across every category** — retrieval finds relevant content almost every time. The low judge scores are an answerer/reasoning gap: the LLM cannot reconstruct chronological order, summarize, or resolve contradictions from Slowave's raw consolidated output.

This is a format mismatch, not a retrieval failure. LLM-on-write competitors produce answerer-friendly text; Slowave produces raw retrieval output optimized for client consumption. 

**BEAM numbers are not directly comparable to LME/LoCoMo judge scores** — BEAM measures retrieval + answer-generation as a compound score, while LME/LoCoMo judge raw retrieved context directly.

---

## ⚠️ Known Limitations

These gaps follow directly from the zero-LLM design. See [limitations.md](limitations.md) for full details including deployment limits, language support, and contradiction handling.

- **Implicit preference inference.** LongMemEval single-session-preference 50.0% LLM-judge. Slowave retrieves what was stated; it cannot infer unstated preferences. Largest gap vs LLM-based competitors.
- **Temporal reasoning and aggregation.** LoCoMo event_ordering 36.5%, LongMemEval temporal_reasoning 31.6%. Facts are retrieved but chronological synthesis and cross-session arithmetic require client-side reasoning.
- **Abstract style drift.** StaleMemory 0–14% on behavioral preferences. No keyword means no retrieval signal for style/tone changes.
- **Not independently verified.** All numbers are internal runs. Reproduction scripts are published — independent verification is welcome.

---

## Reproducibility

```bash
# Full suite (keyword-overlap, no LLM judge)
python tests/integration/run_full_benchmark.py --no-llm

# With LLM-judge scoring (needs `OPENROUTER_API_KEY`)
python tests/integration/longmemeval_eval.py --consolidate --judge-model deepseek-v4-flash
python tests/integration/locomo_eval.py --consolidate --judge-model deepseek-v4-flash
python tests/integration/beam_eval.py --consolidate --judge-model deepseek-v4-flash --workers 6
```

Full dataset download links, run conditions, and expected numbers: [docs/reproducibility.md](reproducibility.md)
