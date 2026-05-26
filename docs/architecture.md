# Architecture

## Overview

```
raw_events  →  episodes (on session_end, <1ms, no LLM)
                  ↓ background worker
                  ↓ cluster into prototypes (fine 0.85 + coarse 0.55)
                  ↓ build latent schema (centroid + SVD axes + temporal anchor)
                  ↓ geometric contradiction detection
              prototype graph + latent schemas
                  ↓
              recall: cosine + predictive seed + spreading activation + multi-scale
```

**Episodes** form immediately on session close — sub-millisecond, no LLM.  
**Prototypes** cluster episodes offline at two scales: fine (CA3-like, exact) and coarse (CA1-like, generalising).  
**Latent schemas** are a deterministic geometric fingerprint of a prototype: centroid + SVD principal axes + temporal anchor. No LLM extraction.  
**Recall** is always LLM-free: FAISS at both scales + predictive transition seed + spreading activation over the prototype graph + salience rerank.

---

## 1. Design Philosophy

Slowave is built on the observation that existing open-source agent memory systems (Mem0, Letta, Zep, A-MEM) update memory **on write only**: ingest a fact, deduplicate, store. Slowave additionally models the key operations of biological memory:

| Biological principle | Slowave implementation |
|---|---|
| Episodic encoding at experience time | Raw events → micro/macro episodes on session close |
| Slow-wave sleep consolidation | Replay engine runs offline (background worker) |
| Semantic abstraction over episodes | Two-scale prototype clustering: fine (CA3, 0.85) + coarse (CA1, 0.55) |
| Schema formation (neocortex) | **Latent schema** (Stage 6): centroid + SVD facet axes + temporal anchor — no LLM |
| Predictive coding / surprise signal | Transition model predicts next episode embedding; surprise boosts salience |
| Ebbinghaus forgetting curve | Exponential salience decay between sessions |
| Memory reinforcement on use | Recall bumps salience of retrieved episodes/schemas |
| Contradiction / belief revision | Geometric contradiction: centroid proximity + facet divergence + temporal ordering — no LLM |
| Pattern completion | Spreading activation over prototype graph (Stage 1) |
| Provenance chain | Every schema traces back through episodes to raw events |

**Default path (Stage 6+) uses zero LLM calls.** The LLM extraction path (Stage 0-5) is preserved for comparison runs only.

The system is designed to generalise across agent types and benchmarks, not to overfit to any single evaluation.

---

## 2. High-Level Architecture

```mermaid
flowchart TD
    A[Agent / Cline / MCP] --> B[session_start]
    B --> C[event_append\nraw_events + embedding]
    C --> D[session_end]
    D --> E[Micro episodes\nsliding window=2]
    D --> F[Macro episode\nfull session]
    E --> G[episodic_memories\nepisode_text\nsalience]
    F --> G
    G --> H[ReplayEngine\nsalience sampling]
    H --> I[Prototype clustering\nonline k-means]
    H --> K[TransitionModel\ne_t to e_t+1]
    I --> J[Prototype graph\nsimilarity + coactivation\n+ transitions]
    I --> L[Consolidator]
    L --> M[SchemaExtractor\nLLM prompt]
    M --> N[ContradictionJudge\nLLM prompt]
    N --> O[SchemaStore\ndurable typed claims]
    P[recall query] --> Q[TextEncoder]
    Q --> R[RetrievalPipeline]
    R --> S[FAISS episodic\nsalience rerank]
    R --> T[FAISS prototype\ngraph expansion]
    R --> U[Schema embedding\nFTS5 lexical]
    S --> V[RecallResult\nschemas + episodes\nraw events]
    T --> V
    U --> V
    O --> U
    G --> S
    J --> T
```

---

## 3. Memory Layers

Slowave has two distinct memory layers mirroring Complementary Learning Systems (CLS) theory.

```mermaid
flowchart LR
    subgraph Latent["Latent Layer (hippocampus-like)"]
        direction TB
        E1[episodic_memories\nembedding + salience]
        E2[semantic_prototypes\ncentroid + variance]
        E3[prototype_edges\nsimilarity / transition\n/ coactivation]
        E1 -->|replay assigns| E2
        E2 -->|graph update| E3
    end

    subgraph Symbolic["Symbolic Layer (neocortex-like)"]
        direction TB
        S1[raw_events\ncanonical log]
        S2[episode_text\ntext + provenance]
        S3[schemas\ntyped claims\n+ facets + embedding]
        S4[schema_evidence\nepisode/event/quote]
        S5[schema_relations\nreinforces/refines\n/contradicts/supersedes]
        S1 -->|session close| S2
        S2 -->|consolidation| S3
        S3 --- S4
        S3 --- S5
    end

    E1 -.->|episode_prototype_map| E2
    E2 -.->|schema_prototype_map| S3
    S2 -.->|episode_ids| E1
```

### Latent layer components

| Component | Role |
|---|---|
| `EpisodicStore` | Stores per-episode float32 embeddings as SQLite BLOBs; rebuilt into FAISS for ANN search |
| `SemanticStore` | Stores prototype centroids updated by online incremental mean during replay |
| `GraphManager` | Sparse directed graph over prototypes; edges carry similarity, transition probability, coactivation |
| `TransitionModel` | Small linear layer trained on consecutive episode pairs; provides prediction error / surprise signal |
| `SalienceEngine` | Novelty, exponential decay, recall reinforcement, consolidation penalty |
| `ReplayEngine` | Orchestrates all latent-layer operations on session close |

### Symbolic layer components

| Component | Role |
|---|---|
| `RawLog` | Append-only event log; source of truth for all provenance |
| `EpisodeTextStore` | Text representation of each episodic memory + source event IDs |
| `SchemaStore` | Durable typed claims with flexible facets, canonical embedding, salience, status, evidence |
| `LatentSchemaBuilder` | **Default** — centroid + SVD principal axes + temporal anchor + confidence, no LLM |
| `GeometricContradictionJudge` | **Default** — centroid proximity + facet divergence + temporal ordering, no LLM |
| `SchemaExtractor` | Legacy (Stage 0-5, `--schema-mode llm`) — LLM call → `ExtractedSchema` objects |
| `ContradictionJudge` | Legacy (Stage 0-5) — LLM call → reinforces / refines / contradicts verdict |
| `Consolidator` | Orchestrates schema building (latent or LLM path) → SchemaStore |

---

## 4. Data Flow: Ingest

```mermaid
sequenceDiagram
    participant Agent
    participant Engine
    participant RawLog
    participant Encoder
    participant EpisodicStore
    participant ReplayEngine
    participant Consolidator
    participant LLM

    Agent->>Engine: session_start(agent, project)
    loop per turn
        Agent->>Engine: event_append(type, content)
        Engine->>Encoder: encode(content)
        Engine->>RawLog: append(event + embedding)
    end
    Agent->>Engine: session_end(consolidate=True)
    Engine->>Engine: form_episodes (micro + macro)
    Engine->>EpisodicStore: add(embedding, salience)
    Engine->>ReplayEngine: replay_once()
    Engine->>Consolidator: consolidate(prototype_ids)
    Consolidator->>LLM: extract_schema(episode_texts)
    LLM-->>Consolidator: claims with facets, tags, evidence_quote
    Consolidator->>LLM: judge(existing, new) if related schema exists
    LLM-->>Consolidator: verdict
    Consolidator->>Engine: SchemaStore.create
```

---

## 5. Data Flow: Recall

```mermaid
sequenceDiagram
    participant Agent
    participant Engine
    participant Encoder
    participant RetrievalPipeline
    participant SchemaStore

    Agent->>Engine: recall(query, top_k)
    Engine->>Encoder: encode(query)
    Engine->>RetrievalPipeline: retrieve(query_embedding)
    RetrievalPipeline-->>Engine: episodic + prototypes + neighbors
    Engine->>SchemaStore: search_embedding(query, wide limit)
    Engine->>SchemaStore: search_fts(query)
    Engine->>SchemaStore: get_many_by_prototypes(proto_ids)
    Engine->>Engine: merge scores + top_k cut
    Engine->>SchemaStore: reinforce recalled schemas (+0.05)
    Engine-->>Agent: RecallResult(schemas, episode_texts, raw_events)
```

---

## 6. Episode Formation

On `session_end`, raw events are converted to episodic memories using a multi-scale strategy:

```mermaid
flowchart LR
    subgraph Session[Session events]
        e0 --- e1 --- e2 --- e3 --- e4
    end

    subgraph Micro[Micro episodes window=2]
        m0[e0+e1]
        m1[e1+e2]
        m2[e2+e3]
        m3[e3+e4]
    end

    subgraph Macro[Macro episode full session]
        mac[e0..e4]
    end

    Session --> Micro
    Session --> Macro
```

- **Micro episodes** preserve local context (individual user preferences, facts, decisions).
- **Macro episode** preserves global session context; downweighted salience (`×0.8`).
- **Salience** = novelty (distance to nearest existing episode) + 0.3 × prediction surprise.
- `remember:` events receive a salience bonus (`+0.6`) so explicit memories survive replay.

---

## 7. Schema Structure

A schema is a durable typed claim about the user or project, consolidated from episodic evidence.

```
Schema {
  content_text             str     ← human-readable claim
  facets {
    schema_class           str     ← fact | preference | habit | decision | constraint | ...
    scope                  str     ← domain/context
    polarity               str     ← positive | negative | neutral | mixed
    stability              str     ← one_off | recurring | current | historical
    positive               [str]   ← what to prioritise in future responses
    negative               [str]   ← what to avoid
    entities               [str]   ← salient named entities
    attributes             {str}   ← structured slots
  }
  tags                     [str]   ← compact search tags
  confidence               float   ← extractor confidence [0, 1]
  salience                 float   ← decays, reinforced on recall
  status                   str     ← active | needs_review | superseded | contradicted | archived
  embedding                blob    ← canonical schema text embedding (claim + facets + tags)
  schema_evidence          [...]   ← {episode_id, raw_event_id, quote, weight}
  schema_relations         [...]   ← {src, dst, relation, confidence, reason}
}
```

### Schema relations

```mermaid
flowchart LR
    A[new schema] -->|reinforces| B[existing schema]
    A -->|refines| C[existing schema]
    A -->|contradicts| D[existing schema]
    A -->|supersedes| E[existing schema]
    A -->|related_to| F[existing schema]
```

### Canonical schema embedding

Schemas are embedded using **canonical schema text** — claim + facets + tags — so the embedding captures structured memory content, not only surface wording:

```
Claim: For running training advice, the user prefers plans adapted to their knee injury.
Class: preference
Scope: running training advice
Positive: knee-adapted plans, gradual mileage increases
Negative: generic high-mileage programmes
Entities: knee injury
Tags: running, training, injury, adaptation
```

---

## 8. Salience Dynamics

```mermaid
flowchart TD
    N[New episode] -->|novelty based on distance to NN| S[Initial salience]
    S -->|plus prediction surprise weight| S2[Adjusted salience]
    S2 -->|time passes| D[Exponential decay
tau = 3600s default]
    D -->|recalled| R[+0.2 reinforcement]
    D -->|consolidated| P[x0.5 penalty]
    R --> D
    P --> D
    D -->|below min| F[Floor at 0.01]
```

Salience governs replay sampling (proportional), retrieval reranking (`cosine + 0.3×salience`), and schema persistence (superseded schemas drop to `0.05`).

---

## 9. Consolidation Pipeline

**Default: brain-only (Stage 6+), zero LLM calls.**

```mermaid
flowchart TD
    R[ReplayEngine sample] --> P[Prototype clustering\nfine 0.85 + coarse 0.55]
    P --> G[Graph update\nsimilarity + coactivation edges]
    P --> T[Transition model train\ne_t → e_t+1]
    P --> C[LatentSchemaBuilder: each prototype]
    C --> LS[centroid + SVD principal axes\n+ temporal anchor + confidence]
    LS --> GEO[GeometricContradictionJudge\ncentroid proximity + facet divergence\n+ temporal ordering]
    GEO --> SS[SchemaStore]
```

**Legacy: LLM-extraction path (Stage 0-5, `--schema-mode llm`):**

```mermaid
flowchart TD
    P[Prototype clustering] --> C[Consolidator: each prototype]
    C --> ET[Collect up to 8 episode texts]
    ET --> EX[SchemaExtractor LLM]
    EX -->|claims| EMB[Embed canonical schema text]
    EMB --> REL{Related schema?}
    REL -->|no| CR[Create schema]
    REL -->|yes| JDG[ContradictionJudge LLM]
    JDG --> SS[SchemaStore]
```

---

## 10. Storage Layout

All data lives in a single **SQLite** file (WAL mode). Embeddings are stored as `BLOB` columns and loaded into **in-memory FAISS** indices on engine start.

```
slowave.db
├── latent layer
│   ├── episodic_memories        embedding + salience + metadata
│   ├── semantic_prototypes      centroid + variance + support_count
│   ├── episode_prototype_map    M:1 episode → prototype
│   └── prototype_edges          similarity / coactivation / transition weights
├── symbolic layer
│   ├── sessions
│   ├── raw_events               canonical event log + optional embedding
│   ├── episode_text             text + event provenance
│   ├── schemas                  claims + facets + canonical embedding + status
│   ├── schema_evidence          episode/event/quote links
│   ├── schema_prototype_map     M:M schema ↔ prototype
│   ├── schema_relations         schema graph edges
│   └── consolidation_debug      LLM prompt/response audit trail
└── FTS5 indices
    ├── schemas_fts
    ├── episodes_fts
    └── raw_events_fts
```

---

## 11. Integrations

```mermaid
flowchart LR
    subgraph Consumers
        CLI[slowave CLI]
        MCP[slowave-mcp\nMCP server]
        PY[Python API]
    end
    ENGINE[SlowaveEngine]
    DB[(SQLite)]
    FAISS[In-memory FAISS]
    OLLAMA[Ollama LLM]
    ENCODER[all-MiniLM-L6-v2]
    CLI --> ENGINE
    MCP --> ENGINE
    PY --> ENGINE
    ENGINE --> DB
    ENGINE --> FAISS
    ENGINE --> OLLAMA
    ENGINE --> ENCODER
```

MCP tools: `slowave_session_start`, `slowave_event`, `slowave_session_end`, `slowave_recall`, `slowave_remember`, `slowave_context`, `slowave_stats`, `slowave_consolidate`.

---

## 12. Key Configuration

```python
SlowaveConfig(
    db_path               = "~/.slowave/slowave.db",
    dim                   = 384,
    schema_mode           = "latent",   # brain-only default; "llm" for legacy path
    encoder               = EncoderConfig(model="all-MiniLM-L6-v2"),
    salience              = SalienceConfig(
        tau_seconds             = 3600.0,
        recall_reinforcement    = 0.2,
        consolidation_penalty   = 0.5,
    ),
    replay                = ReplayConfig(
        sample_size             = 256,
        max_prototypes_per_replay = 32,
        assignment_threshold    = 0.65,  # fine scale; coarse fixed at 0.55
    ),
    # LLM config only used when schema_mode = "llm":
    llm                   = LLMBackendConfig(model="qwen2.5:7b-instruct"),
)
```

---

## 13. Module Map

```
slowave/
├── core/
│   ├── config.py           SlowaveConfig
│   ├── engine.py           SlowaveEngine (public façade)
│   └── consolidation.py    Consolidator
├── latent/
│   ├── episodic_store.py
│   ├── semantic_store.py
│   ├── graph_manager.py
│   ├── replay_engine.py
│   ├── retrieval.py
│   ├── salience.py
│   ├── transition_model.py
│   └── types.py
├── symbolic/
│   ├── raw_log.py
│   ├── episode_text.py
│   ├── schema_store.py       SchemaStore + canonical_schema_text()
│   ├── schema_extractor.py   SchemaExtractor → ExtractedSchema
│   ├── contradiction.py      ContradictionJudge
│   └── encoder.py
├── llm/
│   ├── base.py
│   ├── ollama_backend.py
│   └── prompts/
│       ├── extract_schema.txt
│       └── judge_contradiction.txt
├── storage/
│   ├── sqlite_db.py
│   └── schema.sql
├── cli/main.py
└── mcp/server.py
```

---

## 14. Biological Analogies

| Slowave component | Biological analogue |
|---|---|
| `raw_events` | Sensory input / working memory |
| `episodic_memories` | Hippocampal episodic traces |
| `semantic_prototypes` | Cortical category representations |
| `prototype_edges` | Associative cortical connectivity |
| `transition_model` | Predictive coding / sequence learning |
| Replay engine | Slow-wave sleep / hippocampal sharp-wave ripples |
| `schemas` | Neocortical long-term semantic knowledge |
| Salience decay | Forgetting curve (Ebbinghaus) |
| Recall reinforcement | Memory reconsolidation / use-dependent strengthening |
| Contradiction judge | Belief revision / predictive error correction |
| Evidence provenance | Episodic trace back to sensory context |
