# Changelog

## [0.1.6] - 2026-05-29

### Added
- **VSA (Vector Symbolic Architecture) role binding** — `slowave/latent/vsa.py` is now
  fully documented and covered by tests.  Every latent schema carries a 384-D HRR triple
  vector (`facets["vsa_vec"]`) binding subject / predicate / object roles via circular
  convolution.  Three extraction modes are available via `LatentSchemaBuilder(vsa_mode=...)`:
  - `"geometric"` (default) — language-agnostic; roles from centroid + PCA axes, no encoder call.
  - `"lexical"` — English-optimised regex + lexical signature, encoder called once per schema.
  - `"ner"` — spaCy dep-parse (`en_core_web_sm`); **English-only** (see Language note below).
- **53 VSA unit tests** (was 32) — new test classes cover `_extract_roles_lexical`,
  `_extract_roles_ner`, `LatentSchemaBuilder` vsa_mode guards, NER pipeline component
  validation (confirms NER is disabled, dep-parse only), and edge cases (empty text,
  long text truncation, determinism).

### Changed
- `slowave/latent/vsa.py` — `import re as _re` moved to module top (was at line 220);
  `# Lexical role extraction` and `# NER role extraction` section comments updated with
  clear language/model notes; `_extract_roles_ner` docstring now explicitly states it uses
  the **dependency parser**, not Named-Entity Recognition, and is English-only.
- `docs/architecture.md` — VSA Role Binding section added under §11 (Latent Schema Building);
  biological analogies table updated; module map corrected (removed deleted LLM/symbolic files,
  added `vsa.py` and `schema.py`).
- `docs/limitations.md` — new "VSA dep-parse mode (English-only)" section added under
  Language limitations; clarifies that `vsa_mode="ner"` requires `en_core_web_sm` and
  documents the language-agnostic alternatives.
- `docs/benchmarks.md` — version updated to 0.1.6 (no regression; VSA is a metadata/schema
  encoding path with no effect on the retrieval ranking pipeline).
- `README.md` — Language support section updated to list both English-only components
  (temporal probe and VSA dep-parse mode) in a comparison table with fallback guidance.

### Language note
`vsa_mode="ner"` uses spaCy's `en_core_web_sm` **English-only** model.  Despite the name,
NER tags are disabled; only the dependency parser is used.  For non-English deployments,
use `vsa_mode="geometric"` (default, language-agnostic) or `vsa_mode="lexical"` (no
model dependency).  Multi-language VSA support requires a multilingual or target-language
spaCy model — tracked as a future roadmap item.

### Benchmark results (v0.1.6, brain-only, zero LLM calls)

No regression vs 0.1.5.  VSA is a schema-encoding path and does not affect the retrieval
ranking pipeline.

| Benchmark | n | v0.1.6 | v0.1.5 | Δ |
|---|---:|---:|---:|---:|
| LongMemEval (with consolidation) | 500 | **70.0%** | 70.0% | 0 |
| LoCoMo (with consolidation) | 1 986 | **74.6%** | 74.6% | 0 |
| DMR | 100 | **95.0%** | 95.0% | 0 |

## [0.1.5] - 2026-05-29

### Added
- **LLM path removed** — `slowave/llm/` module deleted entirely (base, ollama_backend, openrouter_backend, prompts). `slowave/symbolic/contradiction.py` and `schema_extractor.py` also removed. The latent brain-only path is now the only supported mode. `SlowaveConfig` no longer accepts `llm`, `disable_llm`, or `schema_mode` fields.
- `stability_score`: schema facet computed from age (days since first formed) and support count. Saturates near 1.0 for old, well-supported schemas; starts near 0 for brand-new ones.
- `recurrence_count` / `recurrence_score`: tracks cumulative recall hits per schema. `recurrence_score = count / (count + 5)` — soft-capped normalisation. Updated on every `reinforce()` call (retrieval hit). `reinforce_schema()` (consolidation path) intentionally does not bump the count.
- `schema_utility`: composite `0.5 * stability_score + 0.5 * recurrence_score`. Stored in schema facets. Wired into the working-memory context gate activation (up to +0.12 bonus) and into `_schema_priors` retrieval steering (up to 1.5× multiplier for high-utility schemas).
- `SchemaStore.decay_unused()`: decay pass for active schemas that have never been recalled (`recurrence_count == 0`) and are older than `idle_days` (default 30). Reduces salience by `decay_amount` (default 0.15) per pass; schemas falling below `review_threshold` (default 0.30) are flagged `needs_review`. Explicit-remember schemas are always protected.
- `SlowaveEngine.decay_schemas()`: public wrapper for `decay_unused`, callable independently of consolidation.
- `consolidate_once()` now runs the decay pass automatically after replay+consolidation and returns a `"decay"` key in its stats dict.
- `display_label` now surfaced in `slowave schema` and `slowave context` human-readable output (format: `[faiss / sqlite / local]`).
- DMR (Deep Memory Retrieval) benchmark harness and dataset: `tests/integration/dmr_eval.py`, `data/dmr/dmr.json`. 10 personas × 3 sessions × 10 questions = 100 total questions.
- 50 unit tests total (16 new for utility scoring / decay).

### Changed
- License changed from MIT to AGPL-3.0-or-later for version 0.1.5 and later. Earlier published versions remain available under the licenses they were originally released with.
- Added commercial licensing guidance for organizations that need non-AGPL terms.
- `pyproject.toml`: removed `llm/prompts/*.txt` from package data; added `pytest` as dev dependency.

### Benchmark results (v0.1.5, brain-only, zero LLM calls)

| Benchmark | n | v0.1.5 | v0.1.4 | Δ |
|---|---:|---:|---:|---:|
| LongMemEval (episode-only) | 500 | **60.2%** | 60.2% | 0 |
| LoCoMo (episode-only) | 1 986 | **74.6%** | 74.6% | 0 |
| DMR (new) | 100 | **95.0%** | — | — |

DMR comparison (LLM-augmented baselines from arXiv:2501.13956):

| System | DMR score |
|---|---:|
| **Slowave v0.1.5** | **95.0%** |
| Zep (SOTA) | 94.8% |
| MemGPT | 93.4% |

No regression on LME or LoCoMo. LLM removal, utility scoring, and decay are all metadata/scoring-path changes with no impact on the core retrieval path.

## [0.1.4] - 2026-05-29

### Added
- `slowave doctor` command: checks Python version, torch, faiss, sentence-transformers, embedding backend, SQLite write access, and MCP server availability. Exits 1 if any check fails.
- `engine.consolidate_once()` public method: one replay + latent consolidation pass. CLI `consolidate` and `worker` now call this instead of engine internals.
- `LatentSchema.lexical_signature`: contrastive TF-IDF over cluster episode texts — pure numpy/stdlib, zero new dependencies.
- `LatentSchema.display_label`: top-3 distinctive terms joined by ` / ` (e.g. `"faiss / sqlite / local"`). Surfaces in schema cards and `context_brief`.
- `docs/limitations.md`: section on latent schema quality (cluster representatives vs generated summaries).

### Fixed
- Encoder `_ensure_loaded` now catches `RuntimeError` and `ModuleNotFoundError` from broken torch/torchvision/transformers stacks and emits a clear actionable diagnostic instead of a confusing import error message.
- `FutureWarning` from `get_sentence_embedding_dimension` suppressed by preferring the current `get_embedding_dimension` API.

### Changed
- `requires-python = ">=3.10,<3.13"` — Python 3.13 is not yet supported due to torch/torchvision dependency compatibility.
- Dependency lower bounds added in 0.1.3 retained.

### Benchmark results (v0.1.4, brain-only, zero LLM calls)

| Benchmark | n | v0.1.4 | v0.1.3 | Δ |
|---|---:|---:|---:|---:|
| LongMemEval | 500 | **60.2%** | 60.2% | 0 |
| LoCoMo | 1 986 | **74.6%** | 74.6% | 0 |

No regression on either benchmark. The new lexical_signature and display_label fields
are metadata-only and have no effect on the retrieval path.

LME elapsed: 149s (was 166s). LoCoMo elapsed: 57s (was 73s). Both on Python 3.13 Mac M-series CPU.


## [0.1.3](https://github.com/mrsalty/slowave/compare/slowave-v0.1.2...slowave-v0.1.3) (2026-05-27)


### Features

* add working-memory context gate ([fd1b8d9](https://github.com/mrsalty/slowave/commit/fd1b8d9874dd548631c7ca2762f7b32e7785bc68))
