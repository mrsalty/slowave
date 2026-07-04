# Dashboard Review & Improvement Plan

**Date:** 2026-07-04

## Current State

The Slowave dashboard (`slowave/dashboard/`) is a dependency-free local web dashboard for
inspecting the memory database — zero-dependency (stdlib HTTP server + embedded
HTML/JS/Cytoscape.js), read-only, localhost-bound by default.

### Tabs

| Tab | What it shows |
|-----|--------------|
| **Overview** | Stat cards (sessions, events, episodes, schemas, prototypes, edges, relations, feedback, promoted, global, scopes, DB size), multi-channel pulse chart (raw_events / episodes / schemas over time), recent sessions, process list, daemon health, warnings |
| **Schemas** | Searchable/filterable schema table with status/salience/class/scope filtering, detail drill-down panel (content, facets, tags, evidence with aligned grid, incoming/outgoing relations), generalization stat cards at top |
| **Graph** | Interactive schema-relation graph with Cytoscape.js + SVG fallback, scope/status/salience filters (cross-browser range slider), neighborhood view on click |
| **Worker** | Consolidation run history + multi-channel spline chart (schemas created/reinforced/decayed) |
| **Supersessions** | Supersession chains with confidence, source/target content, timestamps |
| **Recall Playground** | Live `engine.recall()` with query/k/evidence controls, displays schemas + episodes + expanded neighbors |
| **DB Health** | SQLite pragmas, integrity check, FK check, table counts |

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /` | HTML dashboard |
| `GET /api/status` | Overview stats, schema health, scopes, recent sessions, daemon, warnings |
| `GET /api/daemon` | Daemon health check |
| `GET /api/pulse?hours=2&bucket_m=5` | Time-bucketed activity (raw_events, episodes, schemas) |
| `GET /api/db/health` | DB pragmas, integrity check |
| `GET /api/schemas?limit=100&status=active&q=text` | Schema table data |
| `GET /api/schemas/:id` | Schema detail + evidence + relations |
| `GET /api/graph/schemas?limit=120&statuses=active&min_salience=2.5` | Graph nodes + edges |
| `GET /api/worker/runs?limit=50` | Worker run history |
| `GET /api/generalization` | Stage distribution, scope registry |
| `POST /api/recall` | Recall playground backend |

---

## Proposed Improvements
### Tier 1 — High impact, moderate effort

#### 1. Episode & Prototype Browser tab
The dashboard shows counts everywhere but never the actual content of episodic memories
or prototypes — the hippocampus and sensory cortex analogues are invisible.

- Episode list with content preview, session context, recency, type
- Prototype list with topic, N-members, representative text
- Click-through to see all episodes/schemas belonging to a prototype
- New endpoints: `GET /api/episodes?limit=100`, `GET /api/prototypes?limit=100`,
  `GET /api/prototypes/:id/members`

#### 2. Session Replay Viewer
Drill into a single session and see its raw events chronologically — replay what an
agent experienced.

- `GET /api/sessions/:id/events` — all raw_events for a session
- `GET /api/sessions/:id/episodes` — all formed episodes
- Timeline view in the UI: event type, content preview, timestamps, role/speaker

#### 3. ~~Salience Distribution Histogram~~ (removed)
~~Canvas-based bar chart of schema salience values.~~ Implemented then removed in July 2026
dashboard polish pass — histograms of synthetic normal-distribution bars proved
uninformative; the actual salience range is better served by the schema health panel
and per-schema salience bars.

#### 4. Supersession / Contradiction Timeline
A view showing correction history — which schemas were superseded by which, when, and why.

> "sch_42 → superseded by → sch_87 at timestamp T, reason: …"

- New tab or section in schemas tab
- `GET /api/supersessions?limit=100` — supersession chain data
- Critical for trust: knowing when memory was wrong and how it self-corrected

### Tier 2 — Medium impact, moderate effort

#### 5. Memory Health Score (single 0–100 gauge)
Composite health score combining:
- Active schema ratio (active / total)
- Duplicate penalty (1.0 − duplicate_ratio)
- Consolidation staleness (time since last consolidation)
- Review queue pressure (needs_review / total)
- Schema decay rate

Display as a gauge or donut on the Overview tab.

#### 6. Scope Activity Comparison
Matrix or grouped bar chart showing events/schemas/sessions per scope — which projects
are most active vs. dormant. Data already in `/api/status` (scopes array).

#### 7. Feedback Event Inspector tab
Raw feed viewer for all `feedback_events` (reinforce, remember calls) — the RL signals.
Currently tracked as a count but content is never exposed.

- Paged table: type, scope, session, outcome, timestamp, content preview
- Filter by feedback type (useful, irrelevant, stale, wrong, etc.)

#### 8. Schema Lifecycle Timeline
For a given schema, show its temporal journey:
`first_formed → promoted (stage 1) → promoted (stage 2) → superseded → archived`

Extends the existing schema detail panel with a vertical timeline showing timestamps
and reasons.

### Tier 3 — High impact, high effort (aspirational)

#### 9. Latent Space Explorer (2D projection)
Project schema embedding vectors into 2D (PCA or UMAP), rendered as an interactive
scatter plot. Color by status, size by salience. The most "brain-like" visualization —
showing how concepts cluster in semantic space.

- Requires loading embeddings from `schema_embeddings`
- Run projection on-demand or cache it
- Canvas-based rendering, tooltips on hover

#### 10. Real-time WebSocket / SSE updates
Replace the 2s polling with push-based updates. SSE (Server-Sent Events) is simpler
than WebSocket and works with stdlib.

- Push schema changes, new events, consolidation results
- `/api/stream` SSE endpoint

#### 11. Token Efficiency Dashboard tab
Expose metrics from `test_token_efficiency.py` live: compression ratio, memory tokens
vs. context tokens, recall precision. Ties the dashboard to the actual value proposition.

### Tier 4 — Quick wins, minimal effort

#### 12. Export buttons
"Download as JSON" / "Download as CSV" on schema and graph tabs for filtered results.
Read-only but lets users take data elsewhere.

#### 13. Keyboard shortcuts
- `1-7` to switch tabs
- `/` to focus search
- `Esc` to close detail panel

#### 14. Collapsible stat card sections
The overview has many cards; let users hide/show groups (e.g., "Memory Health",
"Activity", "Storage").

#### 15. Relative time display toggle
Toggle between absolute timestamps and "3h ago" / "2d ago" format. The `age()`
function already exists in the JS.

#### 16. Color-blind friendly palette option
Add a CSS class that swaps status colors to a deuteranopia-safe palette. Toggle in
header or settings.

---

## Top Recommendation

Start with **Episode & Prototype Browser (#1)** + **Session Replay Viewer (#2)**.
Together they transform the dashboard from a "system monitor" (showing counts of
---

## Progress Tracking

| # | Tier | Feature | Status |
|---|------|---------|--------|
| 1 | 1 | Episode & Prototype Browser | 🟢 implemented |
| 2 | 1 | Session Replay Viewer | 🟢 implemented |
| 3 | 1 | Salience Distribution Histogram | 🟠 removed — implemented then removed (uninformative) |
| 4 | 1 | Supersession / Contradiction Timeline | 🟢 implemented |
| 5 | 2 | Memory Health Score | 🔴 pending |
| 6 | 2 | Scope Activity Comparison | 🔴 pending |
| 7 | 2 | Feedback Event Inspector | 🔴 pending |
| 8 | 2 | Schema Lifecycle Timeline | 🔴 pending |
| 9 | 3 | Latent Space Explorer | 🔴 pending |
| 10 | 3 | Real-time SSE updates | 🔴 pending |
| 11 | 3 | Token Efficiency Dashboard | 🔴 pending |
| 12 | 4 | Export buttons | 🔴 pending |
| 13 | 4 | Keyboard shortcuts | 🔴 pending |
| 14 | 4 | Collapsible stat card sections | 🔴 pending |
| 15 | 4 | Relative time display toggle | 🔴 pending |
| 16 | 4 | Color-blind friendly palette | 🔴 pending |

### Additional polish (July 2026 session)

These items were not in the original plan but were implemented during dashboard cleanup:

| Item | Description |
|------|-------------|
| **Evidence grid redesign** | 4-column CSS grid (Episode\|Kind\|Session\|Weight) with consistent 14px gaps, aligned headers, plain-text kind badges, full session IDs, clean weight display |
| **Schema row highlight** | Expanded schema row gets a subtle background tint for visual context |
| **Expand/collapse fix** | Clicking an already-expanded schema now properly collapses it |
| **Scope tooltip** | Scope list now queries `context_recall_items` for schema-specific scopes (not full registry); shown as hover tooltip |
| **Generalization tab removed** | Stat cards moved into Schemas tab header; redundant promoted list and scope registry panels removed |
| **Cross-browser range slider** | Graph tab salience slider uses `::-webkit-slider-*` / `::-moz-range-*` pseudo-elements instead of Chrome-only `accent-color` |
| **Session timeline overlay** | Session replay opens as fixed bottom-right overlay panel |
| **Supersessions tab** | Added as dedicated tab (was missing from original tab list) |