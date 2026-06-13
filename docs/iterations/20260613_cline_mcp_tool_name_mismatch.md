# Cline MCP — Tool Name Mismatch (Bug 6)
**Date:** 2026-06-13  
**Version affected:** 0.5.3 and earlier  
**Reported by:** end-user matte (Windows, Cline TUI)  

---

## Symptoms

1. **MCP server shows green dot in Cline TUI** (`cline /mcp` → `slowave · stdio, local`) — connection is working.
2. **Tools are never invoked** — Cline connects fine but the LLM never calls any slowave tool, despite the lifecycle block being present in `~/.clinerules`.
3. **No cold-start behaviour, no autonomous `slowave_activate` calls** — the LLM reads the lifecycle instructions and tries to follow them, but silently fails every tool invocation, then continues without memory.

---

## Root cause

`FastMCP.tool(name=...)` registers the tool under **exactly the name given**. The server registered all tools with bare, unprefixed names:

```python
@mcp.tool(name="activate")      # → "activate"  on the wire
@mcp.tool(name="remember")      # → "remember"
@mcp.tool(name="recall")        # → "recall"
@mcp.tool(name="reinforce")     # → "reinforce"
@mcp.tool(name="commit")        # → "commit"
@mcp.tool(name="stats")         # → "stats"
@mcp.tool(name="remember_procedure")
```

Cline TUI (and Claude Code, Cursor, etc.) present MCP tool names to the LLM exactly as they appear in the server's `tools/list` response — without any server-name prefix. So the LLM's system prompt read:

```
Available tools: activate, remember, recall, reinforce, commit, stats, remember_procedure
```

The lifecycle block written to `~/.clinerules` (and the Claude Code hooks in `settings.json`) consistently instruct the LLM to call:

```
slowave_activate(...)
slowave_remember(...)
slowave_recall(...)
...
```

These names **do not exist** in the tool list. The LLM either hallucinates a call that the MCP layer rejects, or gives up and skips the tool call silently. Either way: no memory, no lifecycle, no cold-start.

**Why it worked with Claude Code:** Claude Code's hooks (`UserPromptSubmit` / `Stop` in `settings.json`) inject an `echo` command that reminds the LLM to call `slowave_activate`. Because Claude Code processes these as out-of-band shell hook output (not MCP tool calls), the mismatch may have been masked or the LLM was more likely to resolve the correct tool. Cline TUI has no equivalent hook mechanism — it relies entirely on `.clinerules`, so the name mismatch broke it completely.

---

## Fix

**File:** `slowave/mcp/server.py`

Rename all 7 tool registrations to include the `slowave_` prefix, matching the names used in the lifecycle block and hooks:

```python
# BEFORE (broken — bare names):
@mcp.tool(name="activate")
@mcp.tool(name="recall")
@mcp.tool(name="remember")
@mcp.tool(name="remember_procedure")
@mcp.tool(name="reinforce")
@mcp.tool(name="commit")
@mcp.tool(name="stats")

# AFTER (fixed — prefixed names):
@mcp.tool(name="slowave_activate")
@mcp.tool(name="slowave_recall")
@mcp.tool(name="slowave_remember")
@mcp.tool(name="slowave_remember_procedure")
@mcp.tool(name="slowave_reinforce")
@mcp.tool(name="slowave_commit")
@mcp.tool(name="slowave_stats")
```

The lifecycle block in `_LIFECYCLE_BLOCK_TEMPLATE` (setup.py) and the Claude Code hook strings (`_USER_PROMPT_CMD`, `_STOP_CMD`) already use `slowave_*` names throughout — **no changes needed there**.

**File:** `tests/integration/test_old_tools_deleted.py`

- Updated `test_new_tools_present` to expect `slowave_*` names.
- Added `test_bare_names_absent` to reject bare names as a regression guard.

---

## Verification

```python
import asyncio, slowave.mcp.server as srv
tools = asyncio.run(srv.mcp.list_tools())
# → slowave_activate, slowave_commit, slowave_recall, slowave_reinforce,
#   slowave_remember, slowave_remember_procedure, slowave_stats
```

---

## Issue 2 — `.clinerules` not picked up (separate investigation)

The user also reported that Cline TUI did not appear to read `~/.clinerules`. This was the **consequence** of Bug 6, not an independent bug:

- The lifecycle block **was** present in `~/.clinerules` (confirmed by earlier analysis).
- The LLM read the instructions and tried to call `slowave_activate` — which failed silently because the tool was named `activate` on the wire.
- The LLM then answered the user's question without memory, making it appear as if the rules were not read.

Once tool names match, the lifecycle block will work as expected on Cline TUI. No change to the `.clinerules` injection path is needed.

---

## Summary table

| # | Sev | File | Issue | Status |
|---|-----|------|-------|--------|
| 6 | **Critical** | `mcp/server.py` | Tool names registered without `slowave_` prefix → LLM calls `slowave_activate` but wire name is `activate` → all tool invocations fail silently | ✅ Fixed — all 7 tools renamed to `slowave_*` |

---

## Release tracking

### 0.5.4 — 2026-06-13

**Status:** Fixed in source ✅

| Artefact | Value |
|---|---|
| Bug introduced | ≤ 0.5.3 (present since the 5-verb tool rename) |
| Fix commit | pending release |
| Files changed | `slowave/mcp/server.py`, `tests/integration/test_old_tools_deleted.py` |
