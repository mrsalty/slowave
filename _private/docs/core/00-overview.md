# Slowave Core Algorithm — Overview

## Architecture

Slowave is a **dual-layer memory system** for AI agents. It combines:

1. **Latent Layer** (SlowWave substrate): Continuous vector embeddings processed via FAISS, prototype clustering, graph propagation, and temporal encoding. Brain-inspired: hippocampus analogue.

2. **Symbolic Layer** (Slowave additions): Discrete text schemas, FTS indexes, raw event logs, sessions. Brain-inspired: cortical consolidation analogue.

```
                  ┌──────────────────────────┐
                  │      remember(content)    │  ← Agent writes
                  └──────────┬───────────────┘
                             ▼
  ┌──────────────────────────────────────────────────┐
  │  INGESTION                                        │
  │  text → encode() → episodic memory (FAISS+SQLite) │
  │  salience = compute_novelty(nn_similarity)        │
  └──────────────────┬───────────────────────────────┘
                     ▼
  ┌──────────────────────────────────────────────────┐
  │  REPLAY (periodic / session-end)                  │
  │  sample episodes → assign to prototypes           │
  │  update graph edges (similarity + transition)     │
  │  self-supervised rehearsal                        │
  └──────────────────┬───────────────────────────────┘
                     ▼
  ┌──────────────────────────────────────────────────┐
  │  CONSOLIDATION                                    │
  │  prototypes → latent schemas → SQL schemas        │
  │  supersession detection / contradiction           │
  └──────────────────┬───────────────────────────────┘
                     ▼
  ┌──────────────────────────────────────────────────┐
  │  RETRIEVAL                                        │
  │  query → FAISS cosine + spreading activation      │
  │  → temporal boost → salience re-rank → top-k      │
  └──────────────────┬───────────────────────────────┘
                     ▼
  ┌──────────────────────────────────────────────────┐
  │  CONTEXT GATING                                   │
  │  schemas → keyword scoring → activation ranking   │
  │  → MMR dedup → budget trim → rendered text        │
  └──────────────────┬───────────────────────────────┘
                     ▼
  ┌──────────────────────────────────────────────────┐
  │  FEEDBACK LOOP                                    │
  │  user feedback → FeedbackSignal → schema updates  │
  │  salience_delta, confidence_delta, review flags   │
  └──────────────────────────────────────────────────┘
```

## Data Model

### Core Types

| Type | Description | Key Fields |
|------|-------------|------------|
| `Event` | Raw input envelope | event_id, timestamp, type, embedding |
| `EpisodicMemory` | Stored vector trace | id, embedding, salience, recalled_count |
| `SemanticPrototype` | Cluster centroid | id, centroid, support_count, variance, scale |
| `Schema` | Symbolic memory record | id, content_text, embedding, facets, status |
| `RetrievedMemorySet` | Recall result | query_embedding, episodic, prototypes, neighbors |

### Scales (Stage 9)

Two hippocampal subfield analogues:
- **`fine`** (CA3): High assignment threshold — pattern completion. Distinct but related facts stay separate.
- **`coarse`** (CA1): Low assignment threshold — pattern generalization. Similar episodes merge into broader concepts.

## Global Constants (Dimension)

| Constant | Value | Description |
|----------|-------|-------------|
| Default `dim` | `384` | Embedding dimension (paraphrase-multilingual-MiniLM-L12-v2) |
| Default model | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | ONNX Runtime backend |

## Files Structure

| File | Module | Purpose |
|------|--------|---------|
| `slowave/core/engine.py` | `SlowaveEngine` | Top-level facade: remember, recall, consolidate |
| `slowave/core/config.py` | `SlowaveConfig` | Root configuration dataclass |
| `slowave/latent/episodic_store.py` | `EpisodicStore` | FAISS-backed episodic memory |
| `slowave/latent/semantic_store.py` | `SemanticStore` | FAISS-backed prototype store |
| `slowave/latent/salience.py` | `SalienceEngine` | Novelty, decay, reinforcement |
| `slowave/latent/replay_engine.py` | `ReplayEngine` | Prototype assignment + graph building |
| `slowave/latent/graph_manager.py` | `GraphManager` | Weighted directed prototype edges |
| `slowave/latent/retrieval.py` | `RetrievalPipeline` | Cosine + spreading activation |
| `slowave/latent/temporal.py` | `TemporalProbe` | Multi-scale sinusoidal temporal encoding |
| `slowave/latent/transition_model.py` | `TransitionModel` | Graph-based successor prediction |
| `slowave/latent/vsa.py` | VSA bind/unbind | HRR-based role binding (experimental) |
| `slowave/core/consolidation.py` | `Consolidator` | Prototype → schema conversion |
| `slowave/core/context.py` | `WorkingMemoryGate` | Keyword-based activation gating |
| `slowave/core/feedback.py` | Feedback system | Learning signal computation |
| `slowave/core/supersession_manifold.py` | `SupersessionManifold` | SVD1 direction for update detection |