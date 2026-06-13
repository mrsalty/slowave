# PR #7 — Fix/cline lifecycle global path: merge analysis and summary
**Date:** 2026-06-13  
**Branch:** `fix/cline-lifecycle-global-path`  
**PR:** https://github.com/mrsalty/slowave/pull/7  
**Version:** 0.5.5  

---

## Context

Three separate Windows installation issues were tracked across multiple hotfix branches:

| Branch | PR | Release | What it fixed |
|---|---|---|---|
| `fix/windows-setup` | #3, #5 | 0.5.3, 0.5.4 | Worker window, cleanup traceback, process detection, Cline MCP `require_dir_exists`, marker corruption, MCP tool name prefix |
| `fix/dashboard-port-conflict` | (merged into PR#7 branch) | — | Dashboard port-conflict clean error, O(1) status endpoint |
| `fix/cline-lifecycle-global-path` | #7 | 0.5.5 | `_clinerules_path()` returns wrong path for Cline TUI |

---

## Branch divergence at PR open time

When PR #7 was opened, `origin/main` had already advanced via PR#5 (0.5.4) and PR#6 (release bump). The branch forked at `ffcbd93`; main was 5 commits ahead.

| File | Branch HEAD | origin/main | Conflict? |
|---|---|---|---|
| `slowave/cli/setup.py` | `_clinerules_path()` → `~/.cline/rules/slowave.md` | `~/.clinerules` | No — git auto-merged (branch wins) |
| `slowave/dashboard/app.py` | EADDRINUSE fix + O(1) lookup | old version | No — git auto-merged (branch wins) |
| `slowave/mcp/server.py` | bare names (`activate`, …) | `slowave_activate`, … | No — git auto-merged (main wins) |
| `CHANGELOG.md` | 0.5.5 entry at top | 0.5.4 entry at top | **YES** |
| `pyproject.toml` | `version = "0.5.5"` | `version = "0.5.4"` | **YES** |

---

## Conflict resolution

**`pyproject.toml`** — kept `0.5.5` (branch introduces a new fix on top of 0.5.4).

**`CHANGELOG.md`** — merged both sections:
- `0.5.5` entry (HEAD) kept as newest; dashboard fixes from `7753cfd` added to it
- `0.5.4` entry updated to use `origin/main`'s detailed tool-list description
- Duplicate `0.5.4` header from three-way merge removed

**`.release-please-manifest.json`** — auto-merged to `0.5.4`; manually bumped back to `0.5.5`.

---

## What PR #7 ships (0.5.5)

### Bug 7 — `_clinerules_path()` writes to wrong path for Cline TUI (Critical)
**File:** `slowave/cli/setup.py`  
**Iteration doc:** [20260613_cline_clinerules_global_path.md](20260613_cline_clinerules_global_path.md)

`setup.py` wrote lifecycle block to `~/.clinerules`. Read globally by Cline VS Code extension, but **not** by Cline TUI when cwd ≠ home. TUI reads `~/.cline/rules/` (a directory) as its global rules source.

**Fix:** `_clinerules_path()` → `~/.cline/rules/slowave.md`. All downstream code (cleanup, doctor, inject) derives path from same function — no other changes needed.

### Bug A — Dashboard port conflict traceback (Medium)
`ThreadingHTTPServer.__init__` raised raw `OSError` on EADDRINUSE. Now catches `errno 48/98`, prints clean actionable message, exits 1.

### Bug B — Dashboard `/api/status` O(N) subprocess spawning (Low)
Previously spawned one `ps -p <ppid>` per slowave process. Fixed: build `pid→command` dict from single `ps -axo` pass — O(1) lookup. 165ms → 33ms per status call at 71 processes.

---

## Full fix history (Windows bugs 0.5.3 → 0.5.5)

| # | Sev | Bug | Fixed in |
|---|---|---|---|
| 1 | Med | `ps` not on Windows → `process_detected` always False | 0.5.3 |
| 2 | High | Worker opens visible console window | 0.5.3 |
| 3 | High | `slowave cleanup` crashes with `PermissionError [WinError 32]` | 0.5.3 |
| 4a | High | Cline MCP config silently skipped on fresh TUI install | 0.5.3 |
| 5 | High | `_strip_file` leaves stray ` v2 -->` fragment | 0.5.3 |
| 6 | Critical | All 7 MCP tools missing `slowave_` prefix | 0.5.4 |
| A | Med | Dashboard port conflict shows Python traceback | 0.5.5 |
| B | Low | Dashboard `/api/status` O(N) subprocess spawning | 0.5.5 |
| 7 | **Critical** | `~/.clinerules` not globally read by Cline TUI | **0.5.5** |

---

## Post-merge checklist

- [x] Conflicts resolved in `CHANGELOG.md` and `pyproject.toml`
- [x] `.release-please-manifest.json` bumped to `0.5.5`
- [x] Merge commit pushed to `fix/cline-lifecycle-global-path`
- [ ] PR #7 merged on GitHub
- [ ] `slowave 0.5.5` released to PyPI
- [ ] Windows user (matte) installs 0.5.5 and confirms Cline TUI lifecycle works
