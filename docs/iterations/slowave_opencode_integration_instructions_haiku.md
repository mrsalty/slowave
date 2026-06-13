# Slowave OpenCode Integration — Implementation Instructions for Haiku 4.5

## Goal

Implement first-class OpenCode support in `slowave setup`, `slowave doctor`, and integration documentation.

OpenCode should become a fully automatable Slowave client integration using:

1. OpenCode MCP config via `~/.config/opencode/opencode.json`
2. A Slowave-owned instruction file registered through OpenCode's `instructions` config key
3. Optional plugin deployment for lifecycle prompting, treated as experimental until verified

Do **not** modify `AGENTS.md` by default.

---

## Background

OpenCode uses a different MCP config shape from Claude, Cline, Cursor, and other existing clients.

OpenCode expects MCP servers under the top-level `mcp` key:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "slowave": {
      "type": "local",
      "command": ["/absolute/path/to/slowave-mcp"],
      "enabled": true
    }
  }
}
```

Important differences:

- OpenCode uses `mcp`, not `mcpServers`
- Local MCP servers use `"type": "local"`
- `command` is an array, not a string
- Global config path is normally `~/.config/opencode/opencode.json`
- Lifecycle/rule files can be injected through the `instructions` array
- Global plugins can live in `~/.config/opencode/plugins/`

---

## Implementation Scope

Implement the MVP integration first.

### Required in MVP

`slowave setup --client opencode` must:

1. Create or patch OpenCode global config:
   - `~/.config/opencode/opencode.json`
   - respect `XDG_CONFIG_HOME` if set

2. Add or update:

```json
{
  "mcp": {
    "slowave": {
      "type": "local",
      "command": ["/absolute/path/to/slowave-mcp"],
      "enabled": true
    }
  }
}
```

3. Write a Slowave-owned instruction file:

```text
~/.config/opencode/slowave-instructions.md
```

4. Register that instruction file in OpenCode config:

```json
{
  "instructions": ["/absolute/path/to/slowave-instructions.md"]
}
```

5. Update doctor/client detection so Slowave can report OpenCode integration status.

### Not required in MVP

Do **not** make plugin installation mandatory.

The plugin should either be:

- skipped entirely in the first implementation, or
- implemented behind an explicit experimental option if the existing setup command architecture already supports optional features.

Recommended option name if needed:

```bash
slowave setup --client opencode --experimental-plugin
```

If adding that flag is too invasive, leave the plugin for a follow-up PR.

---

## Design Decision

Use `instructions` + a Slowave-owned file as the default lifecycle mechanism.

Do **not** write to:

```text
~/.config/opencode/AGENTS.md
```

by default.

Reason:

- users may already own `AGENTS.md`
- a Slowave-owned instruction file is easier to update
- it is easier to uninstall
- it avoids merging conflicts with user-authored global OpenCode rules
- OpenCode supports combining instruction files with `AGENTS.md`

---

## Files to Inspect First

Before editing, inspect the current implementation around client setup and doctor detection.

Likely relevant files include, but are not limited to:

```text
slowave/cli/setup.py
slowave/cli/clients.py
slowave/cli/doctor.py
slowave/core/config.py
slowave/mcp/*
docs/integrations/*
integrations/*
tests/*
```

Use the actual current structure of the repository. Do not invent new architecture if the existing setup framework already has a pattern for clients.

---

## Required Code Changes

### 1. Add OpenCode client spec

Add a new client entry similar to existing clients.

Target logical shape:

```python
ClientSpec(
    key="opencode",
    label="OpenCode",
    mcp_path=_opencode_global_config_path,
    lifecycle_path=_opencode_slowave_instructions_path,
    lifecycle_agent="opencode",
    require_dir_exists=False,
    restart_note="Restart opencode to apply changes.",
)
```

Adapt to the real `ClientSpec` signature used in the repository.

---

### 2. Add OpenCode path helpers

Add helpers equivalent to:

```python
def _opencode_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", str(_home() / ".config"))
    return Path(xdg) / "opencode"


def _opencode_global_config_path() -> Path:
    return _opencode_config_dir() / "opencode.json"


def _opencode_slowave_instructions_path() -> Path:
    return _opencode_config_dir() / "slowave-instructions.md"


def _opencode_plugin_path() -> Path:
    return _opencode_config_dir() / "plugins" / "slowave.js"
```

Use the repository's existing `_home()` or equivalent helper.

---

### 3. Add OpenCode-specific MCP patching

Existing clients may use `mcpServers`. OpenCode must not.

Add a dedicated patch function:

```python
def _patch_opencode_mcp(config: dict, mcp_path: str) -> tuple[dict, bool]:
    mcp = config.setdefault("mcp", {})

    want = {
        "type": "local",
        "command": [mcp_path],
        "enabled": True,
    }

    if mcp.get("slowave") == want:
        return config, False

    mcp["slowave"] = want
    return config, True
```

Requirements:

- Preserve unrelated OpenCode config keys.
- Preserve unrelated MCP server entries.
- Do not write `mcpServers`.
- Do not use command as a string.
- Make this operation idempotent.

---

### 4. Patch OpenCode instructions

Add a function equivalent to:

```python
def _patch_opencode_instructions(config: dict, instructions_path: str) -> tuple[dict, bool]:
    instructions = config.setdefault("instructions", [])

    if instructions_path in instructions:
        return config, False

    instructions.append(instructions_path)
    return config, True
```

Requirements:

- Use an absolute path string for `instructions_path`.
- Do not use `~` unless existing project conventions explicitly do so and tests confirm expansion.
- Preserve existing instruction entries.
- Avoid duplicates.
- Be idempotent.

If the config already has a non-list `instructions` value, handle it safely:

- Prefer failing with a clear error, or
- normalize only if existing project conventions allow that.

Do not silently destroy user config.

---

### 5. Write OpenCode lifecycle instructions

Write this file during setup:

```text
~/.config/opencode/slowave-instructions.md
```

The content should be equivalent to other Slowave lifecycle blocks, but agent-specific language may mention OpenCode.

Minimum expected content:

```md
# Slowave Memory Lifecycle for OpenCode

You have access to Slowave memory tools.

At the beginning of a new coding session, call `slowave_activate` before answering whenever project context may matter.

During the session, use Slowave tools to remember durable decisions, constraints, project conventions, implementation notes, and user preferences.

Before finishing a meaningful session, call `slowave_commit` to persist important outcomes, decisions, and follow-up tasks.

Prefer storing durable, reusable knowledge. Do not store temporary scratch notes unless they affect future work.
```

Use the repository's existing lifecycle template mechanism if one already exists.

Do not duplicate a second divergent lifecycle prompt system if the project already has shared lifecycle text.

---

### 6. Optional plugin file

Do not make this required unless explicitly requested.

If implementing as experimental, install:

```text
~/.config/opencode/plugins/slowave.js
```

Initial plugin should be conservative.

Suggested content:

```js
export const SlowavePlugin = async ({ client }) => {
  return {
    "session.created": async ({ event }) => {
      // Experimental lifecycle prompt.
      // Verify OpenCode client API before relying on this.
    },

    "session.idle": async ({ event }) => {
      // Experimental lifecycle prompt.
      // Verify OpenCode client API before relying on this.
    },

    "tool.execute.after": async ({ event }) => {
      // Optional: observe slowave tool usage.
    }
  };
};
```

Do **not** claim hard enforcement unless the plugin actually forces tool calls.

Use wording like:

```text
experimental lifecycle prompting
```

not:

```text
guaranteed enforcement
```

---

## Doctor / Detection Requirements

Update OpenCode detection in doctor/client status code.

Doctor should check:

1. OpenCode config file exists:

```text
~/.config/opencode/opencode.json
```

2. `mcp.slowave` exists.

3. `mcp.slowave.type == "local"`.

4. `mcp.slowave.command` is a list.

5. `mcp.slowave.command` includes the Slowave MCP executable path, or at least a command ending in/containing `slowave-mcp` depending on existing detection patterns.

6. `mcp.slowave.enabled is True`.

7. Slowave instruction file exists:

```text
~/.config/opencode/slowave-instructions.md
```

8. OpenCode config contains that file in `instructions`.

9. Optional: plugin exists if plugin support is implemented.

Doctor output should clearly distinguish:

- MCP configured
- lifecycle instructions configured
- plugin installed, if applicable

---

## Documentation Changes

Add a new OpenCode integration document.

Suggested path:

```text
docs/integrations/opencode.md
```

or, if the repository uses another convention:

```text
integrations/opencode/README.md
```

Follow the existing documentation layout.

The doc must include:

### Quick setup

```bash
slowave setup --client opencode
```

### What setup changes

```text
~/.config/opencode/opencode.json
~/.config/opencode/slowave-instructions.md
```

### MCP config shape

```json
{
  "mcp": {
    "slowave": {
      "type": "local",
      "command": ["/absolute/path/to/slowave-mcp"],
      "enabled": true
    }
  }
}
```

### Lifecycle behavior

Explain:

- OpenCode receives Slowave instructions through the `instructions` config key.
- Slowave does not modify `AGENTS.md` by default.
- Users can still add project-specific Slowave guidance to project `AGENTS.md` manually.

### Optional plugin note

If the plugin is not implemented yet, say:

```md
OpenCode also supports plugins under `~/.config/opencode/plugins/`. Slowave may use this in a future version for stronger lifecycle prompting.
```

If implemented experimentally, say:

```md
Experimental plugin support can install a local plugin under `~/.config/opencode/plugins/slowave.js`. This provides lifecycle prompting, not guaranteed tool-call enforcement.
```

### Update integrations index

Update the main integration table to include OpenCode.

Suggested capability row:

```md
| OpenCode | ✅ | ✅ via `instructions` | Experimental / optional plugin | ✅ |
```

Adapt to the actual table columns.

---

## Tests to Add

Add tests matching the existing test style.

Minimum tests:

### MCP patch tests

1. Creates `mcp.slowave` when missing.
2. Preserves existing `mcp` entries.
3. Updates an incorrect `slowave` entry.
4. Is idempotent when config already matches.
5. Does not create `mcpServers`.

### Instructions patch tests

1. Creates `instructions` list when missing.
2. Appends Slowave instruction path.
3. Preserves existing instruction entries.
4. Avoids duplicate entries.
5. Is idempotent.

### Path helper tests

If existing tests cover paths:

1. Default path uses `~/.config/opencode`.
2. `XDG_CONFIG_HOME` is respected.

### Doctor tests

If doctor has unit tests:

1. Detects valid OpenCode MCP config.
2. Detects missing lifecycle instruction file.
3. Detects missing `instructions` reference.
4. Detects invalid command shape where command is a string instead of a list.

---

## Manual Validation Checklist

After implementation, validate locally with a temp home/config directory if possible.

### Setup command

Run:

```bash
slowave setup --client opencode
```

Expected:

- command succeeds
- creates OpenCode config dir if absent
- writes/patches `opencode.json`
- writes `slowave-instructions.md`

### Inspect config

Expected shape:

```json
{
  "mcp": {
    "slowave": {
      "type": "local",
      "command": ["/absolute/path/to/slowave-mcp"],
      "enabled": true
    }
  },
  "instructions": [
    "/absolute/path/to/slowave-instructions.md"
  ]
}
```

### Idempotency

Run setup twice.

Expected:

- no duplicate `instructions` entries
- no duplicate MCP entries
- second run should report unchanged if the existing setup command supports changed/unchanged reporting

### Doctor

Run:

```bash
slowave doctor
```

or:

```bash
slowave doctor --client opencode
```

depending on existing CLI.

Expected:

- OpenCode MCP reports configured
- OpenCode lifecycle instructions report configured

---

## Guardrails

Do not:

- modify `AGENTS.md` by default
- use `mcpServers` for OpenCode
- write command as a string
- overwrite the entire OpenCode config
- remove unrelated OpenCode settings
- remove unrelated MCP servers
- claim plugin enforcement is guaranteed
- add npm/Bun dependency for the MVP
- hardcode popularity claims like GitHub star counts in docs

Do:

- preserve user config
- keep setup idempotent
- use absolute paths
- respect `XDG_CONFIG_HOME`
- keep plugin support optional or deferred
- follow existing Slowave client setup patterns

---

## Acceptance Criteria

The implementation is complete when:

1. `slowave setup --client opencode` works on a clean environment.
2. Existing OpenCode config is preserved.
3. OpenCode receives a valid `mcp.slowave` entry.
4. OpenCode receives Slowave lifecycle instructions through `instructions`.
5. Setup is idempotent.
6. Doctor can detect valid and invalid OpenCode integration states.
7. Tests cover OpenCode MCP patching and instruction patching.
8. Documentation includes OpenCode setup and explains the design choices.
9. No required plugin dependency is introduced.
10. Existing tests still pass.

---

## Suggested Commit Message

```text
feat(setup): add OpenCode client integration
```

Suggested PR summary:

```md
## Summary

Adds first-class OpenCode integration to Slowave setup and doctor.

- Registers Slowave MCP under OpenCode's `mcp` config key
- Writes a Slowave-owned lifecycle instruction file
- Registers lifecycle instructions through OpenCode's `instructions` config key
- Adds OpenCode doctor detection
- Documents OpenCode setup and behavior

## Notes

The implementation intentionally does not modify `AGENTS.md` by default. Plugin-based lifecycle prompting is left optional/experimental.
```
