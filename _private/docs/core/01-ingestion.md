# 01 — Ingestion & Episodic Encoding

## Overview

The ingestion pipeline converts raw text into an episodic memory trace: a dense vector embedding stored in FAISS + SQLite, with an initial salience derived from its novelty relative to existing memories.

## Mathematical Formulation

### Step 1: Text Encoding

Given a text string \( t \in \Sigma^* \):

\[
\mathbf{e} = \text{encode}(t) \in \mathbb{R}^{d}, \quad d = 384
\]

Where `encode` is the ONNX Runtime inference of `paraphrase-multilingual-MiniLM-L12-v2`, producing an L2-normalized vector:

\[
\|\mathbf{e}\|_2 = 1
\]

### Step 2: Salience Initialization (Novelty)

For a new episode with embedding \(\mathbf{e}\), find its nearest neighbor in the episodic store:

\[
\text{nn\_sim} = \max_{i \in \mathcal{E}} \cos(\mathbf{e}, \mathbf{e}_i) = \max_{i \in \mathcal{E}} \langle \mathbf{e}, \mathbf{e}_i \rangle
\]

The initial salience is the complement of similarity (more novel → higher salience):

\[
s_0 = \max(s_{\min}, \;\; w_{\text{novelty}} \cdot \frac{1 - \text{nn\_sim}}{2})
\]

Where:
- \( s_{\min} = \text{min\_salience} \) (default: `0.01`)
- \( w_{\text{novelty}} = \text{novelty\_weight} \) (default: `1.0`)

### Step 3: Storage

The episodic memory \( m \) is stored as:

\[
m = (\text{id}, \text{event\_id}, \text{ts}, \mathbf{e}, s_0, \text{metadata})
\]

- **FAISS Index**: `IndexIDMap2(IndexFlatIP(d))` — inner product on normalized vectors = cosine similarity.
- **SQLite**: Row in `episodic_memories` table with salience, timestamp, metadata_json.

## Configuration

### `EpisodicStoreConfig`
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dim` | `int` | `384` | Embedding dimension |
| `db_path` | `str` | `"slowwave.db"` | SQLite database path |
| `faiss_index_path` | `str` | `"episodic.faiss"` | FAISS index persistence path |

### `SalienceConfig` (initialization)
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `novelty_weight` | `float` | `1.0` | Weight for novelty component |
| `min_salience` | `float` | `0.01` | Floor for salience values |

### `EncoderConfig`
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | `str` | `"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"` | HuggingFace model |
| `normalize` | `bool` | `True` | L2-normalize output embeddings |
| `device` | `str` | `"cpu"` | Compute device (CPU only for ONNX) |
| `use_onnx` | `bool` | `True` | Use ONNX Runtime (no torch dependency) |
| `cache_dir` | `str | None` | `None` | Custom model cache directory |

## Key Invariants

1. All embeddings are L2-normalized; cosine similarity reduces to dot product.
2. `min_salience` ensures no trace decays to exactly zero.
3. `novelty_weight = 1.0` means a perfectly novel episode (nn_sim = -1) gets salience = 1.0; an identical duplicate (nn_sim = 1) gets salience = min_salience.
4. FAISS `IndexFlatIP` + `IndexIDMap2` means exact search, not approximate — full precision at the cost of linear scan.