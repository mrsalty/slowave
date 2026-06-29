# Installing and setting up Slowave

This is the single authoritative guide for every install and client setup scenario.
Client-specific quick-ref cards live in [`integrations/`](../integrations/).

---

## How it works

Every Slowave integration needs exactly **three things**:

1. **MCP server config** — so your AI client can see the `slowave_*` tools
2. **Lifecycle instructions** — so the client actually calls those tools on every session
3. **Background worker** — so raw events consolidate into searchable long-term memories

`slowave setup` handles all three automatically for every supported client it finds. One manual step is required for **Claude Desktop** and **Cursor** (their instructions surfaces aren't accessible programmatically).

---

## Installation

Recommended installation method:

```bash
pipx install slowave
```

`pipx` is recommended because Slowave is a CLI application and should be installed in an isolated environment.

If you do not have `pipx` installed, follow the official guide:

- [Install pipx](https://pipx.pypa.io/stable/how-to/install-pipx/)

Then run:

```bash
pipx install slowave
```

Alternative installation with `pip`:

```bash
pip install slowave
```

See also:

- [Install pip](https://pip.pypa.io/en/stable/installation/)

> **Claude Desktop / Cursor users:** one extra manual step required after setup — see [Step 2a](#step-2a--claude-desktop-add-custom-instructions) and [Step 2b](#step-2b--cursor-add-rules-for-ai).

**Uninstall:**
```bash
slowave cleanup         # remove all configuration
pipx uninstall slowave  # remove package
```

---

## Requirements

- Python 3.10+
- macOS, Linux, or Windows
- 8GB+ RAM recommended
- CPU is enough — no GPU, Ollama, OpenRouter, or cloud service required

> [!NOTE]
> Slowave runs a local ONNX embedding model on your CPU. The model is downloaded on first use and then cached locally. No LLM API calls are required for memory storage, retrieval, consolidation, or context generation.
---

## Step 1 — Install

Choose one method. They all give you the `slowave` CLI and the `slowave-mcp-http` daemon entry point.

**pipx** *(recommended — isolated, no venv management)*

```bash
pipx install slowave
```

**pip**

```bash
pip install slowave
```

**Homebrew (macOS)**

```bash
brew tap mrsalty/slowave https://github.com/mrsalty/slowave
brew install slowave
```

**From source**

```bash
git clone https://github.com/mrsalty/slowave
cd slowave
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify the install:

```bash
which slowave        # e.g. /opt/homebrew/bin/slowave
slowave serve status  # confirm daemon is ready
slowave doctor       # checks Python, faiss, ONNX embedding backend, MCP server
slowave stats        # shows stored events / episodes / schemas
```

> The Slowave HTTP daemon (`slowave serve start`) must be running before clients can connect. Use `slowave serve status` to confirm.

Slowave stores data in `~/.slowave/slowave.db`. Set `SLOWAVE_DB=/absolute/path` only if you intentionally want a different database.

---

## Step 2 — Wire clients and start the worker

```bash
slowave setup
```

Run once after install. What it does:

| Action | Clients | Detail |
|---|---|---|
| MCP config | All | Patches each client's MCP config file so `slowave_*` tools appear |
| Lifecycle instructions | Claude Code, Cline, Windsurf | Injects the mandatory Slowave block into `CLAUDE.md`, `.clinerules`, and `global_rules.md` automatically |
| Lifecycle instructions | Claude Desktop, Cursor | Prints the block to paste — requires one manual step (their instructions surfaces aren't scriptable) |
| Enforcement hooks | Claude Code only | Adds `UserPromptSubmit` + `Stop` hooks so Claude Code always calls Slowave on every turn |
| Background worker | All | Installs a user service: launchd (macOS), systemd (Linux), Task Scheduler (Windows) |

`slowave setup` is **idempotent** — re-running it is always safe. It reports `–` for anything already up-to-date and only writes what has changed.

Options:

```
slowave setup --client [claude-code|claude-desktop|cline|cursor|windsurf|all]  # default: all
              --no-worker       # skip worker service install
              --no-hooks        # skip Claude Code hooks
              --dry-run         # preview without writing anything
```

> **Claude Desktop only:** `slowave setup` handles MCP config and the worker, but lifecycle instructions must be added manually — the Custom Instructions field is stored server-side with no automation path.

### Step 2a — Claude Desktop: add Custom Instructions

Open Claude Desktop → **Settings → General → Instructions for Claude** and paste the [lifecycle instruction block](#lifecycle-instruction-block) below.

`slowave setup` prints the required settings path and links back to the Claude Desktop quick-ref. The Custom Instructions field is stored server-side, so Slowave cannot patch it automatically.

---

## Manual setup (without `slowave setup`)

Use this if you prefer to configure things by hand, or if `slowave setup` can't find your client.

### What every client needs

Every client requires exactly three things:

1. **MCP server configuration** — so the `slowave_*` tools appear in the client
2. **Lifecycle instructions** — so the client actually calls those tools
3. **Background worker** — so episodes consolidate into durable schemas

MCP configuration alone is not sufficient. A client that can see the tools but has no instructions to call them will produce empty or sparse memory.

### MCP config block

```jsonc
{
  "mcpServers": {
    "slowave": {
      "type": "http",
      "url": "http://127.0.0.1:8766/mcp"
    }
  }
}
```

Make sure the daemon is running: `slowave serve start`.

| Client | Config file |
|---|---|
| Claude Code | `~/.claude.json` (user-scope MCP registry) |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Cline (VS Code / Cursor, macOS) | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` |
| Cursor (all platforms) | `~/.cursor/mcp.json` |
| Windsurf (all platforms) | `~/.codeium/windsurf/mcp_config.json` |

### Lifecycle instruction block

Paste this into the appropriate location for each client (see table below).

```md
## MANDATORY — Slowave memory (5-verb cognitive cycle)

You are the reasoning module; Slowave is the memory module. Give it honest signals — what you encoded, what helped, what was noise, the outcome — and trust consolidation to do the rest. Do not respond until step 1 completes. Do not end the task without step 5.

1 — `slowave_activate` (before your first response)
   `slowave_activate(query="<verbatim task>", goal="<short goal>", scope="project:<basename(cwd)>")` → store `retrieval_id`.
   - `query`: the task verbatim — do not summarize (raw text drives retrieval).
   - `goal`: 3–6 word verb-noun phrase (e.g. `"fix auth null pointer"`). Phrase it naturally; it is folded into the retrieval cue, so roughly consistent wording for the same kind of task gives a small overlap boost. Exact matching is NOT needed.
   - `scope`: `project:<name>` (or `user:<id>` / `domain:<topic>`). Never omit. Call ONCE.

2 — `slowave_remember` (encode durable knowledge)
   `slowave_remember(content, type, scope="project:<basename(cwd)>")` — call per durable fact.
   - Novelty gate — skip if it already surfaced in activate/recall, is reconstructible from current context, or is transient/session-only state.
   - ONE fact per call (never bundle — it blurs the embedding).
   - Blank-slate phrasing: write so a reader with zero session context understands it. WRONG: `"fixed it by adding the field"`. RIGHT: `"SessionReaper idle timeout defaults to 3600s; the HTTP daemon disables it (0)"`.
   - `type` (pick the most specific; default `decision`): `fact`, `preference` (how the user wants things), `decision` (choice + reason), `constraint` (invariant), `procedure` (repeatable steps), `lesson` (from failure/surprise), `warning` (hazard), `open_question`, `task` (durable to-do), `artifact` (produced/external ref).
   - If a remembered fact changed: remember the corrected version AND flag the old one via `stale_memory_ids`/`wrong_memory_ids` in step 4.
   - Never encode: what is observable right now, transient state, vague impressions, or what you did this session (step 5 captures that).

3 — `slowave_recall` (only when activate fell short)
   `slowave_recall(query, scope="project:<basename(cwd)>")` — specific, semantic query. WRONG: `"what about auth"`. RIGHT: `"decision on daemon single-instance enforcement"`. Always pass `scope` (omitting returns ALL projects). Store the returned `retrieval_id`. Not a substitute for activate.

4 — `slowave_reinforce` (after ANY retrieval — reward hits, suppress noise)
   Call whenever activate/recall returned memories — not only when you used some. Penalizing noise is how the store stays clean.
   `slowave_reinforce(retrieval_id=<id>, feedback="useful|partially_useful|irrelevant|stale|wrong|missing|too_much_context", outcome="success|partial|failure|unknown", used_memory_ids=[...], irrelevant_memory_ids=[...], stale_memory_ids=[...], wrong_memory_ids=[...])`
   - `used_memory_ids`: IDs you actually relied on (strengthens them).
   - `irrelevant`/`stale`/`wrong_memory_ids`: IDs that were noise, outdated, or incorrect (this is how the store self-cleans). Real IDs only — never invent.
   - `feedback` and `outcome`: honest, not optimistic. Use `missing` to flag a needed-but-absent memory.

5 — `slowave_commit` (session close — always)
   `slowave_commit(scope="project:<basename(cwd)>", outcome="success|partial|failure")`. Non-negotiable. Scope must match activate; outcome honest (`partial` if anything was incomplete). Skipping = no episodes form; the session lingers until the idle reaper closes it.

Anti-patterns: skip activate; `remember` without `scope`; bundle facts; context-dependent phrasing; re-encode facts already surfaced; leave a superseded fact unflagged; reinforce only hits and never penalize noise; default feedback to `useful`; invent memory IDs; report `success` when partial/failed; skip reinforce or commit.
```

**Where to put it:**

| Client | Location | `agent` value |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` (global) or repo `CLAUDE.md` | `claude-code` |
| Claude Desktop | **Settings → General → Instructions for Claude** — see [Step 2a](#step-2a--claude-desktop-add-custom-instructions) | `claude-desktop` |
| Cline | `~/.cline/rules/slowave.md` (global, injected automatically by `slowave setup`) or repo `.clinerules` | `cline-tui` |
| Cursor | **Settings → Rules for AI** (or repo `.cursorrules`) — see [Step 2b](#step-2b--cursor-add-rules-for-ai) | `cursor` |
| Windsurf | `~/.codeium/windsurf/memories/global_rules.md` (injected automatically by `slowave setup`) | `windsurf` |

### Step 2b — Cursor: add Rules for AI

Open Cursor → **Settings → Rules for AI** and paste the lifecycle block above (with `agent="cursor"`).

Alternatively, create a `.cursorrules` file at the root of any project and paste the same block there.

`slowave setup` handles MCP config and the background worker, but the Rules for AI field is not accessible programmatically — it requires a one-time manual paste.

---

### Background worker

The worker runs offline replay and consolidation so episodes become durable schemas.

**One-shot (for testing):**
```bash
slowave worker --once
```

**Persistent (recommended for daily use):**

*macOS — launchd:*

Create `~/Library/LaunchAgents/com.slowave.worker.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>com.slowave.worker</string>
    <key>ProgramArguments</key>
    <array>
      <string>/opt/homebrew/bin/slowave</string>
      <string>worker</string>
      <string>--interval</string>
      <string>300</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/tmp/slowave-worker.log</string>
    <key>StandardErrorPath</key><string>/tmp/slowave-worker.err</string>
  </dict>
</plist>
```

Replace `/opt/homebrew/bin/slowave` with the output of `which slowave`, then:

```bash
launchctl load ~/Library/LaunchAgents/com.slowave.worker.plist
launchctl list | grep slowave   # should show a pid
```

To stop/uninstall:

```bash
launchctl unload ~/Library/LaunchAgents/com.slowave.worker.plist
```

*Linux — systemd user service:*

Create `~/.config/systemd/user/slowave-worker.service`:

```ini
[Unit]
Description=Slowave background consolidation worker

[Service]
ExecStart=/usr/local/bin/slowave worker --interval 300
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

Replace `/usr/local/bin/slowave` with the output of `which slowave`, then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now slowave-worker
systemctl --user status slowave-worker
```

*Windows:* `slowave setup` installs the Task Scheduler task automatically. Run `slowave setup` (or `slowave setup --no-worker` to skip it).

Verify the worker is running:

```bash
slowave status
tail -f /tmp/slowave-worker.log   # macOS launchd
```

---

## Dashboard

```bash
slowave dashboard
# open http://127.0.0.1:8765
```

Read-only local web UI. Shows DB health, Slowave/MCP processes, schemas, a recall playground, and the schema graph.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Client doesn't show Slowave tools | MCP path wrong or client not restarted | Run `slowave setup --dry-run` to check the configured path; restart the client after any config change |
| Client sees tools but never calls them (Claude Code, Cline, Windsurf) | Lifecycle instructions missing | Run `slowave setup` — it re-injects `CLAUDE.md`, `.clinerules`, `global_rules.md`, and Claude Code hooks |
| Client sees tools but never calls them (Claude Desktop) | Custom Instructions not set | Add the lifecycle block to Settings → General → Instructions for Claude — see [Step 2a](#step-2a--claude-desktop-add-custom-instructions) |
| Client sees tools but never calls them (Cursor) | Rules for AI not set | Paste the lifecycle block into Settings → Rules for AI — see [Step 2b](#step-2b--cursor-add-rules-for-ai) |
| Sessions exist but memory is empty | Client skipping `slowave_activate` or `slowave_commit` | Re-run `slowave setup` to refresh lifecycle instructions; Claude Code hooks enforce `slowave_activate` on every turn |
| Recall returns nothing or stale results | Worker not running, or `slowave_recall` used as default | Run `slowave worker --once`; use `slowave_activate` for default priming, not `slowave_recall` |
| Schemas don't appear | Worker/consolidation not running | Run `slowave worker --once` or check the service is active (`launchctl list | grep slowave`) |
| `slowave setup` runs but clients show no tools | Daemon not running | Run `slowave serve start`, then `slowave serve status` |


---

## Uninstalling

To remove Slowave configuration:

```bash
slowave cleanup --dry-run  # preview what will be removed
slowave cleanup            # remove all configuration (keeps database)
```

This removes:
- All MCP server entries from client configs
- All lifecycle instruction blocks (identified by markers)
- All enforcement hooks (Claude Code)
- Background worker service

The database at `~/.slowave/` is **preserved**. To fully remove everything:

```bash
slowave cleanup
pipx uninstall slowave  # or: pip uninstall slowave / brew uninstall slowave
rm -rf ~/.slowave       # optional: delete all memories
```

> **Claude Desktop / Cursor:** also manually clear the lifecycle block from Settings → General → Instructions for Claude (Claude Desktop) or Settings → Rules for AI (Cursor). `slowave cleanup` will remind you.

See **[slowave_setup.md](./slowave_setup.md)** for the complete list of files that `slowave setup` touches.

---

## Further reading

- 📋 **[What gets modified](./slowave_setup.md)** — complete transparency on every file `slowave setup` touches
- 🔧 **[Manual setup guide](./manual_setup.md)** — step-by-step instructions without `slowave setup`
- 💻 **[Client quick-refs](../integrations/)** — one-screen cards for Claude Code, Claude Desktop, Cline, Cursor, Windsurf
- 📊 **[CLI reference](./cli.md)** — all `slowave` commands
- 🌐 **[Dashboard](./dashboard.md)** — local web UI
