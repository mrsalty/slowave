# Token Efficiency Benchmark

This benchmark measures how many context tokens are injected at the start of each session when using three different memory strategies:

1. **History replay** — replay every prior session message.
2. **Static knowledge doc** — inject the same project document every session.
3. **Slowave `context_brief()`** — inject a semantically filtered, salience-ranked working-memory brief.

The benchmark also checks whether Slowave's brief contains the expected relevant memory for each session. Token reduction alone is not useful if the injected context is wrong.

---

## Key Result

Across 20 synthetic coding sessions using the real ONNX embedding backend, Slowave injected substantially fewer context tokens than both baselines while preserving expected-memory recall in 19 out of 20 sessions.

| Strategy | Avg tokens / session | Total tokens | Recall quality |
|---|---:|---:|---:|
| History replay | 982 | 19,647 | N/A |
| Static knowledge doc | 327 | 6,540 | N/A |
| Slowave `context_brief()` | 135 | 2,708 | 19 / 20 |

Result:

| Comparison | Token reduction |
|---|---:|
| Slowave vs history replay | 86.2% |
| Slowave vs static knowledge doc | 58.6% |

Slowave used fewer tokens than history replay from session 2 onward.

---

## What Is Being Compared?

### Baseline A: History Replay

History replay re-injects the full transcript of every previous session into each new session.

This represents the naive approach where context grows linearly over time.

| Property | Value |
|---|---|
| Session 1 context | 96 tokens |
| Session 20 context | 1,875 tokens |
| Growth pattern | Linear |
| Main weakness | Becomes increasingly expensive over time |

---

### Baseline B: Static Knowledge Doc

The static-doc baseline injects the same Markdown knowledge file into every session, regardless of the current task.

This approximates workflows based on files such as `CLAUDE.md`, project notes, or manually maintained context documents.

| Property | Value |
|---|---|
| Context size | 327 tokens per session |
| Growth pattern | Constant |
| Main weakness | Does not adapt to the current task |

---

### Slowave `context_brief()`

Slowave uses `context_brief(query=<current task>)` to build a compact working-memory brief for the current session.

The brief is:

- semantically filtered;
- salience-ranked;
- scope-aware;
- hard-capped;
- generated without an LLM in the memory loop.

| Property | Value |
|---|---|
| Average context size | 135 tokens per session |
| Character cap | 1,800 characters |
| Growth pattern | Constant |
| Main weakness | Depends on retrieval quality |

---

## Full Results

| Metric | History replay | Static doc | Slowave |
|---|---:|---:|---:|
| Average tokens / session | 982 | 327 | 135 |
| Minimum tokens / session | 96 | 327 | 132 |
| Maximum tokens / session | 1,875 | 327 | 139 |
| Total tokens across 20 sessions | 19,647 | 6,540 | 2,708 |

Quality check:

| Metric | Result |
|---|---:|
| Sessions tested | 20 |
| Sessions containing expected memory | 19 |
| Expected-memory hit rate | 95% |

Final result:

> Slowave achieved an 86.2% token reduction compared with history replay and a 58.6% reduction compared with the static-doc baseline, while retrieving the expected memory in 19 out of 20 sessions.

---

## What "Quality" Means

Each session has:

- a realistic task query;
- one expected memory;
- one expected keyword associated with that memory.

Example:

| Session type | Expected memory signal |
|---|---|
| Database migration task | `PostgreSQL` |
| Frontend task | Relevant UI/project preference |
| Deployment task | Relevant infrastructure decision |

A session is counted as a hit if the expected keyword appears in the rendered Slowave brief.

This is intentionally a simple, deterministic quality check. It verifies that the right memory was retrieved, but it does not claim to measure full answer quality or semantic correctness.

---

## Methodology

| Item | Configuration |
|---|---|
| Token estimation | `len(text) // 4` |
| Expected token-count error | approximately +/-15% |
| Encoder | `BAAI/bge-small-en-v1.5` ONNX |
| Embedding dimension | 384 |
| Embeddings | Real encoder output, not random vectors |
| Scenario size | 20 memories x 20 sessions |
| Memory types | Preferences, facts, decisions, lessons |
| Consolidation | One `consolidate_once()` call after ingestion |
| Retrieval | One `context_brief(query=...)` call per session |
| Retrieval settings | `limit=8`, `max_chars=1800` |
| Quality check | Expected keyword present in rendered brief |

---

## Reproducing the Benchmark

Run the benchmark through pytest:

```bash
.venv/bin/python -m pytest tests/test_token_efficiency.py -v -s
```

Or run it as a standalone script:

```bash
.venv/bin/python tests/test_token_efficiency.py
```

Results are written to:

```text
data/token_efficiency/results.json
```

---

## Interpretation

### API Cost

In this benchmark, Slowave reduced injected context from 19,647 total tokens to 2,708 total tokens across 20 sessions.

This corresponds to an 86.2% reduction compared with replaying full session history.

### Context Window Usage

History replay becomes more expensive as the number of sessions increases.

By session 20, the history-replay baseline injects 1,875 tokens before the user's current request is even considered. Slowave remains approximately constant at around 135 tokens per session.

### Static Project Context

The static-doc baseline is more efficient than history replay because its size is constant.

However, it injects the same context every time, even when only a small part is relevant to the current task. In this benchmark, Slowave reduced context size by 58.6% compared with the static document while still retrieving the expected memory in 95% of sessions.

---

## Caveats

This benchmark is intentionally small and deterministic. It should be interpreted as a focused token-efficiency test, not as a complete memory-quality benchmark.

Important limitations:

1. **Synthetic workload**  
   Real conversations vary in length, redundancy, topic drift, and ambiguity.

2. **Approximate token counting**  
   Token counts use `len(text) // 4`, which is a GPT-style approximation. Exact tokenizer counts may differ by approximately +/-15%.

3. **Simple quality metric**  
   Quality is measured by expected keyword presence, not by LLM-judged semantic correctness.

4. **No answer-quality measurement**  
   The benchmark measures injected context size and expected-memory presence. It does not measure whether a downstream model gives a better answer.

5. **Small static-doc baseline**  
   The static document used here is only 327 tokens. Real project context files can be much larger, but they can also be manually optimized.

6. **No LLM in consolidation**  
   Slowave uses embedding geometry and memory mechanics only. It does not use an LLM to summarize, rewrite, or compress memories during this benchmark.

---

## Related Benchmarks

For broader retrieval-quality evaluation, see:

- `docs/benchmarks.md` — LongMemEval, LoCoMo, and DMR benchmark results.
- `tests/test_token_efficiency.py` — token-efficiency benchmark implementation.
- `slowave/core/context.py` — `GatePolicy` and `WorkingMemoryGate` implementation.
