# Slowave Core Architecture

*Personal reference document — generated 2026-07-03 from a full scan of the codebase (dashboard excluded). ~10.7k lines across `latent/`, `symbolic/`, `core/`, `storage/`, `mcp/`.*

---

## 1. Core thesis

Slowave is a neuroscience-inspired long-term memory system for AI agents. The central claim: **memory consolidation does not require language**. The LLM is an output-only channel (verbalization), never a memory operator. Consolidation runs entirely in "brain-only" mode — pure geometry over embeddings, zero LLM calls, no Ollama, no cloud service. All durable state lives in a single SQLite file (`~/.slowave/slowave.db` or `$SLOWAVE_DB`).

North star: mimic how the brain actually works. No patches that add complexity unless supported by a brain-like architecture.

## 2. System map

```
                       ┌────────────────────────────────────────────┐
                       │              MCP layer (slowave/mcp)        │
                       │  stdio server │ HTTP daemon │ 6 tools       │
                       │  SessionResolver · SessionReaper · Compact  │
                       └───────────────────┬────────────────────────┘
                                           │
                       ┌───────────────────▼────────────────────────┐
                       │        SlowaveEngine (core/engine.py)       │
                       │  facade wiring everything below             │
                       │  services/: Ingest · Retrieval ·            │
                       │             Consolidation · Feedback        │
                       └───────┬──────────────────────┬─────────────┘
                               │                      │
        ┌──────────────────────▼──────┐   ┌───────────▼─────────────────┐
        │  LATENT (geometry, no text) │   │  SYMBOLIC (language surface) │
        │  EpisodicStore              │   │  RawLog                      │
        │  SemanticStore (fine/coarse)│   │  EpisodeTextStore            │
        │  GraphManager               │   │  SchemaStore                 │
        │  TransitionModel            │   │  TextEncoder (ONNX, 384-d)   │
        │  ReplayEngine               │   └───────────┬─────────────────┘
        │  RetrievalPipeline          │               │
        │  LatentSchemaBuilder        │               │
        │  TemporalContext/Probe      │               │
        │  SalienceEngine · VSA       │               │
        └──────────────┬──────────────┘               │
                       │                              │
        ┌──────────────▼──────────────────────────────▼──────────────┐
        │  STORAGE: single SQLite (WAL) + in-memory FAISS             │
        │  (FAISS rebuilt from SQLite at startup, never persisted)    │
        └─────────────────────────────────────────────────────────────┘
```

Core cross-cutting modules in `core/`: `WorkingMemoryGate` (context.py), `SupersessionManifold`, `FeedbackSystem` (feedback.py), `Consolidator` (consolidation.py), `scope.py`, `paths.py`, `config.py`.

> **Removed:** `ProceduralMemoryStore` (`core/procedural.py`) was fully deleted in Phase 1 P1 (2026-06-25). The `procedural_memories` / `procedural_memory_evidence` tables are dropped by post-migrations. Procedural behavior is now implicit via graph edges + TransitionModel + schemas typed task/decision/lesson. `engine.stats()["procedures"]` returns a hardcoded 0.

## 3. Latent layer (`slowave/latent/`) — geometry only

### 3.1 Data types (`types.py`)

Frozen dataclasses: `Event` (event_id, ts, type, entities, embedding, metadata), `EpisodicMemory` (id, event_id, ts, embedding, salience, recalled_count, metadata), `SemanticPrototype` (id, centroid, support_count, variance, last_updated_ts), `RetrievedMemorySet` (query_embedding, episodic ranked list, prototypes, expanded_neighbors).

### 3.2 EpisodicStore (`episodic_store.py`)

Append-only episode storage. Rows in SQLite (`episodic_memories`), vectors in FAISS `IndexFlatIP` wrapped in `IndexIDMap2` (inner product over L2-normalized = cosine). Key API: `add()`, `get/get_many()`, `search(query, top_k)`, `update_salience()`, `increment_recall(ids, reinforcement)`, `load_embeddings()`, `reset_faiss_from_db()` (rebuild at startup — FAISS is never persisted). Episodes are never deleted; salience decays instead.

### 3.3 SemanticStore (`semantic_store.py`)

Prototype centroids at **two scales** (Stage 9, `scale` column):

- **fine** (CA3 analogue) — exact retrieval
- **coarse** (CA1 analogue) — pattern completion; agreement between scales is a confidence signal

API: `upsert_prototype(centroid, support_count, variance, scale)`, `map_episode_to_prototype()` (INSERT OR IGNORE — an episode can map to one prototype *per scale*), `episodes_for_prototypes(per_prototype=8)`, `search_by_scale(query, scale, top_k)` (over-fetches `max(top_k*4, 16)` then SQL-filters by scale).

### 3.4 GraphManager (`graph_manager.py`)

Sparse directed graph over prototypes (`prototype_edges`). Each edge fuses three components:

```
weight = 1.0·w_similarity + 0.5·w_transition + 0.3·w_coactivation
```

- Similarity edges: top-8 cosine neighbors per prototype (`top_k_similarity=8`)
- Coactivation edges: top-6 per source (`top_k_coactivation=6`)
- Transition edges: conditional probabilities P(dst|src) from time-ordered episode sequences
- Edges below `prune_below=0.05` are deleted — sparsity is essential; without pruning, spreading activation over-inflates

### 3.5 TransitionModel (`transition_model.py`)

Graph-based successor representation — **no neural net, no torch**. `predict(e_t)`: find nearest prototype (FAISS top-1) → look up successor prototypes via `w_transition > 0` edges (top-5) → return weighted average of successor centroids. `train_batch()` is a no-op that increments `trained_steps`; actual learning happens Hebbianly during replay via transition-edge counting. `trained_steps == 0` gates prediction off in retrieval. Also provides prediction-error surprise for episode salience.

### 3.6 SalienceEngine (`salience.py`)

- Decay: `s' = max(0.01, s · exp(−dt/τ))`, `tau_seconds = 3600`
- Novelty at ingest: `(1 − nn_cosine) / 2`
- Recall reinforcement: `+0.2` per retrieval (cosine-direct hits only)
- Post-consolidation penalty: `s' = 0.5·s`
- `sample_proportional()` — salience-weighted sampling for replay

### 3.7 ReplayEngine (`replay_engine.py`) — offline consolidation

`replay_once()` (one pass):

1. **Decay** all episode saliences (exp decay, floor 0.01)
2. **Sample** 256 episodes proportional to salience (`sample_size=256`)
3. **Assign to fine prototypes**: nearest centroid; if cosine ≥ `assignment_threshold=0.60` → incremental update (`c_new = (n·c_old + e)/(n+1)`, online variance), else create new (cap `max_prototypes_per_replay=32`)
4. **Assign to coarse prototypes** (multi-scale, same episodes, `coarse_assignment_threshold=0.60`)
5. **Graph update**: coactivation +1 per co-selected pair (top-6/source); transition counts from time-sorted proto sequences → P(dst|src); similarity edges recomputed on touched prototypes; prune < 0.05
6. **Train transition model**: 50 steps × batch 64 over (e_t, e_{t+1}) pairs (bumps `trained_steps`)
7. **Penalize** consolidated episodes: salience × 0.5

`self_supervise()` (Stage 5 — retrieval rehearsal): for each prototype with ≥3 members, probe retrieval with the most recent member; missed siblings get **+0.5** coactivation on the bridge edge (bidirectional), foreign confusers get **−0.25**. This is how missed associative bridges get repaired without labels.

Pattern separation (Stage 8, `use_pattern_separation=False` by default — empirically neutral-to-negative): penalize assignment by `best_sim − 0.5·runner_up_sim`.

### 3.8 RetrievalPipeline (`retrieval.py`) — multi-mechanism recall

Given a query embedding, seven steps:

1. **Cosine seeds** — episodic top-10 (`episodic_top_k`); fine prototypes top-6; coarse prototypes top-6 (harvest their episodes into a co-occurrence set)
2. **Predictive completion** (Stage 3) — if TransitionModel trained and ‖pred‖ ≥ 0.01: episodic search on predicted next-state, scores discounted × `transition_score_weight=0.7`, max-merged (never downgrades a direct hit)
3. **Spreading activation** (Stage 1) — 2 steps over the prototype graph:
   `a_{t+1}[p] = 0.6·a_t[p] + 0.4·Σ_q (w_norm(q→p)·a_t[q])` with locally L1-normalized weights, prune < 1e-3; optional salience gate `× (1 + 0.1·√(1+support_count))`
4. **Harvest graph episodes** — up to 6 per activated prototype; base score `0.15·min(1, activation)`, ceilinged at `0.9 × worst cosine score` (graph episodes can *fill gaps* but never out-rank direct hits), modulated by `(0.5 + 0.5·salience)`
5. **Final ranking** — `merged + 0.3·salience + 0.25·temporal_bonus`; ×1.25 multi-scale co-occurrence bonus if the episode also surfaced via a coarse prototype
6. **Diversity cap** — graph-harvested episodes capped at 2 per prototype (cosine-direct exempt)
7. **Predictive-seed reserve** — 1 head slot for the top predictive episode, only if cos(q, pred) < 0.85 (the prediction actually moved somewhere)

Reinforcement discipline: only the cosine-direct top-k get `+0.2` salience on recall — graph-harvested episodes are never reinforced, preventing a self-rewarding feedback loop.

### 3.9 Temporal context (`temporal.py`)

- **TemporalContext** — deterministic multi-scale sinusoidal encoding of a timestamp: 7 scales (minute, hour, day, week, month, year, decade) × (sin, cos) = 14-d unit vector. Episodes near in time have high temporal cosine.
- **TemporalProbe** (Stage 10) — estimates a query's temporal anchor from 12 pre-embedded landmark phrases ("yesterday", "last week", … "years ago"). Dead-zone: if `best_past_sim − now_sim < 0.12` the query is atemporal → anchor = now. Otherwise softmax (T=0.05) over probe similarities → expected displacement → `anchor_ts`. The anchor feeds `RetrievalConfig.temporal_anchor_ts` so past-anchored queries bias toward old episodes.

### 3.10 LatentSchemaBuilder (`schema.py`) — Stage 6

Turns a prototype + member episodes into a **LatentSchema**, deterministically:

- centroid; **facet axes** = top-4 SVD principal directions of `(embeddings − centroid)` with variance-explained strengths (`n_facet_axes=4`, needs ≥3 members)
- **confidence** = `1 − min(1, within_var / variance_floor)` with `variance_floor=1e-2` (tight cluster ≈3e-4 → conf ≈0.97)
- central episode = argmax cosine to centroid; its `source_content` becomes the claim text
- **lexical signature** (Stage 7a) — contrastive TF-IDF over cluster vs corpus texts, top 8 terms; top 3 joined as `display_label`
- temporal anchor: `mean_ts`, `ts_span_s`
- **VSA binding** (Stage 11, `vsa.py`) — circular convolution (FFT) role binding; geometric mode binds (centroid, facet_axis0, facet_axis1) as S-P-O; role vectors seeded with `0x516C6176` ("Slav") — never change post-0.1.6

**GeometricContradictionJudge** — compares a new LatentSchema to the closest existing schema, verdict ∈ {reinforces, refines, contradicts, unrelated}: centroid cos < 0.75 → unrelated; ≥ 0.95 → reinforces; else facet distance `1 − mean|cos(axes)|` ≥ 0.35 → contradicts.

## 4. Symbolic layer (`slowave/symbolic/`)

### 4.1 RawLog (`raw_log.py`)

Canonical append-only event log (`raw_events` + FTS5). Everything cites raw event ids for provenance. `append(session_id, type, content, metadata, embedding)`, `list_session()`, `search_fts()`. Also owns session rows (`start_session`, `end_session`).

### 4.2 EpisodeTextStore (`episode_text.py`)

1:1 human-readable wrapper for latent episodes (`episode_text` table, PK = `episodic_memories.id`): `content_text` (summary), `source_content` (raw text without role prefix — used as schema claim), `event_ids` JSON provenance, FTS index.

### 4.3 SchemaStore (`schema_store.py`) — the heavyweight

First-class semantic memories. `Schema`: content_text, facets (schema_class, scope, polarity, stability, entities, computed utility metrics, generalization counters, `source_kind`), tags, scope_id, **status** ∈ {active, needs_review, superseded, contradicted, archived}, confidence [0-1], salience, embedding BLOB, supporting/contradicting episode ids, `generalization_stage`.

Key mechanics:

- **create(dedupe=True)** — scope-aware duplicate check (normalized text) merges into the existing schema instead of inserting
- **reinforce_schema()** — merge provenance/facets/tags, salience `+0.2`
- **`canonical_schema_text()`** — enriched multi-line text (Claim/Class/Scope/Polarity/…/Tags) is what gets embedded, improving semantic retrieval
- **`_update_utility_scores()`** — `stability_score` (age + support, saturates ~10 episodes), `recurrence_score = hits/(hits+5)`, `schema_utility = 0.5·stability + 0.5·recurrence`; also recomputes cross-scope metrics and generalization stage
- **relations** (`schema_relations`): reinforces, refines, contradicts, supersedes, related_to, part_of
- **decay_unused(idle_days=30)** — suppress never-recalled schemas; `explicit_remember` schemas exempt; flags needs_review below salience 0.30
- `search_embedding()` (Python-side cosine over BLOB embeddings), `search_fts()`, `schemas_for_episodes()` (reverse index used by retrieval for schema priors)

**Cross-scope generalization (Stage 11)** — schemas promote through 4 stages based on breadth of *observed usefulness* (distinct scopes/scope-kinds/sessions from recall + evidence, tracked via `scope_registry`, 90-day active window):

| Stage | Visibility | Promotion gate (defaults) |
|---|---|---|
| 0 Scoped | origin scope only | default |
| 1 Portable | same scope_kind | ≥25% scope breadth, ≥2 scopes, ≥2 sessions |
| 2 Contextual | all scopes, score ×0.70 | ≥50% breadth, ≥40% kind breadth, ≥4 scopes, ≥3 sessions |
| 3 Global | everywhere, no penalty | ≥75% breadth, ≥75% kind breadth, ≥8 scopes, ≥5 sessions |

Cross-scope admission also requires activation ≥ `cross_scope_min_score=0.40`. Offline cross-scope reinforcements count as 0.5-equivalent scopes.

### 4.4 TextEncoder (`encoder.py`, `onnx_encoder.py`)

Lazy-loaded facade. Default backend: **ONNX Runtime** (no torch), model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-d, multilingual) fetched as the Xenova ONNX conversion from HF Hub. Mean pooling over attention mask, L2-normalized float32. Falls back to sentence-transformers when `use_onnx=False`. Nothing loads until the first `encode()`/`dim` access — tests with synthetic vectors never pay the import.

> Note: CLAUDE.md still says `all-MiniLM-L6-v2`; the code default is the multilingual L12 model. Dim is 384 either way.

## 5. Core engine & services (`slowave/core/`)

### 5.1 SlowaveEngine (`engine.py`)

Facade constructed via `SlowaveEngine.from_config(cfg, shared_encoder=None)`. Wires: salience, episodic, semantic, graph, transition model, replay engine (latent); raw log, episode text, schema store, working memory gate (symbolic); encoder (unless `disable_encoder`); Consolidator; lazy SupersessionManifold; lazy TemporalProbe; and four services.

Public API: `session_start / event_append / session_end`, `remember`, `recall`, `context`, `context_brief`, `consolidate_once`, `record_retrieval / retrieval_feedback` (+ context variants), `stats`, `schema_health`, `dedup_schemas_exact`, `decay_schemas`, `refresh_indices`, `close`.

### 5.2 IngestService (`services/ingest.py`)

`form_episodes(session_id)` — turns a session's raw events into multi-scale episodes:

- **micro** episodes: sliding window of 2 adjacent events (preserves user↔assistant exchanges) or singletons; embedding = mean; salience = novelty + 0.3·surprise (transition-model prediction error)
- **macro** episode: whole session mean; salience = micro × 0.8
- `remember:*` events boost salience +0.6; `context_query` events are excluded (retrieval cues are not memories)

### 5.3 RetrievalService (`services/retrieval.py`)

`recall(query, top_k, scope, mode)`:

- Encode query; TemporalProbe estimates anchor_ts; run RetrievalPipeline
- **Schemas compete via 3 paths**: embedding (`cos + 0.25`), FTS (`0.35`), prototype-linkage (`0.15 + salience×0.05`); plus salience bonus `0.3 · σ(salience)` where `σ(s) = 2/(1+e^(−s/2)) − 1`
- Profile schemas (`memory_layer='profile'`) always injected; Stage ≥1 schemas from other scopes injected unless `mode="strict_scope"`
- Mode gating: default → active only; broad → +needs_review; debug → everything
- **Schema priors on episodes** (belief revision): episodes linked to matching schemas get `+0.08·qsim·conf·(1+0.5·utility)`; episodes linked to superseded/contradicted schemas are silenced by `max(0.05, 1 − 0.6·freshness·conf)` with a 14-day half-life
- Dedup by normalized text

`context_brief(...)` — builds candidate pool (FTS + embedding + stage-promoted cross-scope), constructs a `MemoryCue`, delegates to `WorkingMemoryGate.select()` with policy (max_items, `max_chars=1800`, `max_item_chars=500`, `min_activation=0.20`).

### 5.4 ConsolidationService (`services/consolidation.py`)

`consolidate_once(triggered_by)` — ordering is load-bearing:

1. `replay_engine.replay_once()` (clusters, graph, transition model)
2. `consolidator.consolidate(all prototypes)` (latent → symbolic schema lift + geometric judgment)
3. `schemas.decay_unused(idle_days=30)`
4. Audit row in `worker_runs`

**Consolidator** (`core/consolidation.py`) per prototype: fetch ≤8 member episodes + embeddings + timestamps → `LatentSchemaBuilder.build()` → find best related existing schema (embedding ≥0.72 or FTS fallback) → `GeometricContradictionJudge.judge()`:

- contradicts → mark old superseded/contradicted (time-delta dependent) + relation edge
- reinforces/refines → relation edge, possibly cross-scope reinforcement counter
- unrelated → create new schema (with dedupe)

Classification heuristic: ≥3 sentences or >300 chars → `episodic_summary` tag, else `fact`.

Session-end is a **fast path** — `session_end(consolidate=False)` only forms episodes (never blocks the agent); all heavy lifting is deferred to the worker.

### 5.5 FeedbackService (`services/feedback.py`) + FeedbackSystem (`core/feedback.py`)

`record_retrieval()` persists a full retrieval snapshot (`context_recall_events` + one row per returned/filtered item in `context_recall_items` with `admitted` 1/0 — the suppressed pool is recorded too).

`retrieval_feedback(retrieval_id, feedback, outcome, ...)` auto-derives context from the snapshot, maps the label to a numeric signal, and applies deltas:

| Label | salience Δ | confidence Δ | review pressure |
|---|---|---|---|
| useful | +0.10 | +0.02 | — |
| partially_useful | +0.04 | — | — |
| irrelevant | −0.05 | — | — |
| stale | −0.20 | −0.20 | 0.7 (needs_review) |
| wrong | −0.30 | −0.40 | 1.0 (needs_review; escalates on outcome=failure) |
| missing / too_much_context | signal-only | — | — |

Source weighting: recall feedback ×1.0, context feedback ×0.5. Bounds: salience ≥0.01, confidence ∈ [0,1].

### 5.6 WorkingMemoryGate (`core/context.py`)

Two-stage gate for prompt injection:

**Stage 1 — eligibility**: status by mode; scope boundary by generalization stage (Stage 0 hard-blocked cross-scope, Stage 1 same-kind only, Stage 2 admitted with penalty, Stage 3 transparent); facet filters (`injectable != False`, excluded classes/layers/sources); multi-sentence-summary gate (≥3 sentences or >300 chars excluded unless explicit_remember or broad/debug).

**Stage 2 — activation score** (∈ [0,~1]), main components: geometric cosine ×0.40, lexical overlap up to +0.40, salience `min(1, s/20)` ×0.15, class bonus +0.07–0.12, stability +0.08, utility up to +0.12, layer bonus (profile +0.12), explicit_remember +0.12, scope match +0.20 / mismatch −0.35, verbose inhibition −0.12 (>500 chars), assistant-text penalty −0.15.

Then: cross-scope noise floors (activation ≥0.30 AND cosine ≥0.25 for Stage 1/2 imports), MMR dedup (cos ≥0.92), budget enforcement (max_items, max_chars). Output `WorkingMemoryState` with items, rendered markdown (`- [sch_<id>] …`), suppressed-reason counters, and an activation trace for debugging.

### 5.7 SupersessionManifold (`core/supersession_manifold.py`)

One direction in embedding space that explains value-substitution ("X was A, now it's B") across **7 domains** (tech, medical, business, financial, HR, legal, science) + multilingual seeds (IT/FR/DE) — 60 seed pairs. Computation: embed (old, new) pairs → unit-normalized difference vectors → SVD → first right singular vector, sign-oriented by majority vote. Lazy, invalidated if encoder changes.

`direction_score(emb_new, emb_old)` feeds `remember()`'s decision tree:

| Condition | dir_score | Action |
|---|---|---|
| same scope, cos ≥ 0.85 | ≥ 0.10 | supersede (status + `supersedes` relation) |
| | 0.05–0.10 | needs_review |
| | < 0.05 | reinforce (salience +0.1) |
| same scope, cos 0.70–0.85 | ≥ 0.10 | supersede |
| cross-scope, cos ≥ 0.78 | < 0.10 | reinforce + evidence (salience +0.05) |
| | ≥ 0.10 | skip (cross-scope facts diverge independently) |

Empirical calibration (2026-06-19, 104 pairs): SVD1 separation sup-vs-additive +0.35 vs +0.09.

### 5.8 Config (`core/config.py`)

`SlowaveConfig` (frozen): `db_path`, `dim=384`, `encoder: EncoderConfig`, per-subsystem `salience/replay/graph/retrieval/transition/feedback` configs, `disable_encoder=False` (FTS-only fallback, cheap instances), and the convenience `assignment_threshold: float | None` shorthand that overrides both fine and coarse replay thresholds (0.60 = broad clusters, 0.85 = fine-grained precision).

`scope.py`: `normalize_scope`, `scope_kind` ("project:slowave" → "project"; unprefixed → "generic"), `scope_value`. `paths.py`: `default_db_path()` = `$SLOWAVE_DB` or `~/.slowave/slowave.db`.

## 6. Storage (`slowave/storage/`)

### 6.1 SQLiteDB (`sqlite_db.py`)

Thread-safe wrapper: per-thread connections via `threading.local()`. Pragmas: WAL, `busy_timeout=30000`, `synchronous=NORMAL`, 64MB cache, `temp_store=MEMORY`, FKs on. `init_schema()` = pre-migrations (add missing columns, try/except duplicate-column) → idempotent `schema.sql` → post-migrations (drop procedural tables; rebuild `episode_prototype_map` PK to composite for multi-scale; partial UNIQUE index for NULL `raw_event_id` in evidence).

### 6.2 Tables (schema.sql)

**Latent:** `episodic_memories` (embedding BLOB + dim, salience, recalled_count, metadata) · `semantic_prototypes` (centroid, support_count, variance, `scale` fine/coarse) · `episode_prototype_map` (composite PK — one mapping per scale) · `prototype_edges` (w_similarity/w_transition/w_coactivation + fused weight)

**Symbolic:** `sessions` (agent, scope_id/kind, goal, outcome, started/ended_ts) · `raw_events` · `episode_text` · `schemas` (facets_json, status, confidence, salience, embedding, generalization_stage) · `schema_evidence` (normalized provenance) · `schema_prototype_map` (many-to-many) · `schema_relations`

**Feedback:** `context_recall_events` (retrieval snapshots) · `context_recall_items` (per-memory, `admitted` flag) · `context_feedback_events` (labels, outcome, per-category memory-id lists)

**Infra:** `scope_registry` (scope catalogue for generalization denominators) · `worker_runs` (consolidation audit) · `consolidation_debug` · FTS5 virtual tables: `schemas_fts`, `episodes_fts`, `raw_events_fts`

Embeddings serialize via `pack_f32`/`unpack_f32` (raw float32 bytes, dim stored beside). FAISS indexes are in-memory only, rebuilt from SQLite at startup.

## 7. MCP layer (`slowave/mcp/`)

### 7.1 Tools (`tools.py` — shared `register_tools()` for both transports)

| Tool | Engine path | Returns |
|---|---|---|
| `slowave_activate` | `session_start` → `SessionResolver.bind(scope, sid)` → `context_brief` → bg `record_context_recall` + bg `event_append(context_query)` | `retrieval_id` (ctx_*), session_id, rendered brief, compact schemas, `cold_start` flag (scope has 0 schemas) |
| `slowave_remember` | resolve implicit session → `engine.remember` | stored, event_id |
| `slowave_recall` | `engine.recall` → CompactSchema → bg `record_retrieval` | `retrieval_id` (rec_*), memories |
| `slowave_reinforce` | `engine.retrieval_feedback` (context auto-derived from snapshot) | applied deltas |
| `slowave_commit` | resolve session → bg `event_append(task_complete)` → `session_end(consolidate=False)` → `SessionResolver.clear(scope)` | session_id, episodes_formed |
| `slowave_stats` | `engine.stats()` | counts |

All metric/logging writes are fire-and-forget `asyncio.create_task()` — tools never block on bookkeeping. Old tools (slowave_context, session_start/end, event, retrieval_feedback, context_feedback) are deleted.

### 7.2 Transports

- **stdio** (`server.py`, entry `slowave-mcp`): FastMCP subprocess; logs to `~/.slowave/logs/mcp-stdio.log` (stdout must stay clean for JSON-RPC); idle watchdog `SLOWAVE_MCP_IDLE_TIMEOUT=1800s` exits via `os._exit(0)` (anti-zombie when a client abandons stdin)
- **HTTP daemon** (`http_server.py`, entry `slowave-mcp-http` / `slowave serve --http`): uvicorn+starlette on `127.0.0.1:8766`; endpoints `/mcp` (streamable-HTTP), `/sse` + `/messages` (legacy), `/health` (no engine load); idle timeout disabled (0) since HTTP clients reconnect; **single-instance via PID file** (`daemon.py`: `~/.slowave/daemon.pid`, alive-check + command-line-contains-"slowave" verification against PID reuse, stale-file cleanup, remove-only-if-own-pid)

Both cache engine singletons keyed by `(disable_encoder,)`.

### 7.3 Session plumbing

- **SessionResolver** (`session_resolver.py`) — in-memory (not DB) scope → session_id binding with `threading.Lock`, TTL `MAX_IMPLICIT_SESSION_AGE_S=3600`. Lets `remember`/`commit` find the session `activate` opened without passing ids. One binding per scope; process restart naturally invalidates.
- **SessionReaper** (`session_reaper.py`) — daemon thread, polls every 120s, closes sessions with no events for `SLOWAVE_SESSION_IDLE_TIMEOUT=3600s` via `session_end(consolidate=False)`.
- **CompactSchema** (`compact.py`) — ~150–200 tokens/memory: id (`sch_*`, needed for reinforce), text (whitespace-collapsed, truncated — 200 chars in recall), activation (explicit cosine, or fallback `2/π·arctan(salience/2)`), reason, source_kind. Everything else dropped.

## 8. End-to-end data flows

### Ingest (fast, ~1ms, no LLM)

```
event_append → raw_events row (+FTS) (+optional embedding)
commit/session_end → IngestService.form_episodes:
    micro (window 2) + macro (session) episodes
    salience = novelty + 0.3·surprise (+0.6 if remember event)
    → episodic_memories + FAISS + episode_text
```

### Consolidation (offline worker, decoupled)

```
replay_once: decay → salience-sample 256 → fine+coarse prototype assignment (0.60)
           → coactivation/transition/similarity edges → train transition model
           → 0.5× salience penalty
consolidate: per touched prototype → LatentSchemaBuilder (SVD facets, confidence)
           → GeometricContradictionJudge vs best existing schema
           → create / reinforce / supersede symbolic schema
decay_unused: idle 30d schemas suppressed
self_supervise: probe retrieval per prototype → repair missed bridges (+0.5 / −0.25)
```

### Retrieval

```
recall(query) → encode → temporal anchor (probe) → RetrievalPipeline:
    cosine seeds (episodic + fine + coarse) → predictive seed (×0.7)
    → spreading activation (2 steps, α=0.6) → graph harvest (ceilinged)
    → rank: merged + 0.3·salience + 0.25·temporal (×1.25 dual-scale bonus)
    → diversity cap → predictive reserve slot
  + schema competition (embedding/FTS/prototype paths) + schema priors on episodes
  → WorkingMemoryGate (activate path): eligibility → activation → floors → MMR → budget
```

## 9. Key hyperparameters (defaults)

| Parameter | Value | Where |
|---|---|---|
| Embedding dim | 384 | SlowaveConfig |
| Prototype assignment threshold (fine & coarse) | 0.60 | ReplayConfig |
| Replay sample size / max new prototypes | 256 / 32 | ReplayConfig |
| Salience decay τ / floor / recall boost / consolidation penalty | 3600s / 0.01 / +0.2 / ×0.5 | SalienceConfig |
| Edge fusion λ (sim/trans/coact) | 1.0 / 0.5 / 0.3 | GraphConfig |
| Edge prune threshold | 0.05 | GraphConfig |
| Similarity / coactivation edges per node | 8 / 6 | GraphConfig |
| Spread steps / decay α / graph-episode weight / ceiling | 2 / 0.6 / 0.15 / 0.9×floor | RetrievalConfig |
| Salience / temporal ranking weights | 0.3 / 0.25 | RetrievalConfig |
| Transition score weight / reserve qsim gate | 0.7 / <0.85 | RetrievalConfig |
| Facet axes / variance floor | 4 / 1e-2 | LatentSchemaConfig |
| Judge: same-topic / reinforce / contradict thresholds | 0.75 / 0.95 / 0.35 | GeometricJudgeConfig |
| Manifold: direction / review-band / same-scope cos | 0.10 / 0.05 / 0.85 (ext 0.70, cross 0.78) | SupersessionManifold |
| Gate: min activation / max chars / MMR dedup | 0.20 / 1800 / 0.92 | WorkingMemoryGate policy |
| Feedback deltas | see §5.5 table | FeedbackConfig |
| Generalization stage gates | see §4.3 table | GeneralizationConfig |
| Schema decay idle window | 30 days | decay_unused |

## 10. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SLOWAVE_DB` | `~/.slowave/slowave.db` | DB path |
| `SLOWAVE_MCP_IDLE_TIMEOUT` | 1800 (stdio) / 0 (HTTP) | Process watchdog |
| `SLOWAVE_SESSION_IDLE_TIMEOUT` | 3600 | Session reaper |
| `SLOWAVE_DAEMON_PID` | `~/.slowave/daemon.pid` | HTTP single-instance PID file |
| `SLOWAVE_MCP_HOST` / `SLOWAVE_MCP_HTTP_PORT` | 127.0.0.1 / 8766 | HTTP bind |
| `KMP_DUPLICATE_LIB_OK=TRUE`, `OMP_NUM_THREADS=1`, `TOKENIZERS_PARALLELISM=false` | — | macOS FAISS/ONNX coexistence |

## 11. Design invariants (worth keeping front-of-mind)

1. **No LLM anywhere in the memory path** — consolidation, judgment, supersession, schema formation are all geometry. Text is an output surface.
2. **Ingest is decoupled from consolidation** — session end never blocks; the worker does everything heavy.
3. **Graph episodes never out-rank or self-reinforce** — the 0.9×floor ceiling and cosine-only recall reinforcement prevent runaway feedback loops.
4. **One fact = one embedding** — dedup at create, MMR at the gate, exact-dedup maintenance.
5. **Trajectories/edges explain, never prescribe** — memory provides context; the LLM decides. (The removal of ProceduralMemoryStore is this principle applied.)
6. **Everything is auditable** — retrieval snapshots record even the suppressed pool; worker runs are logged; evidence links go all the way down to raw events.
7. **FAISS is a cache, SQLite is the truth** — indexes rebuilt at startup, never persisted.

## 12. Known documentation drift (as of 2026-07-03)

- CLAUDE.md still documents `ProceduralMemoryStore` (`core/procedural.py`) — removed Phase 1 P1, 2026-06-25.
- CLAUDE.md says encoder is `all-MiniLM-L6-v2` — code default is `paraphrase-multilingual-MiniLM-L12-v2` via ONNX Runtime (384-d, multilingual).
- CLAUDE.md architecture section doesn't mention the `core/services/` split (ingest/retrieval/consolidation/feedback) that now carries most engine logic.
