# Slowave — Known Limitations

Slowave is alpha software. This document lists known limitations honestly so you can make an informed decision about whether Slowave is appropriate for your use case.

## Architecture limitations

### Keyword-based evaluation metric
The published benchmark numbers use a keyword hit-rate metric (are answer keywords present in retrieved context?). This is a proxy for retrieval quality, not a direct measure of end-to-end QA accuracy. LLM-extraction systems like Mem0 score higher partly because they can synthesise answers from structured extracts rather than surfacing raw episode text.

### No answer-construction layer
Slowave retrieves relevant memory; it does not construct or synthesise answers. For questions that require arithmetic over retrieved facts ("how many days between X and Y?"), aggregation across episodes ("what is the total X across all sessions?"), or implicit inference, Slowave cannot help without an answer-construction layer on top.

### Preference abstraction gap
Implicit preferences ("I usually prefer shorter replies") are not automatically abstracted into queryable schema entries. Keyword hit-rate on this category is structurally capped at ~20% on LongMemEval. Addressing this within a purely local, LLM-free architecture is an open research problem (Stage 11 — preference-extraction schema layer).

### Multi-session aggregation
Cross-session fact aggregation (summing quantities across multiple episodes) is not implemented. Each episode is retrieved individually; the Slowave engine does not join information across episodes in the retrieval layer.

## Language limitations

### VSA dep-parse mode (English-only)

The `vsa_mode="ner"` / `build_schema_vsa_ner` path in `slowave/latent/vsa.py` uses spaCy's
`en_core_web_sm` model and is **English-only**. Despite the name, this mode does NOT use
Named-Entity Recognition; it uses spaCy's **dependency parser** (tok2vec + tagger + parser)
to extract subject / predicate / object roles from a schema's central-episode text.
NER and lemmatizer components are explicitly disabled for performance.

For multi-language deployments, use:
- `vsa_mode="geometric"` (default) — language-agnostic; roles derived from centroid + PCA axes,
  no text parsing required.
- `vsa_mode="lexical"` — English-optimised regex verb-pattern matching; no language-specific
  model, degrades gracefully on non-ASCII or non-English text.

To extend `vsa_mode="ner"` to another language, replace `en_core_web_sm` with a multilingual
or target-language spaCy model and update `_get_spacy_nlp()` in `slowave/latent/vsa.py`.

### Temporal anchor probe (English-calibrated)
The temporal probe (Stage 10) estimates which past time period a query refers to ("last month", "two weeks ago") by comparing the query embedding against a set of pre-embedded **English** landmark phrases. For queries in other languages, the temporal probe does not fire and the system uses "now" as the temporal reference. This means temporal re-ranking may be slightly suboptimal for non-English past-anchored queries.

All other core operations (embedding, retrieval, FAISS, spreading activation, graph) are language-agnostic.

To extend the probe to another language, add landmark phrases in that language to `_TEMPORAL_PROBES` in `slowave/latent/temporal.py`.

## Benchmark limitations

### Not independently verified
Benchmark numbers in `docs/benchmarks.md` are from internal runs and have not yet been independently reproduced or peer-reviewed. See [docs/reproducibility.md](reproducibility.md) for the planned reproduction path.

### Comparison with Mem0 is not apples-to-apples
Mem0 uses LLM extraction as part of the memory pipeline and is evaluated under a different protocol. The comparison is directional only. Slowave and Mem0 are optimising for different trade-offs: Slowave prioritises local, private, zero-LLM operation; Mem0 prioritises extraction quality with LLM assistance.

### Evaluation datasets
- **LongMemEval**: 500 questions across 6 categories. Gaps in multi-session and preference categories are documented.
- **LoCoMo**: 1986 questions across 5 categories. Commonsense category (27.1%) requires world knowledge not present in the memory store.

## Storage and scale

### Not designed for large-scale production
Slowave uses SQLite and in-memory FAISS indices. It is designed for personal and small-team use with up to tens of thousands of episodes. For large-scale deployments, the storage and index layers would need to be replaced.

### FAISS indices rebuilt on startup
FAISS indices are rebuilt from SQLite on engine startup (`reset_faiss_from_db`). For very large stores, startup latency increases linearly with episode/prototype count.

## Latent schema quality: cluster representatives, not generated summaries

In the default LLM-free path, a latent schema stores:

- The **most-central episode text** as a human-readable handle (e.g. `"User: Nebula uses FAISS local memory item 4"`)
- A **lexical signature** of the top distinctive terms in the cluster (e.g. `{"faiss": 0.88, "sqlite": 0.74, "local": 0.70}`)
- A **display label** derived from the top 3 terms (e.g. `"faiss / sqlite / local"`)

The central episode text is a *representative example*, not a synthesised summary. It is the episode whose embedding is geometrically closest to the cluster centroid — the most typical member. It will look like raw agent/user text, not like an LLM-written abstract.

The lexical signature and display label give a more useful at-a-glance view of what the cluster is about. Both are deterministic and auditable — no LLM, no generation.

If you need human-quality summaries, that requires a verbalization layer (Stage 11 in the roadmap), which is explicitly out of scope for the LLM-free path.


## No LLM required

Slowave is fully LLM-free. Ingest, consolidation, and retrieval require no API key or LLM call. The LLM-based schema extraction code path was removed in v0.1.5.

## Alpha status

APIs, storage schema, and configuration options may change between versions. We do not yet guarantee schema migration between versions. Do not depend on schema stability in production environments until a stable release is announced.
