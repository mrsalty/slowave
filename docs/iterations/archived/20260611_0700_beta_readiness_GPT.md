# Slowave Codebase Review

## Executive verdict

Slowave is **well beyond prototype quality conceptually**, but **not yet clean beta/public-release quality operationally**.

The strongest signal is that this is not just “vector search with a README.” The repository has:

- a coherent product thesis: **local, zero-LLM, adaptive memory for AI tools**;
- a real Python package with CLI/MCP entry points;
- SQLite schema with episodic, semantic, procedural, feedback, evidence, and relation tables;
- FAISS-based retrieval layer;
- working-memory gating;
- explicit feedback/reinforcement path;
- procedural memory support;
- benchmark harnesses for LoCoMo / LongMemEval / temporal tests;
- good docs and public-positioning material.

The main issue is that the project currently feels like a **fast-evolving research/product codebase that has accumulated release debris, duplicated concepts, strong claims, and some rough operational edges**. That is normal at this stage, but before going more public I would do a stabilization pass.

---

## 1. Overall product positioning

### What is strong

The core positioning is genuinely good:

> A second brain for your AI, shared across every tool.

That is clearer than “memory system,” “agent memory,” or “brain-inspired substrate.” The public README quickly communicates the practical value: one local memory store across Claude Code, Cline, Cursor, Windsurf, Claude Desktop, and other MCP-compatible tools.

The strongest differentiators are:

1. **Cross-tool shared memory**
2. **Local-first / private**
3. **No LLM in the memory loop**
4. **Adaptive mechanics: salience, decay, reinforcement, supersession**
5. **Procedural memory**
6. **Compact working-memory injection instead of replaying history**

That is a good hierarchy. Keep leading with the user-facing benefit, not the neuroscience.

### What is risky

Some claims are currently too absolute.

Examples:

- “Works across every AI tool, zero setup”
- “They don’t learn. They don’t forget.”
- “Outdated facts auto-superseded ✅”
- “Procedural memory ✅”
- “Competitive or better than LLM-based memory systems”
- “Slowave learns workflows”

These are directionally fine, but in public they invite criticism unless backed by precise definitions.

I would soften some README wording:

```md
Works across MCP-compatible AI tools
```

instead of:

```md
Works across every AI tool, zero setup
```

And:

```md
Supports usage-based reinforcement, decay, and supersession heuristics
```

instead of implying human-like learning or fully reliable contradiction resolution.

The project can still sound exciting without overclaiming.

---

## 2. Architecture review

### Strong architecture choices

The layered architecture is good:

```text
raw events
  → episodes
  → prototypes
  → schemas
  → recall/context brief
  → feedback
```

The separation between:

- episodic memory;
- semantic prototypes/schemas;
- procedural memory;
- feedback/reinforcement;
- working-memory gating;

is exactly the right shape for Slowave.

The SQLite schema is also more mature than expected. It includes:

- `sessions`
- `raw_events`
- `episodic_memories`
- `episode_text`
- `semantic_prototypes`
- `prototype_edges`
- `schemas`
- `schema_evidence`
- `schema_prototype_map`
- `schema_relations`
- `context_recall_events`
- `context_recall_items`
- procedural memory tables
- worker runs
- FTS tables

That is a strong foundation.

### Main architectural concern

The system currently mixes **research abstractions** and **product abstractions** in the same public surface.

Internally, concepts such as the following are fine:

- CA3/CA1-like prototypes;
- VSA;
- temporal probe;
- geometric contradiction judge;
- latent schema builder;
- replay engine;
- transition model;
- working-memory gate;
- procedural consolidation.

But externally, the user mostly needs:

```text
activate
remember
recall
reinforce
commit
stats
```

The MCP surface is therefore good. Keep the public model simple and hide most biological/latent terminology from default docs.

### Recommended doc split

Keep:

- `README.md` = product value;
- `docs/install.md` = setup;
- `docs/architecture.md` = practical architecture;
- `docs/design.md` = philosophy / brain-inspired rationale;
- `docs/benchmarks.md` = careful evaluation;
- `docs/limitations.md` = honest caveats.

But make sure the README does not overexpose internals.

---

## 3. Codebase structure

The repository has around:

- **53 Python source files**;
- **37 test files**;
- about **14k lines of Python**;
- large modules:
  - `dashboard/app.py` ~1966 lines;
  - `cli/setup.py` ~1142 lines;
  - `cli/main.py` ~1099 lines;
  - `symbolic/schema_store.py` ~945 lines;
  - `core/procedural.py` ~644 lines;
  - `mcp/server.py` ~630 lines;
  - `core/engine.py` ~590 lines.

### Good signs

The recent service extraction is the right direction:

```text
slowave/core/services/ingest.py
slowave/core/services/retrieval.py
slowave/core/services/consolidation.py
slowave/core/services/feedback.py
```

That makes `SlowaveEngine` more of a facade, which is good.

### Main maintainability issue

Several modules are too large and too central.

#### `dashboard/app.py`

At roughly 1966 lines, this should be split into:

```text
dashboard/app.py
dashboard/routes/overview.py
dashboard/routes/schemas.py
dashboard/routes/procedures.py
dashboard/routes/worker.py
dashboard/templates.py
dashboard/queries.py
dashboard/processes.py
```

#### `cli/setup.py`

At roughly 1142 lines, this is also too large, especially because it modifies user config files and installs services.

Split into:

```text
cli/setup.py
setup/clients/claude_code.py
setup/clients/claude_desktop.py
setup/clients/cline.py
setup/clients/cursor.py
setup/clients/windsurf.py
setup/services/launchd.py
setup/services/systemd.py
setup/services/windows_task.py
setup/summary.py
setup/patching.py
```

This is important because setup is a trust-critical path. Users need confidence that it will not corrupt their config.

#### `schema_store.py`

This is a major domain object and currently handles too many responsibilities:

- creation;
- dedupe;
- reinforcement;
- FTS;
- evidence;
- relations;
- decay;
- health;
- exact dedup;
- status update.

It should eventually be split into smaller store/services, but this is less urgent than setup/dashboard.

---

## 4. Packaging / release hygiene issues

This is the most immediate cleanup area.

The archive contains many files that should not be committed or shipped:

```text
__MACOSX/
.DS_Store
__pycache__/
*.pyc
slowave.egg-info/
```

This is a public-release blocker. It makes the project look unpolished and can accidentally leak local environment details.

Add or verify `.gitignore` contains:

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
.DS_Store
__MACOSX/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
dist/
build/
.env
.venv/
data/runs/
data/*/debug_dbs/
```

Also check your PyPI source distribution / wheel to ensure these files are excluded.

### Version mismatch

This is a concrete bug:

`pyproject.toml` says:

```toml
version = "0.4.9"
```

but `slowave/__init__.py` says:

```python
__version__ = "0.1.18"
```

That must be fixed before release.

Prefer one source of truth. For example, use package metadata at runtime instead of duplicating:

```python
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("slowave")
except PackageNotFoundError:
    __version__ = "0.0.0"
```

### Import side effects

`slowave/__init__.py` imports:

```python
from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
```

This means importing `slowave` pulls in the engine, which pulls in heavy dependencies such as FAISS, ONNX/runtime-related code, and model-related code.

That makes even simple things like this fragile:

```python
import slowave
print(slowave.__version__)
```

I would change `__init__.py` to avoid importing the full engine eagerly.

---

## 5. Dependency / test issue

I tried running the unit tests. Test collection failed because `slowave` could not be imported, ultimately due to missing runtime dependency `faiss`.

The visible pytest error was:

```text
ModuleNotFoundError: No module named 'slowave'
```

but a direct Python import showed the underlying issue:

```text
ModuleNotFoundError: No module named 'faiss'
```

This is likely because the current environment does not have `faiss-cpu` installed. Since `pyproject.toml` includes:

```toml
faiss-cpu>=1.7
```

that may be fine after a proper install, but two points remain:

1. The test error is confusing because heavy import happens at package import time.
2. Tests should have a lightweight path that can run without loading the full encoder/FAISS stack where possible.

Recommended actions:

- avoid heavy imports in `slowave/__init__.py`;
- add a `tests/conftest.py` if needed for path/import setup;
- document the test command.

Example:

```bash
uv sync --all-extras
uv run pytest
```

or:

```bash
pip install -e ".[dev]"
pytest
```

Later, consider splitting dependencies into extras:

```text
slowave[core]
slowave[dashboard]
slowave[benchmarks]
slowave[dev]
```

---

## 6. MCP API review

The MCP API shape is good.

Current exposed tools:

```text
activate
recall
remember
remember_procedure
reinforce
commit
stats
```

This is much better than exposing low-level primitives like session start/end/event append.

The cognitive cycle is understandable:

```text
activate → remember / recall → reinforce → commit
```

### Strong point

`activate` automatically opens/binds a session. That removes friction.

### Risk

The MCP server caches engines globally:

```python
_ENGINES: dict[tuple[bool], SlowaveEngine] = {}
```

This is probably fine for a local MCP server, but I would document the concurrency assumptions and make sure SQLite access is safe under concurrent MCP calls.

Potential issue: a full engine and encoder-disabled engine can share the same DB. That is intentional, but you need to be careful about index refresh timing and writes from one engine not being reflected in the other until refresh.

You already refresh indices in retrieval, which helps.

### Naming

The final public verbs are good. Keep them.

Do not expose old names again:

```text
slowave_context
slowave_session_start
slowave_session_end
slowave_event
```

The simplified surface is much more product-ready.

---

## 7. Setup / installer review

`slowave setup` is one of the highest-value features, but also one of the highest-risk parts.

It modifies:

- Claude Code config;
- Claude Desktop config;
- Cline config;
- Cursor MCP config/rules;
- Windsurf config/rules;
- shell/service files;
- launchd/systemd/Windows scheduled tasks.

That is powerful, but users will be nervous.

### What you need before wider release

Add a very strong setup safety story:

```bash
slowave setup --dry-run
slowave setup --backup
slowave setup --yes
slowave setup --only claude-code
slowave setup --skip-worker
slowave cleanup --dry-run
```

Some of this may already exist partially, but the README should make it obvious.

The setup command should always:

- create timestamped backups before modifying files;
- print exact file paths modified;
- be idempotent;
- support dry run;
- support uninstall/cleanup;
- never overwrite unknown user content without markers;
- preserve JSON formatting as much as possible;
- fail safely on malformed existing config.

The code appears to have summaries and idempotence logic, which is good. But because this is a trust-critical path, it deserves dedicated tests with temporary home directories.

---

## 8. Storage schema review

The schema is ambitious and mostly well thought out.

### Strong choices

The following tables are especially valuable:

```text
schema_evidence
schema_relations
schema_prototype_map
context_recall_events
context_recall_items
worker_runs
procedural_memories
```

This gives you provenance, inspectability, and a base for adaptive memory.

### Concern

There is no obvious formal migration system yet, beyond schema creation and a migration SQL file:

```text
scripts/migrations/20260610_cleanup_sessions.sql
```

For public users, DB migrations become important quickly.

Recommended next step:

```text
slowave/storage/migrations/
  0001_initial.sql
  0002_feedback.sql
  0003_procedural.sql
```

and a table:

```sql
schema_migrations(
    version TEXT PRIMARY KEY,
    applied_at INTEGER NOT NULL
)
```

Then `slowave doctor` can report DB schema version.

Without this, early users can get broken local DBs after upgrades.

---

## 9. Benchmark / claims review

The benchmark docs are honest in some places, especially where they mention scorer differences. That is good.

But the README benchmark table is still risky.

Current README says:

```text
LoCoMo: Slowave 83.5%, Zep 75.1%, LangMem 58.1%, GPT-4 fine-tuned ~76%
LongMemEval: Slowave 93.4%, Mem0 94.4%
```

Then it says:

```text
The 1 pp LME gap is within the expected scorer difference — on the same dataset with the same scorer, results are likely at parity.
```

I would remove or soften “likely at parity” from the README. It is an inference, not a measured result.

Use:

```md
Because Slowave and competitor results use different scoring protocols, these numbers should be read as directional rather than directly comparable.
```

You can still say:

```md
The key result is that Slowave reaches high recall quality without LLM calls.
```

That is defensible and still impressive.

### Benchmark maturity

The presence of benchmark harnesses is excellent. But for public credibility, add a single reproducible command:

```bash
slowave benchmark token-efficiency
slowave benchmark synthetic-temporal
slowave benchmark longmemeval --sample 100
```

And a generated report artifact:

```text
data/runs/<timestamp>/report.json
data/runs/<timestamp>/summary.md
```

You may already have parts of this, but it should be very clear from docs.

---

## 10. Docs review

The docs are a major strength.

The README is attractive and communicates value. `design.md` and `architecture.md` are conceptually strong.

### Improvement: reduce repetition

The phrase “zero LLM calls” appears everywhere. It is central, but repeated too much. Keep it prominent in README and design, but avoid repeating it in every paragraph.

### Improvement: split “brain-inspired” from “brain-equivalent”

You are mostly careful, but I would be even more explicit:

```md
Slowave is brain-inspired, not a biological model of memory.
```

This protects you from criticism from neuroscience-oriented readers.

### Improvement: sharper limitations

The limitations doc should be linked near the benchmark section and should clearly say:

- no reasoning layer;
- no implicit preference inference unless explicitly encoded;
- no guarantee of contradiction detection;
- local DB not designed for multi-user/cloud deployment yet;
- English-first / embedding-model dependent;
- benchmark comparisons are not independently audited;
- setup modifies local AI tool configs.

That honesty will increase trust.

---

## 11. Security / privacy review

### Positive

The local-first privacy story is strong. Storing at:

```text
~/.slowave/slowave.db
```

is simple and understandable.

### Risks to address

#### Local dashboard

`slowave dashboard` should bind to:

```text
127.0.0.1
```

by default, which it appears to do. Good.

But docs should explicitly warn against binding to `0.0.0.0` unless the user knows what they are doing.

#### Sensitive memory

A local memory store can accumulate secrets. You need commands like:

```bash
slowave search
slowave delete schema <id>
slowave delete scope project:x
slowave purge
slowave export
slowave redact
```

Some cleanup exists, but privacy controls should become a product feature.

#### Setup trust

Because setup modifies several app config files, add a “what gets modified” page with exact paths. You already have `docs/slowave_setup.md`; make this extremely explicit.

---

## 12. Testing review

The number of tests is a good sign.

You have tests for:

- engine recall/consolidation;
- working memory;
- procedural memory;
- schema utility/dedup;
- session resolver/reaper;
- VSA;
- transition model;
- token efficiency;
- integration benchmarks.

### Missing / needed tests

Highest priority:

1. setup idempotence tests using temporary fake home directories;
2. config patching tests for malformed JSON;
3. migration tests;
4. MCP tool lifecycle test:

```text
activate → remember → recall → reinforce → commit
```

5. concurrency test for simultaneous MCP calls;
6. dashboard smoke test;
7. install/import test:

```python
import slowave
print(slowave.__version__)
```

without forcing model/FAISS initialization.

---

## 13. Top concrete issues found

### Critical before broader public release

1. **Clean repository/distribution artifacts**
   - remove `__MACOSX`, `.DS_Store`, `__pycache__`, `.pyc`, `.egg-info`.

2. **Fix version source of truth**
   - `pyproject.toml`: `0.4.9`;
   - `slowave/__init__.py`: `0.1.18`.

3. **Avoid heavy imports in `slowave/__init__.py`**
   - importing `slowave` should not require FAISS/model stack.

4. **Add formal migration/versioning story for SQLite**
   - important once users install and upgrade.

5. **Soften benchmark/comparison claims**
   - keep strong claims, but make scorer differences impossible to miss.

6. **Strengthen setup safety**
   - dry-run, backup, exact diff/summary, cleanup, idempotence tests.

### Important but not blocking

7. Split large modules:
   - `dashboard/app.py`;
   - `cli/setup.py`;
   - `cli/main.py`;
   - eventually `schema_store.py`.

8. Add a public “threat/privacy model” doc.

9. Add one canonical benchmark command and generated report format.

10. Add more lifecycle-level MCP tests.

### Nice-to-have

11. Optional dependencies:
   - dashboard extras;
   - benchmark extras;
   - dev extras.

12. Improve public terminology:
   - less “brain” in README;
   - more “shared local memory for AI tools”.

13. Add architecture diagram as stable SVG/PNG rendered from Mermaid or a source-controlled diagram file.

---

## 14. Current assessment of Slowave’s state

I would classify it as:

```text
Research/product alpha with unusually strong concept and credible architecture.
Not yet polished beta.
Not yet clean enough for aggressive public launch.
Very close to a controlled public alpha.
```

The project’s best current move is not “add more mechanisms.” It is:

```text
stabilize, clean, verify, simplify public surface, and make claims defensible.
```

You already have enough interesting mechanisms. The risk now is dilution and credibility loss from rough edges.

---

## 15. Recommended next iteration plan

### Phase 1 — Release hygiene

Do this first:

```text
- clean repo artifacts
- fix version source of truth
- clean import side effects
- ensure package install works from fresh venv
- ensure unit tests run with documented command
```

### Phase 2 — Setup trust

```text
- test setup against fake home dirs
- make dry-run output excellent
- ensure backups
- document exact modified files
- test cleanup
```

### Phase 3 — Claims hardening

```text
- soften benchmark comparison language
- move aggressive competitor comparison deeper into docs
- strengthen limitations
- add reproducibility command
```

### Phase 4 — Codebase maintainability

```text
- split dashboard
- split setup
- add migration system
- add lifecycle MCP integration test
```

### Phase 5 — Public alpha

```text
- publish as “developer alpha”
- ask for install feedback
- target Claude Code / Cline / Cursor users first
- show one killer demo: same memory reused across two tools
```

---

## Bottom line

Slowave’s concept is strong and the codebase has real substance. The core direction is worth continuing.

The next best improvement is not another cognitive mechanism. It is a **release-readiness hardening pass**: clean packaging, safer setup, reproducible tests, cautious benchmark language, and a simpler public story.

The product should be presented as:

> **A local shared memory layer for AI tools that remembers, recalls, reinforces, decays, and reuses workflows without LLM calls.**

That is credible, distinctive, and strong enough.

---

## Beta Readiness Checklist

Use this as a practical gate before calling Slowave a public beta rather than a developer alpha.

### 1. Repository and packaging hygiene

- [ ] Remove accidental files from the repository/archive: `__MACOSX/`, `.DS_Store`, `__pycache__/`, `*.pyc`, `*.egg-info/`.
- [ ] Verify `.gitignore` excludes generated files, local databases, build artifacts, caches, virtual environments, benchmark run outputs, and secrets.
- [ ] Ensure the source distribution and wheel do not contain local/generated artifacts.
- [ ] Fix package version mismatch between `pyproject.toml` and runtime `slowave.__version__`.
- [ ] Use a single version source of truth.
- [ ] Confirm a clean install works from a fresh virtual environment.
- [ ] Confirm `pip install slowave` and/or `uv tool install slowave` behave as documented.
- [ ] Confirm CLI entry points are available after installation: `slowave`, `slowave-dashboard`, and any documented worker command.

### 2. Import and dependency robustness

- [ ] Make `import slowave` lightweight and free from FAISS/model initialization side effects.
- [ ] Ensure `slowave.__version__` can be read without importing the full engine stack.
- [ ] Provide clear error messages for missing optional or platform-specific dependencies.
- [ ] Separate optional dependencies where useful: dashboard, benchmarks, dev/test tooling.
- [ ] Document supported Python versions and operating systems.
- [ ] Test on macOS, Linux, and Windows if Windows is advertised.

### 3. Test and quality gate

- [ ] Provide one canonical test command in the README or contributing docs.
- [ ] Ensure unit tests pass from a clean checkout.
- [ ] Ensure integration tests are clearly marked and can be skipped separately.
- [ ] Add a smoke test for the full MCP lifecycle: `activate → remember → recall → reinforce → commit`.
- [ ] Add setup/idempotence tests using temporary fake home directories.
- [ ] Add malformed-config tests for supported clients.
- [ ] Add dashboard startup smoke test.
- [ ] Add migration tests for existing user databases.
- [ ] Add a basic concurrent access test for local MCP calls.
- [ ] Add CI that runs linting, type checks where applicable, unit tests, and packaging validation.

### 4. Setup and uninstall safety

- [ ] `slowave setup --dry-run` shows exactly what would change.
- [ ] Setup creates timestamped backups before modifying user config files.
- [ ] Setup is idempotent when run multiple times.
- [ ] Setup preserves unknown user config entries.
- [ ] Setup handles malformed JSON/config files safely.
- [ ] Setup can target individual clients, for example `--only claude-code` or equivalent.
- [ ] Cleanup/uninstall can remove Slowave MCP entries without damaging user config.
- [ ] Cleanup/uninstall has a dry-run mode.
- [ ] Documentation lists every file path that setup may modify.
- [ ] Documentation explains how to manually undo setup changes.

### 5. Database and migrations

- [ ] Add a formal schema migration system.
- [ ] Add a `schema_migrations` table or equivalent version tracking.
- [ ] Ensure upgrades preserve existing user memories.
- [ ] Add backup guidance before schema migrations.
- [ ] Add `slowave doctor` or equivalent diagnostics for database health.
- [ ] Add repair/reindex commands for corrupted or stale vector/FTS indexes.
- [ ] Test migration from at least the previous public release.

### 6. Privacy and local security

- [ ] Clearly document where data is stored by default.
- [ ] Clearly document what data Slowave stores.
- [ ] Add or document commands for deleting memories by ID, project/scope, or full purge.
- [ ] Add export functionality or document the existing export path.
- [ ] Add redaction guidance for secrets accidentally stored in memory.
- [ ] Ensure the dashboard binds to `127.0.0.1` by default.
- [ ] Warn users before binding the dashboard to non-localhost interfaces.
- [ ] Document the local threat model.
- [ ] State clearly that Slowave is local-first, not a hardened multi-user server.

### 7. MCP/API stability

- [ ] Freeze the beta MCP tool names and argument shapes.
- [ ] Keep the public MCP surface small: `activate`, `remember`, `recall`, `remember_procedure`, `reinforce`, `commit`, `stats`.
- [ ] Document each MCP tool with examples.
- [ ] Define backward-compatibility expectations for future MCP changes.
- [ ] Ensure old/deprecated tool names are either removed or explicitly marked as legacy.
- [ ] Add machine-readable examples for MCP clients where useful.

### 8. Documentation readiness

- [ ] README has a clear 30-second explanation of what Slowave does.
- [ ] README has a minimal install path.
- [ ] README has a minimal first-use path.
- [ ] README distinguishes developer alpha, beta, and stable expectations.
- [ ] Architecture docs explain practical components without overloading new users with neuroscience terminology.
- [ ] Design docs contain the deeper brain-inspired philosophy.
- [ ] Limitations are explicit and easy to find.
- [ ] Troubleshooting docs cover common install, setup, FAISS, MCP, and dashboard issues.
- [ ] Add screenshots or a short GIF for the main dashboard/demo flow.
- [ ] Add a “what gets modified by setup” page.

### 9. Benchmark and claims readiness

- [ ] Benchmark claims are marked as internal/directional unless independently reproduced.
- [ ] Competitor comparisons clearly state differences in scorer, dataset split, setup, and protocol.
- [ ] Avoid saying “parity” unless measured under the same benchmark protocol.
- [ ] Provide at least one reproducible benchmark command.
- [ ] Store benchmark run artifacts in a predictable output folder.
- [ ] Include benchmark metadata: date, version, dataset, sample size, scorer, model, hardware, and config.
- [ ] Separate product-value metrics from academic benchmark metrics.
- [ ] Include token-efficiency demos because they are central to Slowave’s practical value.

### 10. Product UX readiness

- [ ] The default workflow works without users understanding internals.
- [ ] Error messages suggest concrete fixes.
- [ ] `slowave stats` gives useful high-level health information.
- [ ] `slowave doctor` or equivalent reports setup, DB, worker, MCP, and dependency status.
- [ ] Dashboard shows memory health, schemas, recalls, feedback, procedures, and worker status clearly.
- [ ] Dashboard does not require unsafe defaults or hidden configuration.
- [ ] First-run experience explains what to do next after installation.

### 11. Code maintainability readiness

- [ ] Split `dashboard/app.py` into smaller modules.
- [ ] Split `cli/setup.py` into client-specific and platform-specific modules.
- [ ] Reduce `cli/main.py` into smaller command groups.
- [ ] Gradually split `schema_store.py` by responsibility.
- [ ] Keep `SlowaveEngine` as a facade rather than a god object.
- [ ] Add docstrings or module-level comments for non-obvious cognitive/latent mechanisms.
- [ ] Keep public names stable and internal names free to evolve.

### 12. Public beta launch gate

Slowave is ready to be called beta when all of the following are true:

- [ ] Fresh install works on at least macOS and Linux.
- [ ] Setup can be run, inspected, reversed, and rerun safely.
- [ ] Unit tests pass in CI.
- [ ] A full MCP lifecycle test passes in CI or a documented integration test.
- [ ] Existing local databases can survive an upgrade.
- [ ] README claims are defensible and not overstated.
- [ ] Limitations are explicit.
- [ ] Users can delete/export their memory.
- [ ] One compelling cross-tool demo is documented.
- [ ] At least one external user can install and use Slowave without direct help.

