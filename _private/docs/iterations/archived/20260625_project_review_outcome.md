# Slowave Project Review Outcome — 2026-06-25

## Scope

Reviewed the current Slowave repository globally, including documentation, packaging, CLI/MCP entrypoints, core engine/services/storage modules, and the fast test suite. Performed ad-hoc CLI checks on isolated temporary databases.

## Validation performed

- Repository/docs inspection:
  - `README.md`
  - `CLAUDE.md`
  - `pyproject.toml`
  - `slowave/core/engine.py`
  - `slowave/core/services/*`
  - `slowave/storage/sqlite_db.py`
  - `slowave/cli/main.py`
  - `slowave/mcp/tools.py`
  - `slowave/mcp/server.py`
  - `slowave/mcp/http_server.py`
- Fast tests:
  - `.venv/bin/python -m pytest tests/ -m 'not slow and not benchmark and not requires_model and not requires_faiss' -q`
  - Result: passed.
- Smoke tests:
  - `.venv/bin/python -m pytest tests/unit/test_smoke.py -q -ra`
  - Result: `4 passed`.
- CLI smoke/ad-hoc checks:
  - `slowave --help` works in the project virtualenv.
  - `slowave --json stats` works on an isolated temp DB.
  - `slowave --json doctor` works and reports local integration warnings.
  - Manual `session start` → `event` → `remember` → `session end --consolidate` lifecycle worked on `/tmp/slowave_review_lifecycle.db`.

## Overall assessment

Slowave is in a healthy beta-stage state. The project has a coherent local-first thesis, a cleaner MCP tool surface around the 5-verb cognitive cycle, meaningful tests, migration logic, and practical operational tooling.

The main concerns are not core breakages. They are mostly interface consistency, documentation drift, local-dev ergonomics, and a few product/API sharp edges that matter because Slowave depends on agents following the lifecycle correctly.

## Strengths

1. **Clear architecture and product thesis** — latent geometry performs memory work; symbolic text is the interface; no LLM calls are required for ingest/retrieval/consolidation.
2. **Cleaner MCP lifecycle surface** — `activate`, `remember`, `recall`, `reinforce`, `commit`, and `stats` are easier for agents to follow than the old session/event/context API.
3. **Meaningful fast test suite** — lifecycle, smoke, working-memory context, feedback, generalization, schema utility, transition model, setup, and old-tool deletion paths are covered.
4. **Good local-first operations** — doctor/status/stats, backup/restore, dashboard, daemon/worker support, setup/uninstall/cleanup, and platform-aware docs are present.
5. **Practical SQLite design** — per-thread connections, WAL mode, busy timeout, and migration logic are appropriate for MCP/async/threadpool usage.

## Findings and recommendations

### 1. CLI `recall` lacks scope support

`SlowaveEngine.recall()` and MCP `slowave_recall` support `scope`, and MCP explicitly warns that omitting scope can return memories from all projects. The CLI command `slowave recall` currently exposes only `--top-k` and `--evidence`.

**Impact:** manual CLI recall can accidentally retrieve cross-project memories and does not match MCP behavior.

**Recommendation:** add `--scope` and `--mode` to CLI `recall`, pass them through to `eng.recall(...)`, and update `docs/cli.md`.

### 2. Stats JSON version is ambiguous

`slowave --json stats` reports `"version": "1.0"`, while `slowave.__version__`, package metadata, and `doctor` report `0.7.0`.

**Impact:** consumers may confuse payload schema version with package version.

**Recommendation:** rename to `payload_version` or add both `package_version` and `payload_version`.

### 3. Documentation drift around procedural memory

`CLAUDE.md` still references `ProceduralMemoryStore` / `procedural.py` and procedural tests that no longer exist after Phase 1 P1, while current architecture treats procedural behavior as implicit via schemas, prototypes, TransitionModel, and spreading activation.

**Impact:** future agents and contributors may search for removed modules or misunderstand the current design.

**Recommendation:** update the architecture/testing sections to reflect the implicit procedural-memory design.

### 4. CLI lifecycle/debugging ergonomics are uneven

The manual CLI lifecycle works, but CLI recall does not return `retrieval_id`, and CLI commands do not mirror the full MCP lifecycle semantics.

**Impact:** harder to debug reinforce/commit behavior from CLI alone.

**Recommendation:** either add CLI aliases for activate/reinforce/commit semantics, or document clearly that CLI recall is inspection-only and MCP is the lifecycle surface.

### 5. Dev setup docs do not match current venv

Formatting commands in `CLAUDE.md` reference Black/isort, but the current project venv did not include either module.

**Impact:** contributors following the docs cannot run formatting without extra setup knowledge.

**Recommendation:** document the canonical dev install command, e.g. `pip install -e '.[dev]'` or the equivalent `uv` command.

### 6. FAISS test marker appears unused

`requires_faiss` is defined/documented, but no tests appear to be marked with it.

**Impact:** the documented FAISS-specific test command may not provide useful signal.

**Recommendation:** either add marked FAISS tests or remove/adjust the separate command from docs.

### 7. `doctor` may mix temp DB checks with user-level daemon state

When run with `SLOWAVE_DB=/tmp/...`, `doctor` uses the temp DB for runtime info but still reports the user-level running daemon/worker.

**Impact:** users may debug the wrong DB/daemon combination.

**Recommendation:** include daemon DB path in health output when available and warn if it differs from the current CLI DB.

## Suggested priority order

1. Add `--scope` and `--mode` to `slowave recall`.
2. Clarify stats JSON version fields.
3. Update stale procedural-memory documentation.
4. Update dev setup instructions for Black/isort.
5. Reconcile the `requires_faiss` marker/docs.
6. Improve `doctor` DB/daemon consistency reporting.

## Outcome

No blocking correctness failures were found in the fast test suite or basic CLI lifecycle. The highest-impact next work is interface/documentation alignment so MCP, CLI, docs, and engine all tell the same scoped-memory lifecycle story.