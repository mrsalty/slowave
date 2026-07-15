# Remove reinforces schema relation (2026-07-15)

## Rationale

`reinforces` was a `schema_relations` edge type that encoded "schema A restates/strengthens schema B."
It was classified as symmetric alongside `relates_to`, but semantically it is directional:
"A reinforces B" is not the same fact as "B reinforces A."

However, the edge itself was never consumed by any retrieval path:

- **Spreading activation** — `reinforces` was explicitly excluded (`_GRAPH_EXCLUDED_RELATIONS`).
  It was treated as "same content restated, not a distinct association" — pure redundancy.
- **Dashboard leaderboard** — the only consumer. It did a `COUNT(*) GROUP BY dst_schema_id`
  to show "most-reinforced schemas." This is a count, not an edge traversal.
- **Cross-scope signal** — `increment_cross_scope_reinforcement()` increments a facets counter
  independently. The edge write was a side effect, not the payload.
- **`reinforce()` method** — bumps salience/confidence directly. No edge involvement.

The reinforces edge was dead weight: stored, indexed, and never traversed. The reinforcement
*signal* (salience/confidence bumps, cross-scope counters) lived in entirely independent
code paths. The edge was a redundant ledger entry with no brain analog — biological memory
strengthens the trace itself (LTP), it doesn't keep a separate record of "which memory
reinforced which."

Removing it:

- **Simplifies the taxonomy**: 5 relations → 4 (`refines`, `supersedes`, `part_of`, `relates_to`)
- **Removes the most numerous edge type**: 700+ edges in production that were never traversed
- **Makes the graph useful**: centroid-linked schemas now write `relates_to` (traversable)
  instead of `reinforces` (excluded). Previously related schemas were invisible to spreading activation.
- **Eliminates the directional/symmetric confusion**: with `reinforces` gone, only `relates_to`
  is symmetric — the boundary is clean
- **More brain-like**: reinforcement lives in salience/geometry, not in a typed edge

## Execution

### Judge (`slowave/latent/schema.py`)
- Both `reinforces` return sites collapsed to `relates_to`
- `reinforce_cosine` config field removed — no longer needed as a threshold
- Class docstring updated

### Consolidation (`slowave/core/consolidation.py`)
- `_write_latent_schema`: reinforces branch merged into `relates_to`.
  Cross-scope reinforcement signal re-keyed from `verdict == "reinforces"` to
  `cos >= 0.90` on the `relates_to` branch.
- `_link_schemas_via_prototype_centroid`: simplified. Now only writes `relates_to`
  or nothing. All directional verdicts downgraded to `relates_to` (no directional
  context at this call site).

### Schema store (`slowave/symbolic/schema_store.py`)
- `VALID_RELATIONS`: `("refines", "supersedes", "part_of", "relates_to")`
- `_DIRECTIONAL_RELATIONS`: `{"refines", "supersedes", "part_of"}`
- `add_relation` docstring updated

### Spreading activation (`slowave/core/context.py`)
- `_GRAPH_EXCLUDED_RELATIONS` deleted entirely.
  All 4 remaining relations are now traversed in graph expansion.

### Dashboard (`slowave/dashboard/_js.py`, `app.py`)
- Removed from `relColor`, `relLabel`, `RELATION_TYPES`, legend
- `relates_to` color changed to green (`#3ecf6e`, the old reinforces color)
- `relates_to` graph edges: dashed bidirectional arrows (both ends)
- Tooltips show `↔` for `relates_to`, `→` for directional relations
- `renderReinforcesLeaderboard` function removed
- `VALID_SCHEMA_RELATIONS` in `app.py` updated

### Documentation
- `docs/dashboard.md`: removed reinforces leaderboard mention, updated API docs

### DB migration
```sql
-- Delete reinforces edges that duplicate existing relates_to
DELETE FROM schema_relations WHERE rowid IN (
    SELECT r.rowid FROM schema_relations r
    INNER JOIN schema_relations rt
      ON r.src_schema_id = rt.src_schema_id
     AND r.dst_schema_id = rt.dst_schema_id
    WHERE r.relation = 'reinforces' AND rt.relation = 'relates_to'
);

-- Convert remaining
UPDATE schema_relations SET relation = 'relates_to' WHERE relation = 'reinforces';

-- Clean up old contradicts edges (dead since 2026-07-14)
DELETE FROM schema_relations WHERE relation = 'contradicts';
```
Result: 784 reinforces edges migrated (93 duplicates deleted, 691 converted).
2 contradicts edges cleaned up.

### Tests
- 8 tests updated/removed across 6 test files
- Full unit suite passes (540+ tests)
- E2E reverse-duplicate check updated

## Impact

| Dimension | Before | After |
|---|---|---|
| Relation types | 5 (reinforces, refines, supersedes, part_of, relates_to) | 4 (refines, supersedes, part_of, relates_to) |
| Directional relations | reinforces, refines, supersedes, part_of | refines, supersedes, part_of |
| Symmetric relations | relates_to | relates_to (only) |
| Graph exclusions | reinforces excluded | none — all traversed |
| Centroid linker output | relates_to or reinforces | relates_to only |
| Dashboard relation tabs | 4 (supersedes, refines, part_of, reinforces) | 3 (supersedes, refines, part_of) |
| Cross-scope signal gate | `verdict == "reinforces"` | `cos >= 0.90` on relates_to branch |
| Judge verdicts | unrelated, part_of, supersedes, refines, reinforces, relates_to | unrelated, part_of, supersedes, refines, relates_to |