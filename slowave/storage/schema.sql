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
  scope_id    TEXT,
  scope_kind  TEXT,
  started_ts  INTEGER NOT NULL,
  ended_ts    INTEGER,
  goal        TEXT,
  outcome     TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_scope ON sessions(scope_id);

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
  episode_id     INTEGER PRIMARY KEY,
  content_text   TEXT NOT NULL,
  source_content TEXT,                -- raw event content joined without role prefix; used as schema claim
  event_ids      TEXT NOT NULL,       -- JSON array of raw_events.id
  session_id     TEXT,
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
  scope_id                 TEXT,
  scope_kind               TEXT,
  status                   TEXT NOT NULL DEFAULT 'active', -- active/needs_review/superseded/contradicted/archived
  confidence               REAL NOT NULL DEFAULT 1.0,
  salience                 REAL NOT NULL DEFAULT 1.0,
  embedding                BLOB,
  dim                      INTEGER,
  -- Facet axes (within-cluster PCA directions, see 05-consolidation.md Phase 2) and
  -- their singular-value strengths, packed as flat float32 blobs (n_facet_axes x dim
  -- and n_facet_axes respectively). Persisted so Consolidator._write_latent_schema can
  -- reconstruct a real "old" LatentSchema view for the geometric judge's facet-distance
  -- comparison, instead of an always-empty placeholder (root cause fixed 2026-07-09 —
  -- see PROGRESS.md). NULL / n_facet_axes=0 means no facet data (legacy row, or the
  -- schema genuinely had fewer than min_members_for_facets member episodes).
  facet_axes               BLOB,
  facet_strengths          BLOB,
  n_facet_axes             INTEGER NOT NULL DEFAULT 0,
  supporting_episode_ids   TEXT NOT NULL DEFAULT '[]',     -- JSON array
  contradicting_episode_ids TEXT NOT NULL DEFAULT '[]',    -- JSON array
  needs_review             INTEGER NOT NULL DEFAULT 0,     -- 0/1
  generalization_stage     INTEGER NOT NULL DEFAULT 0,         -- 0=scoped 1=portable 2=contextual 3=global
  first_formed_ts          INTEGER NOT NULL,
  last_updated_ts          INTEGER NOT NULL,
  FOREIGN KEY (prototype_id) REFERENCES semantic_prototypes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_schemas_prototype ON schemas(prototype_id);
CREATE INDEX IF NOT EXISTS idx_schemas_scope ON schemas(scope_id);
CREATE INDEX IF NOT EXISTS idx_schemas_status ON schemas(status);
CREATE INDEX IF NOT EXISTS idx_schemas_needs_review ON schemas(needs_review);
CREATE INDEX IF NOT EXISTS idx_schemas_gen_stage ON schemas(generalization_stage);

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
-- Trace log for consolidation passes. Append-only, local to benchmark/dev use.
-- Consolidation is zero-LLM; this table records only geometric/embedding-derived
-- data and prototype→schema mappings.
CREATE TABLE IF NOT EXISTS consolidation_debug (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  prototype_id           INTEGER,
  episode_ids            TEXT NOT NULL,
  created_schema_ids     TEXT NOT NULL DEFAULT '[]',
  ts                     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_consolidation_debug_proto ON consolidation_debug(prototype_id);

-- Worker run log: one row per consolidation pass (from `slowave worker` or
-- `slowave consolidate`). Written by SlowaveEngine.consolidate_once().
CREATE TABLE IF NOT EXISTS worker_runs (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  started_ts            INTEGER NOT NULL,
  ended_ts              INTEGER,
  duration_ms           INTEGER,
  triggered_by          TEXT NOT NULL DEFAULT 'worker',  -- 'worker' | 'consolidate' | 'session_end'
  prototypes_processed  INTEGER NOT NULL DEFAULT 0,
  episodes_processed    INTEGER NOT NULL DEFAULT 0,
  schemas_created       INTEGER NOT NULL DEFAULT 0,
  schemas_reinforced    INTEGER NOT NULL DEFAULT 0,
  schemas_contradicted  INTEGER NOT NULL DEFAULT 0,
  schemas_skipped       INTEGER NOT NULL DEFAULT 0,
  procedures_promoted   INTEGER NOT NULL DEFAULT 0,
  procedures_generalized INTEGER NOT NULL DEFAULT 0,
  schemas_decayed       INTEGER NOT NULL DEFAULT 0,
  error_text            TEXT
);
CREATE INDEX IF NOT EXISTS idx_worker_runs_started ON worker_runs(started_ts DESC);

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

-- ============================================================================
-- Feedback system (context-feedback-mcp feature)
-- ============================================================================

-- Retrieval snapshots: one row per slowave_context or slowave_recall response
CREATE TABLE IF NOT EXISTS context_recall_events (
  context_id        TEXT PRIMARY KEY,
  retrieval_type    TEXT NOT NULL DEFAULT 'context', -- context/recall
  session_id        TEXT,
  scope_id          TEXT,
  scope_kind        TEXT,
  application       TEXT,
  query             TEXT,
  goal              TEXT,
  task_type         TEXT,
  situation_json    TEXT NOT NULL DEFAULT '{}',
  requirements_json TEXT NOT NULL DEFAULT '[]',
  mode              TEXT NOT NULL DEFAULT 'default',
  limit_n           INTEGER NOT NULL DEFAULT 8,
  count_n           INTEGER NOT NULL DEFAULT 0,
  topics_json       TEXT NOT NULL DEFAULT '[]',
  entities_json     TEXT NOT NULL DEFAULT '[]',
  cue_terms_json    TEXT NOT NULL DEFAULT '[]',
  suppressed_json   TEXT NOT NULL DEFAULT '{}',
  memory_ids_json   TEXT NOT NULL DEFAULT '[]',
  response_json     TEXT,
  created_at        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_context_recall_session ON context_recall_events(session_id);
CREATE INDEX IF NOT EXISTS idx_context_recall_scope ON context_recall_events(scope_id);
CREATE INDEX IF NOT EXISTS idx_context_recall_created ON context_recall_events(created_at);

-- Retrieval items: one row per memory returned in slowave_context or slowave_recall
CREATE TABLE IF NOT EXISTS context_recall_items (
  context_id        TEXT NOT NULL,
  memory_id         TEXT NOT NULL,
  retrieval_type    TEXT NOT NULL DEFAULT 'context', -- context/recall
  memory_type       TEXT NOT NULL,
  rank              INTEGER NOT NULL,
  activation        REAL,
  reason            TEXT,
  content_text      TEXT,
  status            TEXT,
  salience          REAL,
  confidence        REAL,
  admitted          INTEGER NOT NULL DEFAULT 1, -- 1=selected into context, 0=filtered by gate
  created_at        INTEGER NOT NULL,
  PRIMARY KEY (context_id, memory_id),
  FOREIGN KEY (context_id) REFERENCES context_recall_events(context_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_context_recall_items_memory ON context_recall_items(memory_id);
CREATE INDEX IF NOT EXISTS idx_context_recall_items_type ON context_recall_items(memory_type);

-- Feedback events: one row per slowave_retrieval_feedback/context_feedback call
CREATE TABLE IF NOT EXISTS context_feedback_events (
  id                         INTEGER PRIMARY KEY AUTOINCREMENT,
  context_id                 TEXT NOT NULL,
  retrieval_type             TEXT NOT NULL DEFAULT 'context', -- context/recall
  session_id                 TEXT,
  scope_id                   TEXT,
  scope_kind                 TEXT,
  goal                       TEXT,
  task_type                  TEXT,
  situation_json             TEXT NOT NULL DEFAULT '{}',
  requirements_json          TEXT NOT NULL DEFAULT '[]',
  feedback                   TEXT NOT NULL,
  outcome                    TEXT NOT NULL DEFAULT 'unknown',
  feedback_signal_json       TEXT NOT NULL,
  outcome_reward             REAL NOT NULL DEFAULT 0.0,
  used_memory_ids_json       TEXT NOT NULL DEFAULT '[]',
  irrelevant_memory_ids_json TEXT NOT NULL DEFAULT '[]',
  stale_memory_ids_json      TEXT NOT NULL DEFAULT '[]',
  wrong_memory_ids_json      TEXT NOT NULL DEFAULT '[]',
  used_procedure_ids_json    TEXT NOT NULL DEFAULT '[]',
  irrelevant_procedure_ids_json TEXT NOT NULL DEFAULT '[]',
  stale_procedure_ids_json   TEXT NOT NULL DEFAULT '[]',
  wrong_procedure_ids_json   TEXT NOT NULL DEFAULT '[]',
  missing_context            TEXT,
  notes                      TEXT,
  created_at                 INTEGER NOT NULL,
  FOREIGN KEY (context_id) REFERENCES context_recall_events(context_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_context_feedback_context ON context_feedback_events(context_id);
CREATE INDEX IF NOT EXISTS idx_context_feedback_type ON context_feedback_events(retrieval_type);
CREATE INDEX IF NOT EXISTS idx_context_feedback_session ON context_feedback_events(session_id);
CREATE INDEX IF NOT EXISTS idx_context_feedback_scope ON context_feedback_events(scope_id);
CREATE INDEX IF NOT EXISTS idx_context_feedback_feedback ON context_feedback_events(feedback);
CREATE INDEX IF NOT EXISTS idx_context_feedback_outcome ON context_feedback_events(outcome);
CREATE INDEX IF NOT EXISTS idx_context_feedback_created ON context_feedback_events(created_at);

-- ============================================================================
-- Scope registry: lightweight catalogue of known scopes for generalization
-- ============================================================================

-- One row per distinct scope_id ever seen. Updated on every session_start
-- and activate call. Provides cheap denominator queries for the cross-scope
-- generalization stage computation (scope_breadth_pct, scope_kind_breadth_pct).
CREATE TABLE IF NOT EXISTS scope_registry (
  scope_id         TEXT PRIMARY KEY,
  scope_kind       TEXT,
  first_seen_ts    INTEGER NOT NULL,
  last_active_ts   INTEGER NOT NULL,
  session_count    INTEGER NOT NULL DEFAULT 1,
  recall_count     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_scope_registry_kind ON scope_registry(scope_kind);
CREATE INDEX IF NOT EXISTS idx_scope_registry_last_active ON scope_registry(last_active_ts);

-- ============================================================================
-- Procedural memory system (REMOVED in Phase 1 P1 — 2026-06-25)
-- Procedural behavior is now implicit: schemas + prototypes + TransitionModel
-- + spreading activation. The explicit procedural_memories / procedural_memory_evidence
-- tables are dropped via _apply_post_migrations() in sqlite_db.py for existing DBs.
-- New installs never create them. See docs/iterations/20260625_procedural_phase1_plan.md
-- ============================================================================
