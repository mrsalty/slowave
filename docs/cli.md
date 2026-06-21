# Slowave CLI

The CLI is useful for manual inspection, debugging, local dashboard access, benchmark runs, and one-off memory writes. For normal AI-client usage, configure MCP and prompt/rules injection instead; CLI-only usage will not make an agent remember automatically.

## CLI-only quickstart

```bash
SID=$(slowave --json session start --agent manual-cli \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["session_id"])')

slowave event --session "$SID" --type user_message --content "I prefer SQLite for MVPs."
slowave event --session "$SID" --type assistant_message --content "Noted the SQLite preference."
slowave session end "$SID"
slowave worker --once
slowave context --query "database preference" --application manual-cli
slowave recall "database preference" --top-k 5 --evidence
slowave dashboard
```

## Command list

| Command | Purpose |
|---|---|
| `slowave session start --agent <name> --scope <scope>` | Start a memory session (scope e.g. `project:my-repo`, `domain:cooking`) |
| `slowave event --session <sid> --type <type> --content <text>` | Append a raw event to a session |
| `slowave session end <sid>` | Close a session and form episodes, fast/no LLM by default |
| `slowave remember <text> --type <type> --scope <scope>` | Store an explicit high-salience memory |
| `slowave context --query <task> --topic <topic>` | Print a gated working-memory brief for prompt injection. MCP `slowave_activate` also returns `retrieval_id` / `session_id` and opens an implicit session. |
| `slowave recall <query> --top-k 5 --evidence` | Retrieve relevant schemas, episodes, and optional raw evidence. MCP `slowave_recall` also returns `retrieval_id` for use with `slowave_reinforce`. |
| `slowave schema --needs-review --limit 50` | List schemas, optionally the review queue |
| `slowave show sch_123` | Inspect a schema, episode, or raw event by ref |
| `slowave stats` | Print episode/prototype/schema/edge counts |
| `slowave status` | Print DB health, schema health, and local Slowave process snapshot |
| `slowave dedup-schemas --apply` | Merge exact duplicate active schemas; dry-run by default |
| `slowave backup [--dir <path>] [--keep N] [--json]` | Create a gzip-compressed SQLite backup; rotates old copies (keep last 7) |
| `slowave consolidate` | Run replay + latent schema consolidation once |
| `slowave worker --interval 300` | Run periodic background consolidation |
| `slowave dashboard --port 8765` | Run the local read-only web dashboard |
| `slowave doctor` | Check Python version, dependencies, embedding backend, SQLite write access, and MCP server availability. Exits 1 on failure. |
| `slowave setup [--client all\|claude-code\|claude-desktop\|cline] [--dry-run]` | One-command post-install wiring: patches MCP configs, injects CLAUDE.md/clinerules lifecycle block, installs enforcement hooks (Claude Code), registers the background worker and daily backup services (launchd/systemd/Task Scheduler). Idempotent. |

## Event types

Common event types:

```text
user_message
assistant_message
tool_call
tool_result
decision
discovery
error
task_complete
task_failed
```

## Memory types for `remember`

```text
fact
preference
decision
constraint
procedure
task
open_question
warning
lesson
artifact
```
