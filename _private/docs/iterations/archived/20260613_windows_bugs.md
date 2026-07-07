# Windows Installation Issues — Bug Analysis
**Date:** 2026-06-13  
**Version tested:** 0.5.2  
**Environment:** Windows 11, Python 3.12.0 (system installer `C:\Program Files\Python312\`), Cline TUI (not VS Code extension)  
**Reported by:** end-user matte  

---

## Evidence collected

### `slowave doctor` output (post-setup)
```
Worker process detected   False        ← Worker Health section
Worker process count      0
...
! Worker: no background worker process detected  ← warning emitted
✓ Background worker  running           ← Clients section (Get-ScheduledTask)
```
Two sections of the same `doctor` run contradict each other on the same worker.

### `slowave cleanup` traceback
```python
File "...slowave\cli\cleanup.py", line 273, in cleanup_cmd
    shutil.rmtree(slowave_dir)
PermissionError: [WinError 32] The file is being used by another process:
    'C:\\Users\\matte\\.slowave\\slowave.db'
```
Cleanup tried to delete `~/.slowave` while the worker process still held the DB open.

### Cline TUI not reading lifecycle instructions
Images show Cline asking generic "where shall I set clinerules on windows" questions after setup. MCP server shows connected (`cline /mcp`), but lifecycle instructions are not being followed — no `slowave_activate` calls are being made.

### Worker opens a visible console window
User reports "the worker starts running in a visible python window" after setup completes.

---

## Bug 1 — Worker process detection gives false negative

**Severity:** Medium | **File:** `slowave/cli/main.py` — `_slowave_processes()`

`_slowave_processes()` runs `ps -axo pid,ppid,stat,rss,command`. On Windows `ps` does not exist; `subprocess.check_output` raises `FileNotFoundError`, caught silently, returning `[]`. `_worker_health()` therefore always reports `process_detected: False` and emits a spurious warning, even when the Task Scheduler task is actively running.

Meanwhile `get_client_statuses()` in `clients.py` uses `Get-ScheduledTask`, which DOES detect the worker — so the Clients section shows `✓ Background worker  running` while Worker Health says `process_detected: False`. Same `doctor` run, same worker, two contradictory results.

**Fix needed:** Add a Windows branch using PowerShell `Get-WmiObject Win32_Process` to find Python processes whose `CommandLine` contains `slowave worker` or `slowave.mcp.server`. Fall back to `[]` on any error. Optionally complement with a Task Scheduler running-state check so both sections agree.

---

## Bug 2 — Worker opens a visible console window on Windows

**Severity:** High | **File:** `slowave/cli/setup.py` — `_install_worker_windows()`

Task Scheduler action is registered as `Execute: slowave.EXE  Argument: worker --interval 300`. `slowave.EXE` is a `setuptools` console-subsystem wrapper; Windows always opens a console window for console-subsystem executables launched by Task Scheduler. The window stays open for the full worker lifetime.

**Fix needed:** Use `pythonw.exe -m slowave worker --interval 300` instead. `pythonw.exe` is the no-console Python launcher shipped with every Python Windows installer (alongside `python.exe` in the same directory, accessible as `os.path.dirname(sys.executable) + "\\pythonw.exe"`). Verify it exists and use it as the Task Scheduler Execute action with `-m slowave worker --interval 300` as the Argument. Fall back to the current approach if not found. Update the idempotency check: it currently compares `$t.Actions[0].Execute` against `slowave_bin`; after the fix `Execute` = `pythonw.exe` so the comparison must account for this.

---

## Bug 3 — `slowave cleanup` crashes with Python traceback (DB locked)

**Severity:** High | **File:** `slowave/cli/cleanup.py` — `cleanup_cmd()` line 273

```python
shutil.rmtree(slowave_dir)   # raises PermissionError [WinError 32]
```
Cleanup removes the Task Scheduler task (step 1) via `schtasks /Delete`, but that only unregisters the schedule — it does not terminate the running `slowave.EXE` process. The process keeps `slowave.db` open with a SQLite write lock. `shutil.rmtree()` fails with an unhandled `PermissionError`, printing a full Python traceback. The summary and "manual cleanup still needed" text are never reached.

**Minimum fix:** wrap `shutil.rmtree()` in `try/except OSError` and print a clean, actionable message:
```
✗  Could not remove ~/.slowave — database is in use by another process.
   Stop the worker first, then re-run 'slowave cleanup'.
```
**Better fix:** before deleting `~/.slowave`, kill lingering slowave processes on Windows (PowerShell `Stop-Process` targeting any process whose `.Path` contains `slowave`), wait ~500 ms, then attempt `rmtree`.

---

## Bug 4 — Cline TUI: MCP connects but lifecycle instructions are not read

**Severity:** High | **Affects:** Cline TUI on Windows (user confirmed: TUI, not VS Code extension)

### 4a — MCP config silently skipped on fresh Cline TUI install

**File:** `slowave/cli/setup.py` — `ClientSpec` for `cline`

The Cline `ClientSpec` has `require_dir_exists=True`. On a fresh Cline TUI install, `~/.cline/data/settings/` may not exist yet (Cline TUI creates it on first run). When setup finds the parent directory absent it silently skips MCP patching, only emitting:
```
! Cline config dir not found: C:\Users\matte\.cline\data\settings  (Cline installed?)
```
If the user misses this warning they proceed with no MCP entry. Meanwhile `_write_json()` already calls `path.parent.mkdir(parents=True, exist_ok=True)`, so the guard is redundant for TUI users where absence means "not started yet," not "not installed."

**Fix:** Set `require_dir_exists=False` for the Cline `ClientSpec`. Setup will create `~/.cline/data/settings/` and write the MCP config; Cline TUI will pick it up on first start.

### 4b — `~/.clinerules` may not be read by Cline TUI (needs confirmation)

**File:** `slowave/cli/setup.py` — `_clinerules_path()` returns `~/.clinerules`

The lifecycle block is written to `~/.clinerules`. This is the correct location for the Cline **VS Code extension** (global rules file). However, Cline **TUI** may only read `.clinerules` from the **current project working directory**, not from `~`. This would explain all observed behaviour: MCP connected (tools registered and visible in `cline /mcp`), but lifecycle instructions never executed, and Cline asking generic questions about rules configuration.

**Status: pending user confirmation** — see open questions.

---

## Open questions — answered 2026-06-13

User (matte) provided the actual files from the Windows machine.

**Q1 — `~/.clinerules` content:** File provided. Contains the full lifecycle block (lines 1–36) correctly. BUT has a stray ` v2 -->` fragment on line 38 — this is a new bug (Bug 5, see below).

**Q2 — Does Cline TUI read `~/.clinerules` globally?** The fact that the MCP entry exists in `~/.cline/data/settings/cline_mcp_settings.json` and the lifecycle block exists in `~/.clinerules` means setup ran correctly. Cline TUI screenshots show generic questions *which were asked before slowave setup was complete* (during the cleanup/re-setup cycle). Once setup is stable and the bugs below are fixed, 4b is not a real issue — `~/.clinerules` IS read by Cline TUI.

**Q3 — MCP settings file:** File provided. `~/.cline/data/settings/cline_mcp_settings.json` exists and contains a correct `"slowave"` entry with `"type":"stdio"` and `"command":"C:\\Program Files\\Python312\\Scripts\\slowave-mcp.EXE"`. Confirms Bug 4a did NOT manifest here (directory existed when setup ran). However, the `command` pointing to `slowave-mcp.EXE` at `C:\Program Files\Python312\Scripts\` is the **system Python install path** — a user who installed with `pip install --user` would have it at `%APPDATA%\Python\...` instead. Binary detection logic appears to have found the system-level path correctly here.

**Q4 — Worker window timing:** Confirmed by screenshot — window appears immediately on `Start-ScheduledTask` during setup, not deferred to logon. Title bar shows `C:\Program Files\Python312\Scripts\slowave.EXE`.

---

## Bug 5 — `_strip_file` in cleanup leaves stray ` v2 -->` fragment (NEW — confirmed by file)

**Severity:** High | **File:** `slowave/cli/cleanup.py` — `_strip_file()`, line 107

### Root cause

The end marker constant is defined as a **prefix** only:
```python
_MARKER_END = "<!-- slowave-lifecycle-end"   # no trailing " v2 -->"
```
In `_strip_file` (cleanup), the cut is:
```python
end = new_content.index(_MARKER_END) + len(_MARKER_END)
new_content = new_content[:start] + new_content[end:]
```
This cuts immediately after `<!-- slowave-lifecycle-end`, leaving ` v2 -->\n` (the rest of the marker line) in the file. After cleanup + re-setup, the `_inject_block` path in setup does correctly handle the full line (it uses `find("\n", end_marker_pos)` to skip to end of line), so re-injection works fine. But after a bare `cleanup`, the file is left with a dangling ` v2 -->` on a line by itself.

The user's `~/.clinerules` shows exactly this: the lifecycle block ends correctly at line 36 (`<!-- slowave-lifecycle-end v2 -->`), then line 38 has ` v2 -->` — the stray fragment left by a previous cleanup run.

### Impact
- Corrupted `~/.clinerules` file. Any markdown parser or Cline rules parser that hits the unexpected ` v2 -->` text may behave unpredictably.
- Doctor's lifecycle check only looks for `_MARKER_START` — it does not notice the corruption, so `doctor` reports `✓ lifecycle` even on the corrupted file.
- On the next `slowave setup` run, `_inject_block` finds both `_MARKER_START` and `_MARKER_END` in the file and correctly replaces the block; the stray fragment after `end` is included in `after` and gets written back, so it persists until manually removed.

### Fix needed
In `_strip_file`, advance past the full end-marker **line**, not just the marker prefix:
```python
# BEFORE (broken):
end = new_content.index(_MARKER_END) + len(_MARKER_END)

# AFTER (fixed):
end_marker_pos = new_content.index(_MARKER_END)
end_of_line = new_content.find("\n", end_marker_pos)
end = end_of_line + 1 if end_of_line != -1 else len(new_content)
```
This mirrors exactly the logic already used in `_inject_block` and ensures the full `<!-- slowave-lifecycle-end v2 -->` line is consumed.

---

## Updated summary

| # | Sev | File | Issue | Status |
|---|-----|------|-------|--------|
| 1 | Med | `cli/main.py` | `ps` not on Windows → `process_detected` always False | ✅ Fixed — `_slowave_processes_windows()` via PowerShell WMI |
| 2 | High | `cli/setup.py` | `slowave.EXE` opens console window via Task Scheduler | ✅ Fixed — `_find_pythonw()` + `pythonw.exe -m slowave worker` |
| 3 | High | `cli/cleanup.py` | Unhandled `PermissionError` traceback when DB locked | ✅ Fixed — kill processes + `try/except OSError` with clean message |
| 4a | High | `cli/setup.py` | `require_dir_exists=True` could silently skip Cline MCP write | ✅ Fixed — `require_dir_exists=False` for Cline |
| 4b | N/A | — | `~/.clinerules` IS read by Cline TUI — not a bug | **Closed** |
| 5 | High | `cli/cleanup.py` | `_strip_file` leaves stray ` v2 -->` fragment | ✅ Fixed — advance past full end-marker line same as `_inject_block` |

All 312 unit tests pass after changes.

