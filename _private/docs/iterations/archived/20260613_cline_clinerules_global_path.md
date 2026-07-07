# Cline TUI — `~/.clinerules` is not a global rules path (Bug 7)
**Date:** 2026-06-13  
**Version affected:** 0.5.4 and earlier  
**Reported by:** end-user matte (Windows, Cline TUI)  

---

## Symptoms

After installing 0.5.4 (MCP tool name fix):

1. **MCP green dot** — server connects correctly, tools are now named `slowave_activate` etc.
2. **No autonomous calls** — Cline TUI still never calls `slowave_activate` at task start; no cold-start, no lifecycle.
3. `slowave doctor` reports `✓ Cline: MCP, lifecycle` — both files exist.
4. `slowave doctor` reports `Sessions started: 0` — no `slowave_activate` has ever been called.
5. User has to explicitly ask Cline about slowave before anything happens.

---

## Root cause

`_clinerules_path()` in `setup.py` returned `~/.clinerules`. This is the correct location for the **VS Code extension** version of Cline (where it is a global rules file), but it is **not globally read by Cline TUI**.

### What Cline TUI actually reads

Confirmed by inspecting `@cline/shared` dist (`resolveRulesConfigSearchPaths`):

```
resolveRulesConfigSearchPaths('/repos/myproject') →
  [
    '/repos/myproject/AGENTS.md',            ← project cwd
    '/repos/myproject/.clinerules',           ← project cwd
    '/repos/myproject/.cline/rules',          ← project cwd
    '~/.agents/AGENTS.md',                   ← global
    '~/.cline/rules',                        ← global rules DIRECTORY
    '~/Documents/Cline/Rules',               ← global rules DIRECTORY
  ]
```

`~/.clinerules` is only scanned when the user runs `cline` from their home directory (`cwd == home`). In all other cases — cwd is a project like `C:\repos\cve-risk-score-prediction` — `~/.clinerules` is never read.

The global rules mechanism for Cline TUI is `~/.cline/rules/` (a **directory**). Any `.md` file placed in that directory is loaded globally into every session.

### Impact

- `slowave setup` wrote the lifecycle block to `~/.clinerules` — file exists, doctor confirms it, but Cline TUI never reads it when cwd is a project directory.
- LLM starts each task with no knowledge of `slowave_activate` → no cold-start, no memory, no lifecycle.
- This was masked in earlier testing by the tool name mismatch (Bug 6) — both bugs were present simultaneously.

### Why doctor reports `✓ Cline: lifecycle`

`clients.py` checks whether `_MARKER_START` is in `_clinerules_path()`. After the fix, if the user ran `slowave setup` before 0.5.5, `~/.clinerules` still exists and still has the marker, so doctor still reports `✓`. After running `slowave setup` with 0.5.5, it moves to `~/.cline/rules/slowave.md` and doctor will correctly check the new path.

---

## Fix

**File:** `slowave/cli/setup.py` — `_clinerules_path()`

```python
# BEFORE (broken — VS Code extension path, not read globally by TUI):
def _clinerules_path() -> Path:
    return _home() / ".clinerules"

# AFTER (fixed — global rules directory read by Cline TUI):
def _clinerules_path() -> Path:
    return _home() / ".cline" / "rules" / "slowave.md"
```

`~/.cline/rules/` is the global rules directory for Cline TUI (`RULES_CONFIG_DIRECTORY_NAME = "rules"`). Any `.md` file placed there is loaded into every session. Writing `slowave.md` into that directory ensures the lifecycle block is always present, regardless of which project directory the user is in.

The cleanup path (`_strip_file` in `cleanup.py`), doctor check (`clients.py`), and lifecycle injection logic (`_inject_block` in `setup.py`) all derive their path from `_clinerules_path()` — no other changes needed.

---

## Verification

```bash
# After slowave setup:
ls ~/.cline/rules/slowave.md          # must exist
cat ~/.cline/rules/slowave.md | head  # must contain <!-- slowave-lifecycle-start
```

On Windows:
```powershell
Get-Content "$env:USERPROFILE\.cline\rules\slowave.md" | Select-Object -First 5
```

---

## Notes on `~/.clinerules` (old path)

- Files written by slowave ≤ 0.5.4 at `~/.clinerules` are not automatically migrated by `slowave setup` — setup is idempotent, it will write the lifecycle block to the new path and leave the old file untouched.
- Running `slowave cleanup` removes the block from `~/.clinerules` (if it exists) AND from the new `~/.cline/rules/slowave.md`.
- Users upgrading from ≤ 0.5.4 should run `slowave setup` to write to the correct path.

---

## Summary table

| # | Sev | File | Issue | Status |
|---|-----|------|-------|--------|
| 7 | **Critical** | `cli/setup.py` | `_clinerules_path()` returns `~/.clinerules` — not read globally by Cline TUI; lifecycle block never injected when cwd ≠ homedir | ✅ Fixed — write to `~/.cline/rules/slowave.md` |

---

## Release tracking

### 0.5.5 — 2026-06-13

**Status:** Fixed in source ✅

| Artefact | Value |
|---|---|
| Bug introduced | ≤ 0.5.4 (present since initial Cline TUI support) |
| Fix commit | pending release |
| Files changed | `slowave/cli/setup.py` (`_clinerules_path()`), `pyproject.toml`, `CHANGELOG.md` |

**Note:** 0.5.4 (MCP tool name fix) and 0.5.5 (clinerules global path fix) should be released together or 0.5.5 should supersede 0.5.4. Both bugs were present simultaneously in ≤ 0.5.3 and make Cline TUI non-functional.
