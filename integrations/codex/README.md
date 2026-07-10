# Codex + Slowave — quick-ref

Full guide: **[../../docs/install.md](../../docs/install.md)**

---

## Setup

```bash
pipx install slowave
slowave setup --client codex
```

`slowave setup` handles everything automatically:
- Adds `[mcp_servers.slowave]` to `~/.codex/config.toml`, pointing at the Slowave HTTP daemon
- Injects `UserPromptSubmit` + `Stop` enforcement hooks into the same `config.toml` (fire every turn)
- Injects the lifecycle instruction block into `~/.codex/AGENTS.md`
- Installs and starts the background worker and HTTP daemon as system services

Restart Codex (whichever surface you use — CLI, Desktop, or IDE extension).

---

## One integration, three surfaces

**"Codex" here means the CLI, the Codex Desktop app (in ChatGPT), and the Codex IDE extension —
all three, covered by one `slowave setup --client codex` run.** Unlike Claude, where Claude Code
and Claude Desktop are separate apps with separate config files, OpenAI consolidated all three
Codex surfaces onto the **same** `~/.codex/config.toml`. Configure it once and every surface picks
it up; there's no separate "Codex Desktop" client to run setup against.

One caveat: the MCP config and `AGENTS.md` instructions are confirmed shared across all three
surfaces. Whether the enforcement hooks fire identically inside the Codex Desktop GUI (vs. the
terminal CLI) hasn't been independently verified — if you notice the hooks aren't triggering in
the desktop app specifically, please report it.

---

## What gets configured

| What | Where |
|---|---|
| MCP server | `~/.codex/config.toml` → `[mcp_servers.slowave]` |
| Enforcement hooks | Same file → `[[hooks.UserPromptSubmit]]` / `[[hooks.Stop]]` |
| Lifecycle instructions | `~/.codex/AGENTS.md` |
| Background worker | launchd (macOS) / systemd (Linux) / Task Scheduler (Windows) |

Unlike every other client Slowave configures, Codex keeps the MCP registry *and* the enforcement
hooks in one TOML file — `slowave setup` patches both in a single read/write pass so a re-run
never leaves a partial, out-of-sync state between them.

`$CODEX_HOME` is respected if set (defaults to `~/.codex`).

---

## Lifecycle instructions

`slowave setup` injects the lifecycle block into `~/.codex/AGENTS.md` — directly analogous to
Claude Code's `CLAUDE.md`. Codex reads this file once per session and folds it into the first
turn.

**Full lifecycle documentation:** [docs/install.md#lifecycle-instruction-block](../../docs/install.md#lifecycle-instruction-block)

### `AGENTS.override.md` caveat

If you already have `~/.codex/AGENTS.override.md`, Codex reads *only* that file at the global
scope and ignores `AGENTS.md` entirely — the injected lifecycle block would never be read.
`slowave doctor` warns if this applies to you; if it does, copy the lifecycle block from
`AGENTS.md` into your override file manually.

---

## Enforcement hooks

Codex has a native hooks system, and Slowave uses it the same way it uses Claude Code's
`UserPromptSubmit` + `Stop` hooks — nudging the model to call `slowave_activate` at the start of
a turn and `slowave_commit` before finishing. This is one of only two clients Slowave enforces
this way today (the other being Claude Code); Cline, Cursor, Windsurf, and OpenCode currently
rely on instructions alone.

**Compatibility note:** older Codex versions ignore remote (`url`-based) MCP servers unless
`[features] experimental_use_rmcp_client = true` is set in `config.toml`. Current versions don't
need this. If `slowave_*` tools don't appear after setup, check your Codex version first —
`slowave setup` does not write this flag automatically since its name is being deprecated
upstream in favor of `[features].rmcp_client`.

---

## Manual MCP config (if `slowave setup` didn't work)

Edit `~/.codex/config.toml` (create it if it doesn't exist):

```toml
[mcp_servers.slowave]
url = "http://127.0.0.1:8766/mcp"
```

No `auth`, `bearer_token_env_var`, or headers needed — Codex connects to a local, unauthenticated
server without any credential fields set.

Make sure the daemon is running (`slowave serve status`). Restart Codex after editing.

---

## Verify

Open Codex and start any coding task. If Slowave is configured correctly, the `slowave_*`
tools appear in the tool list and the lifecycle (activate → commit) runs automatically on every
session — no manual invocation needed.

To confirm from the terminal:

```bash
slowave stats     # shows session/event counts
slowave doctor    # shows client detection and daemon health
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tools don't appear | Run `slowave serve status`; restart Codex; check for the `experimental_use_rmcp_client` compatibility note above |
| Tools appear but aren't called | `AGENTS.md` block or hooks missing — re-run `slowave setup`; check for a shadowing `AGENTS.override.md` |
| Sessions are empty | Hooks should enforce this on every turn; check `~/.codex/config.toml` has the `[[hooks.UserPromptSubmit]]` / `[[hooks.Stop]]` entries |
