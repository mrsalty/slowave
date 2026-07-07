# 11 — Vector Symbolic Architecture (VSA)

**Status: Experimental / internal use only.** VSA vectors are stored in schema facets but not currently used in retrieval ranking or consolidation decisions.

## Overview

VSA provides a lightweight, deterministic algebraic implementation of **hippocampal role binding** using Holographic Reduced Representations (HRRs). Three fixed role vectors (subject, predicate, object) are bound to content vectors via circular convolution, producing a single superposition vector that encodes the triple.

## Core Operations

### Circular Convolution (bind)

For vectors \( \mathbf{a}, \mathbf{b} \in \mathbb{R}^d \):

\[
(\mathbf{a} \circledast \mathbf{b})_k = \sum_{i=0}^{d-1} a_i \cdot b_{(k-i) \bmod d}
\]

Implemented efficiently via FFT:

\[
\mathbf{a} \circledast \mathbf{b} = \mathcal{F}^{-1}(\mathcal{F}(\mathbf{a}) \odot \mathcal{F}(\mathbf{b}))
\]

Properties:
- Nearly orthogonal to both \( \mathbf{a} \) and \( \mathbf{b} \)
- Reversible: given \( \mathbf{a} \circledast \mathbf{b} \) and \( \mathbf{a} \), you can recover \( \mathbf{b} \)

### Circular Correlation (unbind)

Approximate inverse of bind:

\[
(\mathbf{a} \mathbin{\#} \mathbf{c})_k = \sum_{i=0}^{d-1} a_i \cdot c_{(i+k) \bmod d}
\]

Recovers \( \mathbf{b} \approx \mathbf{a} \mathbin{\#} (\mathbf{a} \circledast \mathbf{b}) \).

### Bundle (superposition)

Element-wise sum + L2 normalization:

\[
\text{bundle}(\mathbf{v}_1, \ldots, \mathbf{v}_n) = \frac{\sum_i \mathbf{v}_i}{\|\sum_i \mathbf{v}_i\|_2}
\]

### Encode Triple

\[
\mathbf{v}_{\text{triple}} = \text{bundle}(\mathbf{r}_S \circledast \mathbf{f}_S, \; \mathbf{r}_P \circledast \mathbf{f}_P, \; \mathbf{r}_O \circledast \mathbf{f}_O)
\]

Where:
- \( \mathbf{r}_S, \mathbf{r}_P, \mathbf{r}_O \) = fixed role vectors (subject, predicate, object)
- \( \mathbf{f}_S, \mathbf{f}_P, \mathbf{f}_O \) = filler vectors (content bound to each role)

### Query Role

Recover the approximate filler for a role from a VSA vector:

\[
\text{query\_role}(\mathbf{r}, \mathbf{v}_{\text{triple}}) = \mathbf{r} \mathbin{\#} \mathbf{v}_{\text{triple}}
\]

## Role Vectors

Three fixed vectors generated from a seeded RNG (`seed = 0x516C6176` = ASCII "Slav"):

\[
\mathbf{r}_S, \mathbf{r}_P, \mathbf{r}_O \sim \mathcal{N}(0, 1)^d, \quad \text{then L2-normalized}
\]

Properties:
- Deterministic — same on every machine, forever
- Nearly orthogonal to each other and to any real content vector
- Stored as module-level constants — zero runtime cost after import

## Modes

### Geometric Mode (default)

Roles derived from prototype geometry:
- **Subject** = prototype centroid
- **Predicate** = dominant PCA axis (`facet_axes[0]`)
- **Object** = secondary PCA axis (`facet_axes[1]`)

### Lexical Mode

Roles extracted from schema text via regex verb detector + lexical signature:
- **Subject** = first capitalised token or top lexical term
- **Predicate** = first verb-pattern match
- **Object** = remaining top lexical terms

## Storage

VSA vectors are stored in `schemas.facets_json` under the key `"vsa_vec"` as base64-encoded float32 blobs. No schema change required — fully backwards compatible.

## Key Invariants

1. VSA is **not** currently connected to retrieval ranking — it is stored but unused.
2. The seed constant (`0x516C6176`) must never change after shipping — it would invalidate all stored VSA vectors.
3. Role vectors are dimension-dependent — generated per dimension via `get_role_vectors(dim)`.
4. Both modes (geometric and lexical) are deterministic and require no model training.
5. VSA provides a future path for structured querying (e.g., "who changed the budget?") without LLM calls.