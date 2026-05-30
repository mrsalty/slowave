# Changelog

## [0.1.11](https://github.com/mrsalty/slowave/compare/slowave-v0.1.10...slowave-v0.1.11) (2026-05-30)


### Features

* 0.1.4 — doctor, consolidate_once, lexical signatures, Python bound ([e17a35b](https://github.com/mrsalty/slowave/commit/e17a35b1dbac2990c0cdfaa1f1941d93cf66189d))
* 0.1.5 — remove legacy LLM path, expose display_label in CLI schema/context ([cc2549e](https://github.com/mrsalty/slowave/commit/cc2549eb60a10c2dec7e2aecd5b7ab6bb8a9ea64))
* 0.1.5+0.1.6 — stability_score, recurrence_score, schema_utility, decay_unused ([8b8a5d4](https://github.com/mrsalty/slowave/commit/8b8a5d4465ea969c61fac190087e3c88bf2b9da8))
* add DMR (Deep Memory Retrieval) benchmark harness and dataset ([0ce57da](https://github.com/mrsalty/slowave/commit/0ce57dac500c4ec4b3f8d340c599023cd342fd93))
* add slowave setup command for one-command cross-platform wiring ([190efba](https://github.com/mrsalty/slowave/commit/190efba3f6928667b2c4afb1ed0a36b30ae75525))
* add working-memory context gate ([fd1b8d9](https://github.com/mrsalty/slowave/commit/fd1b8d9874dd548631c7ca2762f7b32e7785bc68))
* brain spinner on model load, sleep spinner on worker idle ([ee8dc6e](https://github.com/mrsalty/slowave/commit/ee8dc6e4607b6f7ffc7562d3da90291272ba25df))
* emoji output for slowave doctor ([dd1581c](https://github.com/mrsalty/slowave/commit/dd1581c404c8d852d870af47d9cd43c26267a919))
* fancy recall output — schema cards, sal bars, episode dates ([74bed02](https://github.com/mrsalty/slowave/commit/74bed02cf14d7e4ad574416dcd875735c27128ee))
* fancy stats output with emoji and thousand separators ([f74178f](https://github.com/mrsalty/slowave/commit/f74178fb040b4a2897534637fa6f05541fac0ded))
* **temporal:** Stage 10 — embedding-space temporal anchor estimation ([ad6906e](https://github.com/mrsalty/slowave/commit/ad6906e4a8c6382ace8313a269c3ddde11e1ee68))


### Bug Fixes

* bail out on invalid JSON in _read_json instead of silently returning {} ([1f74afa](https://github.com/mrsalty/slowave/commit/1f74afade2878b2e7ae554720b402ad6c6cfd41e))
* Claude Desktop skill must be uploaded manually via UI (filesystem injection not persistent) ([30f3b6f](https://github.com/mrsalty/slowave/commit/30f3b6ff52984d07215795e0e3cf0209ff9a483a))
* Claude Desktop uses Custom Instructions not Skills; setup prints the text to paste ([79a3539](https://github.com/mrsalty/slowave/commit/79a35394a1091af3eb7ca657b5332af7bd0c791a))
* document Claude Desktop turn-1 limitation and Custom Instructions workaround ([8b39777](https://github.com/mrsalty/slowave/commit/8b39777c8ac7a707c662bedb7fec78741cbc8a6c))
* lift Python 3.13 restriction — all deps ship cp313 wheels ([d63f0cc](https://github.com/mrsalty/slowave/commit/d63f0cc955dbcb30bdf1de3d98be04c93df728f0))
* replace Claude Desktop Skill with Custom Instructions; remove dead skill injection code ([2e15735](https://github.com/mrsalty/slowave/commit/2e15735a127bfffb503effad98b2c6f94c7eaf59))
* setup, docs, ci, and test improvements ([e403668](https://github.com/mrsalty/slowave/commit/e403668b08ec081ee763406d99b3b674446d7963))
* silence HF warning and Loading weights bar on cold model download ([94b4d3e](https://github.com/mrsalty/slowave/commit/94b4d3ed46c83a776959c31d76e28f7844c8c754))
* simplify Claude Desktop setup warning to one-liner with link ([e75c371](https://github.com/mrsalty/slowave/commit/e75c371d59d131d42e53d46bb4637ab4beed1c77))
* strengthen Skill description to trigger automatically on every conversation start ([a910088](https://github.com/mrsalty/slowave/commit/a9100887e4f46d23e7d57185f992cb01330fbf79))
* suppress HF hub warning and model loading progress bar on CLI/MCP startup ([3421f90](https://github.com/mrsalty/slowave/commit/3421f90979123aa7852e4268575f0715209c33e1))
* suppress License-File metadata field that breaks older PyPI upload ([32ba8b1](https://github.com/mrsalty/slowave/commit/32ba8b1e1eda33dfe8d9bd67ae92c3fecb1ecee7))
* use stable symlink path for slowave-mcp, not resolved versioned Cellar path ([e93bba5](https://github.com/mrsalty/slowave/commit/e93bba51c97ecfd83615ba1a313e4a321a304ca6))
* use table-form license in pyproject.toml to fix twine metadata error ([d3b2e18](https://github.com/mrsalty/slowave/commit/d3b2e18fe76737884a0ec7ce98b8b707a2c7f27b))


### Performance Improvements

* apply grid search best params (Phase 1-3, 2026-05-28) ([7201d7f](https://github.com/mrsalty/slowave/commit/7201d7f18a30e0b3ddcea5c951995ce25fe9e460))


### Documentation

* add brain emoji to title ([0d462a2](https://github.com/mrsalty/slowave/commit/0d462a29b924d710b4a60710c7acb1c6891ef422))
* add cross-tool shared memory row to comparison table ([5146083](https://github.com/mrsalty/slowave/commit/5146083319b40e23f2eaa42cbbc4de01a96a5c00))
* add emoji to main section headings ([c1daa54](https://github.com/mrsalty/slowave/commit/c1daa54f78564c21c775e0bab858601ac33d934c))
* add Fastest path section to cline integration README ([331aca2](https://github.com/mrsalty/slowave/commit/331aca2c029601ba73595731eeb71869ecb4d571))
* add gentle dig at MD/RAG memory systems before At a glance ([8b0c341](https://github.com/mrsalty/slowave/commit/8b0c341a865c7bfe1a7ff4f7d91427da70407d47))
* agent enforcement ([767faeb](https://github.com/mrsalty/slowave/commit/767faeb622f7699e33e50b5e719b951730e3f927))
* agent enforcement ([330031c](https://github.com/mrsalty/slowave/commit/330031ceaa4379428c5b3efdb7f5b1b2b35d4bbf))
* clarify cosine ablation, drop parameter tuning + comparison notes sections ([d8694c2](https://github.com/mrsalty/slowave/commit/d8694c224eba615f81f2d6d28964484d8d875070))
* clarify integration setup requirements ([a36a8c0](https://github.com/mrsalty/slowave/commit/a36a8c0b055dab133f03691a0053192c8eb05777))
* clarify public setup and integration guides ([9f7a03d](https://github.com/mrsalty/slowave/commit/9f7a03d53ff66aff56173b2bd2a0497760d326f3))
* convert overview ASCII pipeline to mermaid flowchart ([793bb05](https://github.com/mrsalty/slowave/commit/793bb050842b89c829e53161a6e195c20ad04e0c))
* correct install path before PyPI release ([084d66f](https://github.com/mrsalty/slowave/commit/084d66fbfef48991d7220496a242821f3a697e98))
* document background worker setup ([57e6f29](https://github.com/mrsalty/slowave/commit/57e6f290ac8be231f946ea8bc297ab1ed384dde9))
* make overview flowchart vertical (TD) ([513a42c](https://github.com/mrsalty/slowave/commit/513a42cae7a212365856e7a2270353649247f5d8))
* mark temporal scores as solid ([4bc5b54](https://github.com/mrsalty/slowave/commit/4bc5b546fb0bb840c96c42e86994b6c828b736e1))
* prune public documentation surface ([3e21865](https://github.com/mrsalty/slowave/commit/3e21865b58ac38d5672cb19cab8210589c9b0a87))
* refresh README presentation ([68b2536](https://github.com/mrsalty/slowave/commit/68b25368a8d05b7f4e213acd1ea6cbdee7841bff))
* remove emoji from title ([f62bbd2](https://github.com/mrsalty/slowave/commit/f62bbd2e7ae8f42a508f957d036dd0eb3c250676))
* remove redundant env vars from MCP config snippets ([116702d](https://github.com/mrsalty/slowave/commit/116702d869be5565435499702ebd9308d082e5e6))
* remove stage annotations from benchmark table, use absolute scores only ([78f00c7](https://github.com/mrsalty/slowave/commit/78f00c74fd0b2c7a3ff1d0d0d22458b2ff179da6))
* rename "Install in minutes" to "Install" ([2c3d72f](https://github.com/mrsalty/slowave/commit/2c3d72f2d85d8ecb02d38ea6fd34842c9623687f))
* rewrite benchmark section — highlight achievements, honest gaps ([4e05693](https://github.com/mrsalty/slowave/commit/4e05693e87f708a8121f4f37d51e4f8961c87f74))
* simplify overview flowchart node labels ([9e5e6ed](https://github.com/mrsalty/slowave/commit/9e5e6edfbfefcae13e6a35fa3c1c03726a4e98c6))
* simplify README install path ([5b1b42e](https://github.com/mrsalty/slowave/commit/5b1b42e51d83f23502587f6c6dc717e2dd3f6b5a))
* trim How it works, drop What Slowave is for + Why Slowave is different, signal more clients coming ([8885b3c](https://github.com/mrsalty/slowave/commit/8885b3c79f77c73833849201a654a481bc653aaa))
* update benchmark numbers to Stage 10 actuals ([39791f5](https://github.com/mrsalty/slowave/commit/39791f5cf8db5af495bbe2452fc649a9f475d2e9))
* update benchmark section with grid search tuned results ([d834485](https://github.com/mrsalty/slowave/commit/d8344850d989bd7fc61ffc62dde4d76a597b0475))
* update for 0.1.5 release ([fe2460e](https://github.com/mrsalty/slowave/commit/fe2460ec4b3fe357d4f47f24006ef7781eb162e3))
* update PyPI install instructions ([e88bfd0](https://github.com/mrsalty/slowave/commit/e88bfd05b941451e09677c9fb2a9ad4db054478a))
* update README and install.md for v0.1.8 ([f5e8619](https://github.com/mrsalty/slowave/commit/f5e8619a3a169d3e768fd073a04f67c6f303df0e))

## [0.1.10] - 2026-05-30

### Fixed
- **Claude Desktop:** replaced unreliable Skill filesystem injection with Custom Instructions
  approach. `slowave setup` now prints a single `⚠ REQUIRED` warning with the exact
  Settings path and a link to the instruction block. Skills fired on turn 2+ and were
  reset by Claude Desktop on each launch; Custom Instructions fire before turn 1 and
  persist permanently.
- Removed ~140 lines of dead Skill injection code (`_find_skill_file`,
  `_skills_plugin_base`, `_install_claude_desktop_skill`) from `setup.py`.
- Replaced personal names (`Matteo`) in tests with neutral names (`Alex`).
- Replaced `chamomile tea` demo with `spaghetti` / `what is my favourite food`.

### Changed
- `integrations/claude-desktop/README.md` rewritten: Custom Instructions as Step 1,
  fenced code block with GitHub copy button, explains why Skills don't work for turn 1.
- `slowave setup --client claude-desktop` output: compact warning + link instead of
  a large ASCII box.
- Release workflow unified: PyPI + Homebrew formula update both triggered automatically
  via release-please on PR merge.

## [0.1.9] - 2026-05-30

### Fixed
- `slowave setup` (Claude Desktop): Skill is now installed **automatically** by writing
  directly to Claude Desktop's skills directory — no manual upload required. Falls back to
  manual instructions if the directory is not found (Claude Desktop not yet opened).
- `slowave setup`: stale versioned Homebrew Cellar path (`/opt/homebrew/Cellar/slowave/X.Y.Z/...`)
  is detected and rewritten to the stable symlink on re-run. Fixed in v0.1.8;
  `re-run slowave setup` to repair existing installs.
- Suppress HF Hub unauthenticated-request warning and all progress bars (`Loading weights`,
  download bars) on model load. Both logger level AND handler level must be set after
  `sentence_transformers` import to silence the warning correctly.
- NER tests (`TestExtractRolesNer`) now skip cleanly when `en_core_web_sm` is not installed,
  fixing flaky CI failures.

### Added
- **Brain spinner** (`🧠 ··· loading memory`) during cold model load on any CLI command
  that encodes text. No-op when stderr is not a TTY.
- **Sleep spinner** (`💤 zzZ sleeping (4m 32s)`) during worker idle phase, with countdown.
- **Fancy `slowave stats`** output: emoji rows with salience bars and thousand-formatted counts.
- **Fancy `slowave doctor`** output: emoji per dependency, ✅/❌ status, `✨ all checks passed`.
- **Fancy `slowave recall`** output: schema cards with status dot, salience bar, episode count;
  compact episode list with dates and salience bars.
- `slowave/data/slowave.skill` bundled as package data — available after any install method.

### Changed
- **Documentation restructure**: `docs/install.md` is the single authoritative guide;
  `integrations/` pages are quick-ref cards; `docs/design.md` rewritten as decision record;
  `docs/architecture.md` state machine diagram fixed, stale LLM appendix removed.
- CI matrix dropped from Python 3.10+3.12 to Python 3.12 only (no version-split code).
- Worker output uses emoji timestamps and `🧠`/`💤` markers.

## [0.1.8] - 2026-05-29

### Fixed
- `slowave setup`: use `Path.absolute()` instead of `Path.resolve()` when locating
  `slowave-mcp` and `slowave` binaries. `resolve()` followed Homebrew symlinks into the
  versioned Cellar path (`/opt/homebrew/Cellar/slowave/0.1.7/libexec/bin/slowave-mcp`),
  which broke silently on every `brew upgrade`. The stable symlink
  (`/opt/homebrew/bin/slowave-mcp`) is now preserved in all generated configs.

### Changed
- `requires-python` lifted from `>=3.10,<3.13` to `>=3.10`. All dependencies
  (`torch`, `faiss-cpu`, `sentence-transformers`, `spacy`, `numpy`) ship `cp313` wheels
  as of their current releases. Python 3.13 classifier added.
- `slowave doctor`: removed the hard-coded "Python 3.13 not supported" message.
- `docs/install.md`: requirement updated to `Python 3.10+`.

## [0.1.7] - 2026-05-29

### Added
- **`slowave setup` command** — one-command cross-platform post-install wiring.
  Automates the full setup pipeline in a single invocation:
  - Locates `slowave-mcp` and `slowave` binaries (PATH, pipx, Homebrew, Windows AppData).
  - Patches `~/.claude/settings.json` with the MCP server block.
  - Injects `UserPromptSubmit` + `Stop` enforcement hooks into `~/.claude/settings.json`
    (Claude Code only) — the only mechanism that fires on every turn unconditionally.
  - Injects the mandatory lifecycle block into `~/.claude/CLAUDE.md` (marker-based, idempotent).
  - Patches Claude Desktop MCP config (platform-correct path: macOS / Linux / Windows).
  - Patches Cline `cline_mcp_settings.json` (detects VS Code and Cursor).
  - Injects lifecycle block into `~/.clinerules`.
  - Installs the background worker as a system service:
    launchd plist (macOS), systemd user service (Linux), Task Scheduler task via PowerShell (Windows).
  - Runs `slowave doctor` to verify the result.
  - Flags: `--client all|claude-code|claude-desktop|cline`, `--dry-run`, `--no-worker`, `--no-hooks`.
  - Fully idempotent — re-running is always safe.

### Changed
- `docs/install.md` — TL;DR one-liner (`pipx install slowave && slowave setup`) at top;
  new `## Setup command reference` section with per-platform table.
- `docs/cli.md` — `setup` added to the command reference table.
- `integrations/README.md`, `integrations/claude-code/README.md`,
  `integrations/claude-desktop/README.md` — "Fastest path" one-liner section at top of each.

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
