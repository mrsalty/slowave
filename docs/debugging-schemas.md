# Investigating Schemas in Local Slowave

This guide shows how to query, debug, and understand schemas stored in your local Slowave database.

## Quick Start: CLI Commands

### 1. List All Schemas

```bash
# List all schemas (human-readable)
slowave schema

# Limit to 10 results
slowave schema --limit 10

# JSON output (for parsing)
slowave schema --json

# Only schemas marked for review
slowave schema --needs-review
```

**Output**:
```
  [sch_1] For code review, user prefers detailed feedback over style-only changes  status=active sal=0.856 supports=5 tags=code,review,preferences
  [sch_2] User uses SQLite for prototypes  status=active sal=0.720 supports=3 tags=sqlite,database
```

### 2. Show a Specific Schema

```bash
# View full schema by ID
slowave show sch_1 --json | jq .

# Pretty-print
slowave show sch_1
```

**Output** (JSON):
```json
{
  "id": 1,
  "content_text": "For code review, user prefers detailed feedback over style-only changes",
  "facets": {
    "schema_class": "preference",
    "scope": "code review",
    "polarity": "positive",
    "stability": "current",
    "positive": ["detailed feedback", "architectural insights"],
    "negative": ["style-only changes"],
    "entities": ["code reviews"],
    "attributes": {}
  },
  "tags": ["code", "review", "preferences"],
  "confidence": 0.89,
  "salience": 0.856,
  "status": "active",
  "supporting_episode_ids": [10, 15, 22, 45, 67],
  "needs_review": false,
  "contradicting_episode_ids": []
}
```

### 3. Search Schemas by Query

```bash
# Find schemas relevant to a query
slowave recall "code review preferences" --top-k 5

# Include raw event evidence
slowave recall "code review preferences" --evidence

# JSON output
slowave recall "code review preferences" --json
```

**Output**:
```
=== Schemas ===
  [sch_1] For code review, user prefers detailed feedback over style-only changes  status=active sal=0.856 supports=5

=== Episodes ===
  [epi_22] (sal=0.71) User said: I prefer architectural feedback, not nitpicks...
  [epi_45] (sal=0.65) Claude suggested blunt feedback on design...

=== Raw events (evidence) ===
  [evt_145] user_message: I prefer meat over fish
```

### 4. View System Statistics

```bash
# High-level overview
slowave stats

# JSON with all counts
slowave stats --json
```

**Output**:
```json
{
  "n_sessions": 8,
  "n_episodes": 245,
  "n_episodic_memories": 245,
  "n_prototypes": 18,
  "n_schemas": 12,
  "n_raw_events": 1240
}
```

### 5. Show Episode or Event

```bash
# Show an episode (which schemas/events it contains)
slowave show epi_22 --json

# Show a raw event
slowave show evt_145 --json
```

---

## Python API: Direct Investigation

### Get a Schema by ID

```python
from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine

cfg = SlowaveConfig(db_path="~/.slowave/slowave.db")
eng = SlowaveEngine(cfg)

# Get schema by ID
schema = eng.get_schema(1)
print(f"Schema: {schema.content_text}")
print(f"Status: {schema.status}")
print(f"Salience: {schema.salience}")
print(f"Confidence: {schema.confidence}")
print(f"Supporting episodes: {schema.supporting_episode_ids}")
print(f"Contradicts: {len(schema.contradicting_episode_ids)} schemas")
print(f"Facets: {schema.facets}")

eng.close()
```

### List All Schemas with Filtering

```python
from slowave.core.engine import SlowaveEngine
from slowave.core.config import SlowaveConfig

cfg = SlowaveConfig(db_path="~/.slowave/slowave.db")
eng = SlowaveEngine(cfg)

# List all schemas
all_schemas = eng.list_schemas(limit=100)
for s in all_schemas:
    print(f"[sch_{s.id}] {s.content_text} (sal={s.salience:.2f}, status={s.status})")

# Only active schemas
active = [s for s in all_schemas if s.status == "active"]
print(f"Active schemas: {len(active)}")

# Only those marked for review
review = eng.list_schemas(needs_review=True, limit=100)
print(f"Need review: {len(review)}")

eng.close()
```

### Trace a Schema Back to Episodes

```python
from slowave.core.engine import SlowaveEngine
from slowave.core.config import SlowaveConfig

cfg = SlowaveConfig(db_path="~/.slowave/slowave.db")
eng = SlowaveEngine(cfg)

schema = eng.get_schema(1)

# Get episodes that support this schema
supporting_episode_ids = schema.supporting_episode_ids
for ep_id in supporting_episode_ids:
    ep_text = eng.episode_text.get(ep_id)
    print(f"[epi_{ep_id}] {ep_text.content_text[:100]}...")

# Get raw events that created each episode
for ep_id in supporting_episode_ids[:3]:  # first 3 episodes
    ep_text = eng.episode_text.get(ep_id)
    raw_event_ids = ep_text.raw_event_ids
    for evt_id in raw_event_ids:
        raw_event = eng.raw_log.get(evt_id)
        print(f"  [evt_{evt_id}] {raw_event.type}: {raw_event.content[:80]}...")

eng.close()
```

### Search and Inspect Results

```python
from slowave.core.engine import SlowaveEngine
from slowave.core.config import SlowaveConfig

cfg = SlowaveConfig(db_path="~/.slowave/slowave.db")
eng = SlowaveEngine(cfg)

# Search for memories
result = eng.recall("code review preferences", top_k=5, evidence=True)

# Inspect schemas
print("=== SCHEMAS ===")
for s in result.schemas:
    print(f"[sch_{s.id}] {s.content_text}")
    print(f"  Class: {s.facets.get('schema_class')}")
    print(f"  Scope: {s.facets.get('scope')}")
    print(f"  Status: {s.status}, Salience: {s.salience:.3f}")
    print(f"  Supports: {len(s.supporting_episode_ids)} episodes")
    print(f"  Tags: {', '.join(s.tags)}")

# Inspect episodes
print("\n=== EPISODES ===")
for ep in result.episode_texts:
    print(f"[epi_{ep['id']}] {ep['content_text'][:100]}...")
    print(f"  Salience: {ep['salience']:.3f}")

# Inspect raw events (if evidence=True)
print("\n=== RAW EVENTS ===")
for evt in result.raw_events:
    print(f"[evt_{evt['id']}] {evt['type']}: {evt['content'][:100]}...")

eng.close()
```

---

## Direct SQLite Queries

For power users: query the database directly.

### Common Queries

```bash
# Connect to database
sqlite3 ~/.slowave/slowave.db
```

#### List all schemas with key fields

```sql
SELECT id, content_text, status, salience, confidence, 
       COUNT(DISTINCT se.episode_id) as support_count
FROM schemas s
LEFT JOIN schema_evidence se ON s.id = se.schema_id
GROUP BY s.id
ORDER BY s.salience DESC
LIMIT 20;
```

#### Find schemas by class

```sql
SELECT id, content_text, status, salience
FROM schemas
WHERE json_extract(facets, '$.schema_class') = 'preference'
ORDER BY salience DESC;
```

#### Find schemas by scope (domain)

```sql
SELECT id, content_text, status, salience
FROM schemas
WHERE json_extract(facets, '$.scope') LIKE '%code%'
ORDER BY salience DESC;
```

#### Find schemas marked for review

```sql
SELECT id, content_text, status, salience, needs_review
FROM schemas
WHERE needs_review = 1
ORDER BY salience DESC;
```

#### Find schemas with low confidence

```sql
SELECT id, content_text, confidence, salience, support_count
FROM schemas
WHERE confidence < 0.7
ORDER BY confidence;
```

#### Find contradictions

```sql
SELECT sr.src_schema_id, sr.dst_schema_id, sr.relation, sr.confidence,
       s1.content_text as source_schema,
       s2.content_text as target_schema
FROM schema_relations sr
JOIN schemas s1 ON sr.src_schema_id = s1.id
JOIN schemas s2 ON sr.dst_schema_id = s2.id
WHERE sr.relation IN ('contradicts', 'supersedes')
ORDER BY sr.confidence DESC;
```

#### Show evidence for a schema (raw events)

```sql
SELECT se.schema_id, se.episode_id, se.raw_event_id, 
       re.type, re.content
FROM schema_evidence se
JOIN raw_events re ON se.raw_event_id = re.id
WHERE se.schema_id = 1  -- replace with your schema ID
ORDER BY re.ts DESC;
```

#### Show schema relations graph

```sql
SELECT src_schema_id, dst_schema_id, relation, confidence
FROM schema_relations
WHERE relation IN ('reinforces', 'refines', 'contradicts', 'supersedes')
ORDER BY confidence DESC
LIMIT 30;
```

#### Find newest schemas

```sql
SELECT id, content_text, status, created_at
FROM schemas
ORDER BY created_at DESC
LIMIT 20;
```

---

## Debugging: Common Investigations

### Problem: A schema has low salience. Why?

```python
from slowave.core.engine import SlowaveEngine
from slowave.core.config import SlowaveConfig

cfg = SlowaveConfig(db_path="~/.slowave/slowave.db")
eng = SlowaveEngine(cfg)

schema = eng.get_schema(5)  # replace with your schema ID
print(f"Schema: {schema.content_text}")
print(f"Current salience: {schema.salience}")
print(f"Confidence: {schema.confidence}")
print(f"Support count: {len(schema.supporting_episode_ids)}")

# Why low salience?
# 1. Not recalled recently (salience decays with time)
# 2. Low confidence (geometry-based score)
# 3. Marked as superseded/contradicted (status != active)

print(f"Status: {schema.status}")
if schema.contradicting_episode_ids:
    print(f"Contradicted by {len(schema.contradicting_episode_ids)} schemas")

# Solution: If it's important, call slowave_remember() to boost salience
eng.close()
```

### Problem: Two contradicting schemas exist. Which is right?

```python
from slowave.core.engine import SlowaveEngine
from slowave.core.config import SlowaveConfig

cfg = SlowaveConfig(db_path="~/.slowave/slowave.db")
eng = SlowaveEngine(cfg)

# Get both schemas
s1 = eng.get_schema(1)
s2 = eng.get_schema(2)

print(f"Schema 1: {s1.content_text}")
print(f"  Confidence: {s1.confidence}, Salience: {s1.salience}, Status: {s1.status}")
print(f"  Supporting episodes: {len(s1.supporting_episode_ids)}")

print(f"\nSchema 2: {s2.content_text}")
print(f"  Confidence: {s2.confidence}, Salience: {s2.salience}, Status: {s2.status}")
print(f"  Supporting episodes: {len(s2.supporting_episode_ids)}")

# Winner: higher confidence + newer + active status
if s1.confidence > s2.confidence and s1.status == "active":
    print("\n→ Schema 1 is authoritative")
else:
    print("\n→ Schema 2 is authoritative")

# If needed, manually mark one as superseded:
eng.schemas.update_status(s2.id, "superseded")

eng.close()
```

### Problem: Want to trace why a query returned a certain schema

```bash
# Use recall with evidence
slowave recall "my query" --evidence --json | jq '.schemas[0]'

# Then show all supporting episodes
slowave show epi_22  # one of the supporting episodes
```

---

## Schema Facets: What Do They Mean?

When inspecting a schema, you'll see facets:

```json
{
  "schema_class": "preference|decision|fact|habit|constraint|warning|lesson|artifact",
  "scope": "context/domain where this applies",
  "polarity": "positive|negative|neutral|mixed",
  "stability": "one_off|recurring|current|historical",
  "positive": ["what to prioritize"],
  "negative": ["what to avoid"],
  "entities": ["named entities mentioned"],
  "attributes": {"custom": "structured data"}
}
```

**Examples**:

```json
{
  "schema_class": "preference",
  "scope": "code review",
  "polarity": "positive",
  "stability": "current",
  "positive": ["detailed feedback", "architectural insights"],
  "negative": ["style-only changes", "nitpicks"]
}
```

```json
{
  "schema_class": "decision",
  "scope": "database selection",
  "stability": "recurring",
  "positive": ["SQLite for prototypes"],
  "entities": ["SQLite", "PostgreSQL"]
}
```

---

## Status Values: What Do They Mean?

- **`active`**: Current and valid; used in recall
- **`needs_review`**: Uncertain; marked for manual inspection
- **`superseded`**: Older version of a concept; replaced by newer schema
- **`contradicted`**: Conflicts with newer, more confident schema
- **`archived`**: Explicitly marked as no longer relevant

---

## Performance Tips

- **For many schemas**: use `slowave schema --json | jq` for scripting
- **For history**: check `created_at` and `updated_at` timestamps in raw SQL
- **For large result sets**: increase `--limit` but be aware of memory
- **For JSON parsing**: pipe to `jq` or parse in Python

