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
| `slowave session start --agent <name> --project <project>` | Start a memory session |
| `slowave event --session <sid> --type <type> --content <text>` | Append a raw event to a session |
| `slowave session end <sid>` | Close a session and form episodes, fast/no LLM by default |
| `slowave remember <text> --type <type> --project <project>` | Store an explicit high-salience memory |
| `slowave context --query <task> --topic <topic>` | Print a gated working-memory brief for prompt injection |
| `slowave recall <query> --top-k 5 --evidence` | Retrieve relevant schemas, episodes, and optional raw evidence |
| `slowave schema --needs-review --limit 50` | List schemas, optionally the review queue |
| `slowave show sch_123` | Inspect a schema, episode, or raw event by ref |
| `slowave stats` | Print episode/prototype/schema/edge counts |
| `slowave status` | Print DB health, schema health, and local Slowave process snapshot |
| `slowave dedup-schemas --apply` | Merge exact duplicate active schemas; dry-run by default |
| `slowave consolidate` | Run replay + latent schema consolidation once |
| `slowave worker --interval 300` | Run periodic background consolidation |
| `slowave dashboard --port 8765` | Run the local read-only web dashboard |
| `slowave doctor` | Check Python version, dependencies, embedding backend, SQLite write access, and MCP server availability. Exits 1 on failure. |

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
