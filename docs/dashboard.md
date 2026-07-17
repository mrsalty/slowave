# Slowave local dashboard

Slowave includes a dependency-free local web dashboard for inspecting the memory
database, MCP/server processes, schema health, schema relations, and schema graph.

The dashboard is intended for local development and operational hygiene. The
only way to mutate memory content from it is forgetting a schema (see
[Forgetting a memory](#forgetting-a-memory) below), enabled by default; pass
`--no-allow-actions` for a strictly read-only dashboard, e.g. before sharing
a screen or a port.

## Launch

```bash
slowave dashboard
```

Then open:

```text
http://127.0.0.1:8765
```

Common options:

```bash
# Use a different port.
slowave dashboard --port 8766

# Do not open the browser automatically.
slowave dashboard --no-open

# Refresh the overview every 5 seconds instead of 2 seconds.
slowave dashboard --refresh-ms 5000

# Disable the Forget/Unforget buttons for a strictly read-only dashboard.
slowave dashboard --no-allow-actions
```

The default DB is `~/.slowave/slowave.db`. Use `SLOWAVE_DB` or the global
`--db /path/to/slowave.db` option only when you need to inspect another DB.

The dashboard binds to `127.0.0.1` by default. Binding to a non-localhost address
prints a warning because Slowave memory content may contain private project or
user information.

## What it shows

### Overview

Live cards for:

- DB size and WAL size
- sessions and raw events
- episodes and episode text rows
- prototypes and prototype graph edges
- schemas and schema relations
- active schemas and review queue size
- running Slowave MCP processes

The overview also surfaces warnings such as:

- multiple `slowave-mcp` processes
- orphaned MCP processes
- schemas needing review
- exact duplicate active schemas

### Processes

Lists local Slowave-related processes:

- `slowave-mcp`
- `slowave worker`
- `slowave dashboard`

For each process, it shows PID, PPID, process age, RSS, orphan status, command,
and parent command. This helps catch stale MCP servers left by multiple IDE or
agent sessions.

### Schemas

Searchable schema table with status filtering. Columns include schema id,
status, salience, schema class, scope, support count, and content preview.
Click a row to expand its full detail: content, facets, tags, evidence,
outgoing/incoming relations, and generalization info. Unless the server was
started with `--no-allow-actions`, the expanded view also shows a Forget (or
Unforget, for already-forgotten schemas) button — see
[Forgetting a memory](#forgetting-a-memory).

### Schema graph

Interactive graph of explicit `schema_relations`:

- node = schema
- edge = relation from `schema_relations`
- node color = schema status
- node size = salience
- edge color = relation type
- edge width = relation confidence

Controls:

- scope filter
- result limit
- schema status toggles
- minimum salience slider

Click a schema node to inspect content, facets, tags, evidence rows, outgoing
relations, and incoming relations.

The MVP graph intentionally shows only explicit schema relations. Future graph
modes can add same-prototype links, shared-evidence links, and neighborhood-only
views.

### Relations

Browsable view over `schema_relations`, split by relation type:

- **supersedes** / **refines** — pair table; click a row to expand a two-column
  detail (full text, status/salience/confidence/scope/stage, reason, adjacent
  chain links)
- **part_of** — parent/children tree

### DB health

Shows SQLite pragmas, `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, and
table counts.

## Forgetting a memory

If you spot a memory in the Schemas tab that's wrong, stale, or something you
just don't want influencing future recall, you can suppress it — expand the
schema and click **Forget** (shown by default). This sets the schema's
status to `forgotten`, which hides it
from `activate`/`recall` in every retrieval mode (`strict_scope`, `broad`,
`debug`). It's reversible: click **Unforget** on a forgotten schema to restore
it to whatever status it had before (not always `active` — a schema that was
already `superseded` or `contradicted` goes back to that, not `active`).
Forgetting is logged with an optional reason to `schema_forget_log` for audit,
and the underlying episodes/raw events/evidence are never touched — only the
schema row's status changes.

Forget/Unforget are deliberately **CLI and dashboard only** — there is no MCP
tool for this, unlike `remember`/`recall`/`reinforce`/`commit`. Forgetting is
meant to be a deliberate action a human takes after looking at a specific
memory, not something an AI agent infers from conversational subtext (which
could also make it a prompt-injection target if it were a callable tool). See
`slowave forget`/`slowave unforget` in [`docs/cli.md`](cli.md) for the CLI
equivalent, which works without a running dashboard.

## Local JSON API

The dashboard serves a small JSON API on the same local HTTP server:

| Endpoint | Purpose |
|---|---|
| `GET /api/status` | Overview stats, schema health, recent sessions, process warnings |
| `GET /api/processes` | Slowave MCP/worker/dashboard process snapshot |
| `GET /api/db/health` | SQLite pragmas, integrity check, FK check, table counts |
| `GET /api/schemas?limit=100&status=active&q=text` | Schema table data |
| `GET /api/schemas/123` | Schema detail, evidence, incoming/outgoing relations |
| `GET /api/graph/schemas?limit=120&min_salience=2.5` | Schema graph data |
| `GET /api/relations?type=supersedes&limit=50` | Relations tab data; `type` is one of `supersedes`, `refines`, `part_of`, `relates_to` (default `supersedes`), `limit` is 1-200 (default 50) |
| `POST /api/schemas/123/forget` | Suppress schema 123 (status → `forgotten`). Body: optional JSON `{"reason": "..."}`. `403` if started with `--no-allow-actions`. |
| `POST /api/schemas/123/unforget` | Undo a forget, restoring schema 123's prior status. `403` if started with `--no-allow-actions`. |

Example graph request:

```bash
curl 'http://127.0.0.1:8765/api/graph/schemas?limit=120&statuses=active,needs_review&min_salience=2.5'
```

Example relations request:

```bash
curl 'http://127.0.0.1:8765/api/relations?type=part_of&limit=100'
```

## Safety and limitations

- The only mutating action is forgetting/unforgetting a schema. It's enabled
  by default; pass `--no-allow-actions` for a strictly read-only dashboard —
  see [Forgetting a memory](#forgetting-a-memory).
- It is local-first and binds to `127.0.0.1` by default.
- It uses Python stdlib HTTP serving and embedded HTML/JS; no FastAPI, Node, or
  frontend build step is required.
- The schema graph uses a simple SVG layout suitable for MVP-scale inspection.
  Large graph exploration may later move to Cytoscape.js or another graph UI.
