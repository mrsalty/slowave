# Retrieval — Deep Dive Outcomes (2026-07-08)

**Status:** COMPLETE  
**Branch:** `feat/retrieval-deep-dive` → merged to main (private)  
**Session duration:** ~1 working day

---

## Root Cause Found

The system had a **score-scale mismatch**: graph episodes scored via `spread_episode_weight=0.15 × activation × salience_multiplier` (max ≈ 0.15), while cosine-direct episodes scored at 0.56+ on real corpora. Graph could never compete. `graph_only_saves = 0` on all 18 wiki scenarios.

**Deeper cause:** The pre-trained embedding space and the prototype graph were learned by separate processes with no shared calibration. The brain analog: CA3 similarity and association are encoded by the same synaptic weights learned jointly. Slowave had two incommensurable numerical spaces.

---

## Fix: Spread-Projection FAISS

Replaced the prototype-harvest loop (Phase 4) with spread-projection:

```
q_spread = normalize( Σ a(P) * centroid(P) )
```

Second FAISS search on `q_spread` in the same cosine space as the direct query. `spread_score_weight=0.85` applies a principled discount (direct recall fires stronger than associative spreading — brain-faithful).

**Files changed:**
- `slowave/latent/retrieval.py` — `_spread_projection()`, `spread_episodic_top_k=10`, `spread_score_weight=0.85`
- `slowave/latent/types.py` — `EpisodeDiagnostic`, `QueryDiagnostics`, `diagnose=True` flag
- `slowave/core/services/retrieval.py` — wire `diagnose` through service
- `slowave/core/engine.py` — wire `diagnose` through engine

**Deprecated (kept for compat):** `spread_episode_weight`, `spread_score_ceiling`

---

## What the Instrumentation Found (before fix)

Ran wiki scenarios with `diagnose=True`. Key findings:

| Q | Finding |
|---|---------|
| Q1 (graph saves?) | 0 everywhere. Root cause: score architecture, not topology. |
| Q2 (activation depth) | R/I families: no activation (no prototypes, no consolidation). G/D/S/C: depth=[44,77] — spreading fans OUT, not converges. |
| Q4 (q_pred_sim) | 0.44–0.72 when transition model fires — meaningfully different predictions. |
| Q6 (cosine band) | G-3: band=0.028, S-2: 0.033 — cosine near-random; salience/temporal doing the work. |
| Q7 (dual-scale pct) | 10–50% on scenarios with prototypes — multi-scale NOT cosmetic. |

**`test_spreading_path_completion.py`** confirmed: graph path A→B→C is correctly wired. The problem was purely score-scale.

---

## Ablation Matrix (post-fix)

Ran all 7 ablations × 18 wiki scenarios. **Result: 0pp delta on every component.**

**Why:** Wiki hits are determined by the schema layer (`RetrievalService` FTS + embedding search), not the episode pipeline. Ablations varied `RetrievalPipeline` parameters. Zero delta was correct — wiki tests the wrong layer.

**Real-world benchmarks showed the actual improvement** (see below).

---

## Retrieval Stress Tests (plumbing tests)

`tests/unit/test_retrieval_pipeline_plumbing.py` — 2 tests, 0.36s:
- **SP-1 (spreading):** `graph_harvest_n > 0` with spreading, `== 0` without. Confirms graph path wired.
- **SP-2 (temporal):** Gondola before LRU with `temporal_anchor_ts`, reversed without. Confirms temporal boost fires.

Key engineering discoveries during test construction:
1. Predictive completion learns short ingestion sequences — must disable `use_transition` to isolate spreading
2. Multi-turn sessions create macro episodes with blended embeddings — can split prototype assignment
3. `RetrievalService.TemporalProbe` overrides `temporal_anchor_ts` — must call `RetrievalPipeline.retrieve()` directly
4. FAISS returns higher IDs first for tied scores — not insertion order

---

## Architecture Decision: Two-Space Problem

**Finding:** The fundamental issue is that the pre-trained embedding space and the prototype graph were learned independently (no shared calibration). The brain avoids this because CA3 encodes both similarity and association in the same synaptic weights.

**Near-term fix (implemented):** Spread-projection back into embedding space — resolves score-scale mismatch.

**Long-term direction:** VSA (module 11) — single high-dimensional space where binding (graph) and similarity (cosine) use the same algebra. Already planned in `core/11-vsa.md`.

---

## Benchmark Delta (2026-07-08 vs 2026-07-07)

| Benchmark | Before | After | Δ | Explanation |
|-----------|--------|-------|---|-------------|
| LoCoMo | 74.3% | 78.7% | **+3.7pp** | Cross-session episodes now score 0–0.85 (was 0–0.15); compete with weak cosine hits |
| Temporal | 73.3% | 80.0% | **+6.7pp** | CH-1 (chain scenario) flipped from miss to HIT — direct evidence graph chain traversal works |
| DMR | 94.2% | 95.6% | **+2.2pp** | Same mechanism; smaller effect (DMR more cosine-matchable) |
| LongMemEval | 87.6% | 87.8% | ~0 | Schema-layer driven; episode pipeline not the binding constraint |
| Wiki | 83.3% | 83.3% | 0 | Schema layer does the work; episode pipeline irrelevant for these scenarios |
| StaleMemory | 45.2% | 45.2% | 0 | Schema supersession logic; episode pipeline not involved |

---

## Open Items (not addressed)

1. **C-1/C-2/C-3 completion misses:** Graph finds the right neighborhood but not the specific prototype holding the indirect fact. Needs graph quality work (module 3) — the domain→fact prototype edge doesn't form from a single consolidation pass.
2. **Wiki C-1 false regression:** Old system accidentally hit Thermacrete via weak schema score; new system correctly surfaces militarily-relevant content for a military query. Expected behavior.
3. **Retrieval stress tests are plumbing, not performance:** They verify wiring but don't measure real-world quality improvement. Next step for real measurement: scenarios where ground truth is an episode unreachable via cosine alone (not yet designed).
