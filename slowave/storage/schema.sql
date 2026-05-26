-- Slowave schema (SQLite)
-- Origin: merged from SlowWave (latent CLS substrate) + Slowave symbolic layer.
-- Latent layer: vectors stored as BLOB (float32); similarity search via FAISS.
-- Symbolic layer: raw events, episode text, typed schemas, sessions, FTS.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS episodic_memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  ts INTEGER NOT NULL,
  embedding BLOB NOT NULL,
  dim INTEGER NOT NULL,
  salience REAL NOT NULL,
  last_salience_ts INTEGER NOT NULL,
  metadata_json TEXT NOT NULL,
  recalled_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_episodic_ts ON episodic_memories (ts);
CREATE INDEX IF NOT EXISTS idx_episodic_event_id ON episodic_memories (event_id);

CREATE TABLE IF NOT EXISTS semantic_prototypes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  centroid BLOB NOT NULL,
  dim INTEGER NOT NULL,
  support_count INTEGER NOT NULL,
  variance REAL NOT NULL,
  last_updated_ts INTEGER NOT NULL,
  -- Stage 9: CA3 fine / CA1 coarse dual-scale prototypes. Defaults to
  -- 'fine' for backward compatibility (legacy single-scale rows behave
  -- exactly as before).
  scale TEXT NOT NULL DEFAULT 'fine'
);
CREATE INDEX IF NOT EXISTS idx_semantic_proto_scale ON semantic_prototypes (scale);

-- Stage 9: episodes can map to one prototype per scale. The primary
-- key is (episode_id, prototype_id) so a single episode can have
-- multiple memberships, but each (episode, prototype) pair is unique.
CREATE TABLE IF NOT EXISTS episode_prototype_map (
  episode_id INTEGER NOT NULL,
  prototype_id INTEGER NOT NULL,
  PRIMARY KEY (episode_id, prototype_id),
  FOREIGN KEY (episode_id) REFERENCES episodic_memories(id) ON DELETE CASCADE,
  FOREIGN KEY (prototype_id) REFERENCES semantic_prototypes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_map_prototype_id ON episode_prototype_map (prototype_id);
CREATE INDEX IF NOT EXISTS idx_map_episode_id ON episode_prototype_map (episode_id);

-- Sparse directed graph over prototypes
CREATE TABLE IF NOT EXISTS prototype_edges (
  src_prototype_id INTEGER NOT NULL,
  dst_prototype_id INTEGER NOT NULL,
  w_similarity REAL NOT NULL,
  w_transition REAL NOT NULL,
  w_coactivation REAL NOT NULL,
  weight REAL NOT NULL,
  last_updated_ts INTEGER NOT NULL,
  PRIMARY KEY (src_prototype_id, dst_prototype_id),
  FOREIGN KEY (src_prototype_id) REFERENCES semantic_prototypes(id) ON DELETE CASCADE,
  FOREIGN KEY (dst_prototype_id) REFERENCES semantic_prototypes(id) ON DELETE CASCADE
);

-- ==========================================================================
-- Symbolic layer (Slowave additions on top of SlowWave)
-- ==========================================================================

-- Sessions: agent conversations. Scope for events; trigger for replay at end.
CREATE TABLE IF NOT EXISTS sessions (
  id          TEXT PRIMARY KEY,
  agent       TEXT NOT NULL,
  project     TEXT,
  started_ts  INTEGER NOT NULL,
  ended_ts    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);

-- Raw events: canonical source-of-truth log. Everything else cites back here.
CREATE TABLE IF NOT EXISTS raw_events (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id    TEXT NOT NULL,
  ts            INTEGER NOT NULL,
  type          TEXT NOT NULL,
  content       TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  embedding     BLOB,
  dim           INTEGER,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_raw_events_session ON raw_events(session_id);
CREATE INDEX IF NOT EXISTS idx_raw_events_ts ON raw_events(ts);
CREATE INDEX IF NOT EXISTS idx_raw_events_type ON raw_events(type);

-- Episode text + provenance to raw events. 1:1 with episodic_memories.id.
CREATE TABLE IF NOT EXISTS episode_text (
  episode_id    INTEGER PRIMARY KEY,
  content_text  TEXT NOT NULL,
  event_ids     TEXT NOT NULL,        -- JSON array of raw_events.id
  session_id    TEXT,
  FOREIGN KEY (episode_id) REFERENCES episodic_memories(id) ON DELETE CASCADE,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_episode_text_session ON episode_text(session_id);

-- Schemas: durable symbolic memories / typed claims. A schema is a first-class
-- semantic memory: it may be associated with zero/many prototypes and grounded
-- in zero/many episodic/raw evidence rows. This intentionally allows multiple
-- schemas per prototype (one latent theme can support many claims).
CREATE TABLE IF NOT EXISTS schemas (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,
  prototype_id             INTEGER,
  content_text             TEXT NOT NULL,
  facets_json              TEXT NOT NULL DEFAULT '{}',
  tags_json                TEXT NOT NULL DEFAULT '{"tags":[]}',
  project                  TEXT,
  status                   TEXT NOT NULL DEFAULT 'active', -- active/needs_review/superseded/contradicted/archived
  confidence               REAL NOT NULL DEFAULT 1.0,
  salience                 REAL NOT NULL DEFAULT 1.0,
  embedding                BLOB,
  dim                      INTEGER,
  supporting_episode_ids   TEXT NOT NULL DEFAULT '[]',     -- JSON array
  contradicting_episode_ids TEXT NOT NULL DEFAULT '[]',    -- JSON array
  needs_review             INTEGER NOT NULL DEFAULT 0,     -- 0/1
  first_formed_ts          INTEGER NOT NULL,
  last_updated_ts          INTEGER NOT NULL,
  FOREIGN KEY (prototype_id) REFERENCES semantic_prototypes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_schemas_prototype ON schemas(prototype_id);
CREATE INDEX IF NOT EXISTS idx_schemas_project ON schemas(project);
CREATE INDEX IF NOT EXISTS idx_schemas_status ON schemas(status);
CREATE INDEX IF NOT EXISTS idx_schemas_needs_review ON schemas(needs_review);

-- Normalized evidence links for schema provenance. The legacy JSON arrays on
-- schemas are retained for compatibility, but new code should prefer this table.
CREATE TABLE IF NOT EXISTS schema_evidence (
  schema_id    INTEGER NOT NULL,
  episode_id   INTEGER,
  raw_event_id INTEGER,
  quote        TEXT,
  weight       REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (schema_id, episode_id, raw_event_id),
  FOREIGN KEY (schema_id) REFERENCES schemas(id) ON DELETE CASCADE,
  FOREIGN KEY (episode_id) REFERENCES episodic_memories(id) ON DELETE SET NULL,
  FOREIGN KEY (raw_event_id) REFERENCES raw_events(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_schema_evidence_schema ON schema_evidence(schema_id);
CREATE INDEX IF NOT EXISTS idx_schema_evidence_episode ON schema_evidence(episode_id);
CREATE INDEX IF NOT EXISTS idx_schema_evidence_raw_event ON schema_evidence(raw_event_id);

-- Many-to-many link between symbolic schemas and latent prototypes.
CREATE TABLE IF NOT EXISTS schema_prototype_map (
  schema_id    INTEGER NOT NULL,
  prototype_id INTEGER NOT NULL,
  weight       REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (schema_id, prototype_id),
  FOREIGN KEY (schema_id) REFERENCES schemas(id) ON DELETE CASCADE,
  FOREIGN KEY (prototype_id) REFERENCES semantic_prototypes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_schema_prototype_map_proto ON schema_prototype_map(prototype_id);

-- Schema-to-schema memory dynamics: reinforcement, refinement, contradiction,
-- supersession, and loose associations.
CREATE TABLE IF NOT EXISTS schema_relations (
  src_schema_id INTEGER NOT NULL,
  dst_schema_id INTEGER NOT NULL,
  relation      TEXT NOT NULL,
  confidence    REAL NOT NULL DEFAULT 1.0,
  reason        TEXT,
  created_ts    INTEGER NOT NULL,
  PRIMARY KEY (src_schema_id, dst_schema_id, relation),
  FOREIGN KEY (src_schema_id) REFERENCES schemas(id) ON DELETE CASCADE,
  FOREIGN KEY (dst_schema_id) REFERENCES schemas(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_schema_relations_src ON schema_relations(src_schema_id);
CREATE INDEX IF NOT EXISTS idx_schema_relations_dst ON schema_relations(dst_schema_id);

-- Debug/audit trace for consolidation experiments. This is intentionally
-- append-only and local to benchmark/dev use; it records what the LLM saw and
-- what claim candidates were parsed from the response.
CREATE TABLE IF NOT EXISTS consolidation_debug (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  prototype_id           INTEGER,
  episode_ids            TEXT NOT NULL,
  prompt_text            TEXT NOT NULL,
  response_json          TEXT NOT NULL,
  extracted_claims_json  TEXT NOT NULL,
  created_schema_ids     TEXT NOT NULL DEFAULT '[]',
  ts                     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_consolidation_debug_proto ON consolidation_debug(prototype_id);

-- FTS5 over schema content for lexical recall bonus.
CREATE VIRTUAL TABLE IF NOT EXISTS schemas_fts USING fts5(
  content_text
);

-- FTS5 over episode content for lexical recall bonus.
CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
  content_text
);

-- FTS5 over raw events for source-level search.
CREATE VIRTUAL TABLE IF NOT EXISTS raw_events_fts USING fts5(
  content
);
