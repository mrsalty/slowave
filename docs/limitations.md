# Slowave — Known Limitations

Slowave is alpha software. This document covers operational limits, capability gaps, and design trade-offs. For full per-benchmark results and category breakdowns see [docs/benchmarks.md](benchmarks.md).

---

## Capability limits (zero-LLM design trade-offs)

These gaps are **structural** — they follow directly from Slowave's zero-LLM design. Closing them would require adding an LLM reasoning step, which is outside the current design boundary.

### Implicit preference inference

Slowave can only recall what was **explicitly stated**. It cannot infer what was *implied*.

- If you say "I prefer shorter replies", Slowave stores and recalls that.
- If you gradually shift to shorter replies without ever stating a preference, Slowave has no signal to detect the change.

**Benchmark impact:** 76.7% on LongMemEval single-session-preference (vs 96.7% for Mem0, which uses an LLM to extract and verbalize implied preferences). This is the largest capability gap vs LLM-based competitors.

### Cross-session arithmetic and aggregation

Slowave retrieves individual episodes but does not count, aggregate, or calculate across them.

- "How many times total did I mention X?" → not supported.
- "How many days since event Y?" → not supported.

**Benchmark impact:** LoCoMo temporal category 57.3%; LongMemEval multi-session −1.5 pp vs Mem0.

### Abstract behavioral style drift

Slowave detects preference changes by keyword signal. Abstract behavioral shifts ("be more concise", "explain less") are expressed through turn length and structure — there is no keyword to retrieve.

**Benchmark impact:** StaleMemory abstract behavioral drift 0–1%. Concrete preference changes with distinct keywords (e.g. switching from Python to Go) score 86–89%.

### Contradiction detection is heuristic, not guaranteed

Slowave uses geometric similarity to detect likely contradictions between new memories and existing ones. This is a best-effort heuristic:

- It catches clearly conflicting statements about the same topic with high cosine similarity.
- It **does not guarantee** detection of all contradictions, especially implicit or indirect ones.
- "Use tabs for indentation" and "I prefer spaces" may or may not be detected as conflicting depending on how they were stated.

Do not rely on Slowave for safety-critical contradiction detection.

### World knowledge

Slowave recalls what it was told. It cannot infer what it was never stored. Questions requiring general world knowledge that was never stated in a session will not be answered.

**Benchmark impact:** LoCoMo commonsense category 34.4% (out of scope by design).

---

## Benchmark comparison caveats

All published Slowave benchmark numbers are from **internal runs**. They have not been independently verified or reproduced by a third party.

- Slowave uses **keyword-overlap** scoring. Most competitors use an **LLM-as-judge**. These protocols produce different numbers for the same underlying retrieval quality — they are not directly comparable.
- Competitor numbers are taken from their published self-reports. Scoring protocols, dataset splits, and configurations may differ.
- Do not treat published numbers as academic benchmarks until they have been independently reproduced.

Reproduction scripts and expected numbers are published at [docs/reproducibility.md](reproducibility.md). Independent verification is welcome.

---

## Language support

All core memory operations are **language-agnostic**: episode storage, embedding, retrieval, and consolidation work on vectors and numeric metadata with no language dependency. Non-English input is supported.

One optional component has English-only defaults and falls back gracefully:

- **Temporal anchor probe** — compares query embeddings against pre-embedded English landmark phrases ("last month", "two weeks ago"). For non-English queries the probe does not fire and the system defaults to "now", which is correct for atemporal queries and slightly suboptimal for past-anchored ones.

**Multi-language support** (per-language temporal probes, multilingual embedding model selection) is planned for a future release.

---

## Deployment limits

- **Single-user, local only.** Slowave is designed for one user on one machine. The SQLite storage layer is not designed for concurrent multi-user writes or cloud deployment.
- **English-first embeddings.** The default embedding model (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) is trained primarily on English text. Non-English memory quality depends on the chosen embedding model.
- **No reasoning layer.** Slowave is a retrieval system. It surfaces relevant memories; it does not reason about them, synthesize answers, or draw conclusions.

---

## Alpha status

APIs, storage schema, and configuration options may change between versions. We do not yet guarantee schema migration between versions. Do not depend on schema stability in production environments until a stable release is announced.
