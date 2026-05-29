# Changelog

## [0.1.5] - 2026-05-29 (includes 0.1.6 features)

### Added
- `stability_score`: schema facet computed from age (days since first formed) and support count. Saturates near 1.0 for old, well-supported schemas; starts near 0 for brand-new ones.
- `recurrence_count` / `recurrence_score`: tracks cumulative recall hits per schema. `recurrence_score = count / (count + 5)` — soft-capped normalisation. Updated on every `reinforce()` call (i.e. every retrieval hit). `reinforce_schema()` (consolidation path) intentionally does not bump the count.
- `schema_utility`: composite `0.5 * stability_score + 0.5 * recurrence_score`. Stored in schema facets. Wired into the working-memory context gate activation (up to +0.12 bonus) and into `_schema_priors` retrieval steering (up to 1.5× multiplier for high-utility schemas).
- `SchemaStore.decay_unused()`: decay pass for active schemas that have never been recalled (`recurrence_count == 0`) and are older than `idle_days` (default 30). Reduces salience by `decay_amount` (default 0.15) per pass; schemas falling below `review_threshold` (default 0.30) are flagged `needs_review`. Explicit-remember schemas are always protected.
- `SlowaveEngine.decay_schemas()`: public wrapper for `decay_unused`, callable independently of consolidation.
- `consolidate_once()` now runs the decay pass automatically after replay+consolidation and returns a `"decay"` key in its stats dict.
- 16 new unit tests covering all the above.



### Changed
- License changed from MIT to AGPL-3.0-or-later for version 0.1.5 and later. Earlier published versions remain available under the licenses they were originally released with.
- Added commercial licensing guidance for organizations that need non-AGPL terms.

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
