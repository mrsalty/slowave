# Schema Investigation Cheatsheet

Quick reference for debugging and inspecting Slowave schemas.

## CLI Quick Commands

```bash
# List all schemas
slowave schema                          # human-readable
slowave schema --json | jq              # pretty JSON
slowave schema --needs-review           # only flagged for review

# Find schemas by query
slowave recall "query text" --top-k 5   # search with evidence
slowave recall "text" --evidence --json # full details as JSON

# Show a specific schema/episode/event
slowave show sch_1                      # schema ID 1
slowave show epi_22                     # episode ID 22
slowave show evt_145                    # raw event ID 145

# System stats
slowave stats --json | jq               # overview of database

# Manually consolidate
slowave consolidate                     # trigger replay + schema building
```

## Schema JSON Keys

```json
{
  "id": 1,
  "content_text": "human-readable claim",
  "facets": {
    "schema_class": "preference|decision|fact|...",
    "scope": "domain/context",
    "polarity": "positive|negative|neutral|mixed",
    "stability": "one_off|recurring|current|historical",
    "positive": ["what to prioritize"],
    "negative": ["what to avoid"],
    "entities": ["key entities"]
  },
  "tags": ["search tags"],
  "confidence": 0.0..1.0,          # how sure geometry is
  "salience": 0.0..1.0,             # decays over time, boosted on recall
  "status": "active|needs_review|superseded|contradicted|archived",
  "supporting_episode_ids": [10, 15, 22],
  "contradicting_episode_ids": [],
  "needs_review": false
}
```

## Status Legend

| Status | Meaning | Use in Recall? |
|---|---|---|
| `active` | Current and valid | ✅ Yes |
| `needs_review` | Uncertain; needs inspection | ✅ Yes |
| `superseded` | Replaced by newer schema | ❌ No |
| `contradicted` | Conflicts with newer schema | ❌ No |
| `archived` | No longer relevant | ❌ No |

## Trace Schema → Episode → Event

```bash
# 1. Find schema
slowave recall "your query" --evidence

# 2. Get schema details (shows supporting_episode_ids)
slowave show sch_1 --json

# 3. View an episode
slowave show epi_22 --json  # includes raw_event_ids

# 4. View raw events
slowave show evt_145 --json
```

## SQL Queries (Power User)

```bash
sqlite3 ~/.slowave/slowave.db
```

### By class/scope

```sql
-- Preferences
SELECT id, content_text, salience
FROM schemas
WHERE json_extract(facets, '$.schema_class') = 'preference'
ORDER BY salience DESC;

-- In a domain
SELECT id, content_text, salience
FROM schemas
WHERE json_extract(facets, '$.scope') LIKE '%database%';
```

### By status

```sql
-- Active only
SELECT id, content_text, salience FROM schemas WHERE status = 'active';

-- Needs review
SELECT id, content_text FROM schemas WHERE needs_review = 1;

-- Contradictions
SELECT s1.id, s2.id, s1.content_text, s2.content_text
FROM schema_relations sr
JOIN schemas s1 ON sr.src_schema_id = s1.id
JOIN schemas s2 ON sr.dst_schema_id = s2.id
WHERE sr.relation = 'contradicts';
```

### Evidence chain

```sql
-- Raw events supporting a schema
SELECT se.schema_id, re.type, re.content, re.ts
FROM schema_evidence se
JOIN raw_events re ON se.raw_event_id = re.id
WHERE se.schema_id = 1
ORDER BY re.ts DESC;
```

## Python One-Liners

```python
from slowave.core.engine import SlowaveEngine; eng = SlowaveEngine(); 

# Count
len(eng.list_schemas(limit=1000))

# By status
len([s for s in eng.list_schemas(limit=1000) if s.status == 'active'])

# Top 5 by salience
sorted(eng.list_schemas(limit=1000), key=lambda s: s.salience, reverse=True)[:5]

# Needs review
eng.list_schemas(needs_review=True, limit=1000)

# Search
eng.recall("your query", top_k=5).schemas
```

## Common Issues & Debugging

### "I lost a memory I know I recorded"

1. Check if status is `superseded` or `contradicted`
   ```bash
   slowave schema --json | jq '.[] | select(.status != "active")'
   ```

2. Check if salience decayed to 0 (very old, unused)
   ```bash
   slowave schema --json | jq '.[] | select(.salience < 0.1)'
   ```

3. Search by query instead of browsing
   ```bash
   slowave recall "key phrase from the memory" --evidence
   ```

### "Two contradicting memories exist"

Check which is authoritative:
```bash
slowave show sch_1 --json | jq '{confidence, salience, status}'
slowave show sch_2 --json | jq '{confidence, salience, status}'
```

Higher `confidence` + active status = correct. Consolidation may not have run yet.

### "Why does my recall not return what I expect?"

1. Query might be too different from stored memories (embeddings)
   - Try simpler, more literal keywords
   
2. Schemas may not be consolidated yet
   ```bash
   slowave consolidate  # manually trigger
   ```

3. Check if schemas exist at all
   ```bash
   slowave stats --json | jq '.n_schemas'
   ```

4. Search with evidence to see what episodes were found
   ```bash
   slowave recall "your query" --evidence
   ```

## Debugging Workflow

```bash
# 1. Check system status
slowave stats --json

# 2. Search for what you think should be there
slowave recall "topic" --evidence

# 3. Inspect the top result
slowave show sch_1 --json | jq .

# 4. Trace back to episodes
slowave show epi_22 --json | jq '.raw_event_ids'

# 5. View raw events
slowave show evt_145 --json

# 6. If memories are stale, manually consolidate
slowave consolidate
```

## Files & Paths

```
~/.slowave/slowave.db          # Default database location
SLOWAVE_DB env var            # Override location

docs/debugging-schemas.md      # Full investigation guide (this file's parent)
```

## See Also

- `docs/architecture.md` §10: Schema Structure
- `docs/architecture.md` §9: Consolidation Pipeline
- `docs/agents.md`: Logging & session lifecycle
