# Slowave CLI

The CLI mirrors the MCP tools 1-to-1, making the full cognitive cycle scriptable and testable without a running daemon. All commands accept `--json` for machine-readable output.

```bash
export SLOWAVE_DB=/path/to/slowave.db   # optional; defaults to ~/.slowave/slowave.db
```

---

## 5-verb cognitive cycle

These commands map exactly to the MCP tools used by AI agents.

### `slowave activate`

Prime working memory and open a task session.

```bash
slowave --json activate \
  --query "fix the session reaper race condition" \
  --scope "project:my-repo" \
  --goal "fix reaper race" \
  --mode strict_scope
```

Returns `retrieval_id` and `session_id`. Pass them to `reinforce` and `commit`.

| Option | Default | Description |
|--------|---------|-------------|
| `--query` | *(required)* | Task description |
| `--scope` | — | `project:<name>` or `domain:<topic>` |
| `--goal` | — | 3-6 word verb-noun phrase |
| `--task-type` | — | e.g. `coding`, `debugging` |
| `--situation` | — | JSON object with situational metadata |
| `--requirement` | — | Requirement cue (repeatable) |
| `--topic` | — | Topic cue (repeatable) |
| `--entity` | — | Entity cue (repeatable) |
| `--mode` | `strict_scope` | `default` · `strict_scope` · `broad` · `debug` |
| `--limit` | `8` | Max schemas returned |

---

### `slowave remember`

Encode a durable typed claim into long-term memory.

```bash
slowave --json remember "Prefer SQLite for MVPs." \
  --type fact \
  --scope "project:my-repo" \
  --session sess_abc123
```

| Option | Default | Description |
|--------|---------|-------------|
| `--type` | `decision` | `fact` · `preference` · `decision` · `constraint` · `procedure` · `lesson` · `warning` · `open_question` · `artifact` · `task` |
| `--scope` | — | Scope to attach the memory to |
| `--session` | — | Bind to an open session (optional) |

---

### `slowave recall`

Semantic retrieval — mid-task lookup beyond what `activate` surfaced.

```bash
slowave --json recall "database preference" \
  --scope "project:my-repo" \
  --top-k 5
```

Returns `retrieval_id` and `memories`. Pass `retrieval_id` to `reinforce`.

| Option | Default | Description |
|--------|---------|-------------|
| `--scope` | — | Recommended; omit to search all scopes |
| `--mode` | `default` | `default` · `strict_scope` · `broad` · `debug` |
| `--top-k` | `5` | Max memories returned |
| `--evidence` | off | Include raw event citations |

---

### `slowave reinforce`

Apply feedback to memories from a prior `activate` or `recall`.

```bash
slowave --json reinforce ctx_abc123 \
  --feedback useful \
  --outcome success \
  --used sch_5 sch_12 \
  --irrelevant sch_7
```

| Argument / Option | Description |
|------------------|-------------|
| `RETRIEVAL_ID` | `ctx_…` from `activate`, `rec_…` from `recall` |
| `--feedback` | `useful` · `partially_useful` · `irrelevant` · `stale` · `wrong` · `missing` · `too_much_context` |
| `--outcome` | `success` · `partial` · `failure` · `unknown` |
| `--used SCH_ID` | Schema IDs relied on (repeatable) |
| `--irrelevant SCH_ID` | Schema IDs not relevant (repeatable) |
| `--stale SCH_ID` | Outdated IDs (repeatable) |
| `--wrong SCH_ID` | Factually wrong IDs (repeatable) |

---

### `slowave commit`

Close a session and encode its events into episodic memories.

```bash
slowave --json commit sess_abc123 --outcome success
```

| Option | Default | Description |
|--------|---------|-------------|
| `--outcome` | `unknown` | `success` · `partial` · `failure` · `unknown` |

---

## Session & event management

Lower-level commands for manual session control.

```bash
# Start a session
SID=$(slowave --json session start --scope "project:my-repo" \
      | python3 -c 'import sys,json; print(json.load(sys.stdin)["session_id"])')

# Append raw events
slowave event --session "$SID" --type user_message --content "I prefer SQLite for MVPs."
slowave event --session "$SID" --type assistant_message --content "Noted."

# End session (use commit for the MCP-aligned path; session end for raw control)
slowave session end "$SID"
```

`slowave commit` is preferred over `slowave session end` when working in the cognitive cycle — it maps to `slowave_commit` and uses the same contract. `session end` is lower-level and accepts `--consolidate` for synchronous replay.

---

## Operational commands

| Command | Description |
|---------|-------------|
| `slowave consolidate [--decay-idle-days N]` | Replay + latent consolidation pass. `--decay-idle-days 0` decays all eligible schemas immediately (useful in tests). |
| `slowave worker [--interval 300] [--once]` | Background consolidation worker. `--once` for cron/CI. |
| `slowave context [OPTIONS]` | Context brief without opening a session (operational inspection). Same options as `activate`. |
| `slowave schema [--needs-review] [--limit 50]` | List schemas. |
| `slowave show sch_N \| epi_N \| evt_N` | Inspect a schema, episode, or raw event. |
| `slowave stats` | Episode / prototype / schema / edge counts. |
| `slowave status` | DB health, schema health, local process snapshot. |
| `slowave dedup-schemas [--apply]` | Merge exact duplicate active schemas; dry-run by default. |
| `slowave backup [--dir PATH] [--keep N]` | Gzip-compressed SQLite backup; rotates old copies. |
| `slowave dashboard [--port 8765]` | Local read-only web dashboard. |
| `slowave doctor` | Checks Python version, deps, encoder, SQLite, MCP availability. Exits 1 on failure. |
| `slowave setup [--client all\|claude-code\|…] [--dry-run]` | One-command post-install wiring: MCP configs, CLAUDE.md lifecycle block, hooks, worker and backup services. Idempotent. |
| `slowave serve start \| stop \| status` | Manage the HTTP MCP daemon (port 8766 by default). |

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SLOWAVE_DB` | `~/.slowave/slowave.db` | SQLite database path |
| `SLOWAVE_MCP_HTTP_PORT` | `8766` | HTTP daemon port |
| `SLOWAVE_MCP_HOST` | `127.0.0.1` | HTTP daemon bind host |
| `SLOWAVE_DAEMON_PID` | `~/.slowave/daemon.pid` | PID file path |
| `SLOWAVE_SESSION_IDLE_TIMEOUT` | `3600` | Session idle reaper timeout (seconds) |
| `KMP_DUPLICATE_LIB_OK` | — | Set to `TRUE` on macOS if FAISS + ONNX segfault |
