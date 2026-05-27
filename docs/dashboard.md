# Slowave local dashboard

Slowave includes a dependency-free local web dashboard for inspecting the memory
database, MCP/server processes, schema health, recall behavior, and schema graph.

The dashboard is intended for local development and operational hygiene. It is
read-only in the current MVP.

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
status, salience, schema class, project, support count, and content preview.

### Schema graph

Interactive graph of explicit `schema_relations`:

- node = schema
- edge = relation from `schema_relations`
- node color = schema status
- node size = salience
- edge color = relation type
- edge width = relation confidence

Controls:

- project filter
- result limit
- schema status toggles
- minimum salience slider

Click a schema node to inspect content, facets, tags, evidence rows, outgoing
relations, and incoming relations.

The MVP graph intentionally shows only explicit schema relations. Future graph
modes can add same-prototype links, shared-evidence links, and neighborhood-only
views.

### Recall playground

Runs `SlowaveEngine.recall()` from the browser. This can load the text encoder,
so the first query may take longer than dashboard-only pages.

### DB health

Shows SQLite pragmas, `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, and
table counts.

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
| `POST /api/recall` | Recall playground backend |

Example graph request:

```bash
curl 'http://127.0.0.1:8765/api/graph/schemas?limit=120&statuses=active,needs_review&min_salience=2.5'
```

Example recall request:

```bash
curl -X POST http://127.0.0.1:8765/api/recall \
  -H 'Content-Type: application/json' \
  -d '{"query":"database preference","top_k":5,"evidence":true}'
```

## Safety and limitations

- The dashboard is read-only in the MVP.
- It is local-first and binds to `127.0.0.1` by default.
- It uses Python stdlib HTTP serving and embedded HTML/JS; no FastAPI, Node, or
  frontend build step is required.
- The schema graph uses a simple SVG layout suitable for MVP-scale inspection.
  Large graph exploration may later move to Cytoscape.js or another graph UI.
- Recall uses the normal encoder-backed recall path and may be slower than the
  stats/process/schema pages.
