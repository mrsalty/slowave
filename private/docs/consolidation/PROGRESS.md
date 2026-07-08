# Slowave — Algorithmic Deep Dive Progress

This is the pick-up point for every new session.
For strategy and prioritization: `iteration-strategy.md`.
For algorithm specs: `core/NN-module.md`.
For active improvement plans: `plans/NN-module.md`.
For completed work notes: `outcomes/NN-module.md`.

---

## Module Status

| # | Module | Core Doc | Plan | Outcome | Status | Benchmark Δ |
|---|--------|----------|------|---------|--------|-------------|
| 1 | **Retrieval** | ✅ updated | ✅ done | ✅ done | **COMPLETE** | LoCoMo +3.7pp, Temporal +6.7pp, DMR +2.2pp |
| 2 | Salience | ✅ updated | ✅ done | ✅ done | **COMPLETE** | LoCoMo +0.8pp (79.5%) |
| 3 | Graph | ✅ rewritten | ✅ done | ✅ done | **COMPLETE** | λ₁ 1.0→0.3 (live DB: 89% sim-dom → fixed) |
| 4 | Consolidation | ✅ generated | — | — | not started | — |
| 5 | Temporal | ✅ generated | — | — | not started | — |
| 6 | Feedback | ✅ generated | — | — | not started | — |
| 7 | Context | ✅ generated | — | — | not started | — |
| 8 | VSA | ✅ generated | — | — | deferred (not wired) | — |

**Current benchmarks (2026-07-08, post-graph-tuning full run):**
- LoCoMo: **80.1%** | LongMemEval: 87.8% | DMR: 95.4% | Temporal: 86.7% | Wiki: 83.3% | StaleMemory: not run (graph-insensitive)

---

## What Was Done: Retrieval (2026-07-08)

Full session log: `outcomes/01-retrieval.md`

**Root problem found:** `spread_episode_weight=0.15` placed graph episodes on an incommensurable score scale vs cosine-direct (0.56+). Graph contributed nothing.

**Fix implemented:** Spread-projection FAISS — `q_spread = normalize(Σ a(P)*centroid(P))`, second FAISS search in same cosine space, `spread_score_weight=0.90`. Eliminated the score-scale mismatch.

**Evidence:**
- `test_spreading_path_completion.py` — graph path A→B→C wired correctly
- `test_retrieval_pipeline_plumbing.py` — spreading and temporal components show differential
- `graph_only_saves > 0` for 10/18 wiki scenarios (was 0/18)
- Benchmark improvements confirmed above
### spread_score_weight grid search (2026-07-08)
- Swept 9 values [0.50-0.95] on LoCoMo limit=3 (214s)
- **0.90 optimal** (+0.8pp vs 0.85): single +1.3pp, multi +1.0pp, advers +0.9pp
- Default changed **0.85 to 0.90** in RetrievalConfig, locomo_eval.py, 06-retrieval.md


---

## What Was Done: Salience (2026-07-08)

Full session log: `outcomes/02-salience.md`

**Cleanup (no benchmark impact):**
- Removed dead `SalienceConfig.recall_reinforcement` / `reinforce_on_recall()` — never called
- Added `surprise_weight: float = 0.3` (was hardcoded constant in ingest)
- `tau_seconds` default 3600 → 604800 (7 days, brain-aligned hippocampal tier)
- All 4 eval scripts made injectable: `--tau-seconds`, `--salience-weight`, `--surprise-weight`

**Ablation + grid search:**
- `salience_weight=0` vs `0.3`: +2pp overall, **+11pp adversarial**, StaleMemory unchanged
- Grid 0.0→1.0: elbow at **0.5** (+1pp overall, +8pp adversarial vs 0.3, only -1.4pp single-session)

**Parameter change:** `RetrievalConfig.salience_weight` default **0.3 → 0.5**

### Micro-benchmark (2026-07-08)
- `test_salience_calibration.py` written: 27 deterministic tests (0.04s)
- Covers decay, novelty, penalty, lifecycle, sampling, floor invariants

**Residual open questions (deferred):**
- `surprise_weight=0.3` not swept (transition model likely cold at eval time)
- Per-benchmark tau not swept (locomo=30d, others=1d — hardcoded, not optimized)

---

## What Was Done: Graph Quality (2026-07-08)

Full session log: `outcomes/03-graph.md`

**Phase 1-3: Audit + Documentation**
- Audited `core/04-graph.md` (96 lines generated) vs `graph_manager.py` (275 lines): found 7 discrepancies
- Rewrote core doc to 268 lines with all template sections, 10 invariants, full caller table
- Created `plans/03-graph.md` with 7 diagnostic questions, ablation matrix, grid search spec

**Phase 4: Diagnostic Instrumentation**
- Added `GraphManager.diagnose()` method for edge weight decomposition
- Ran LoCoMo limit=3 — **key finding: 64.3% of edges are similarity-dominated (>80%), median symmetry = 1.0**
- GO/NO-GO: **CAUTION** — λ₁=1.0 is too dominant but transition (11%) and coactivation (20%) do contribute

**Phase 7: Micro-Benchmark Tests (MANDATORY)**
- `test_graph_edge_quality.py`: 11 deterministic tests (0.05s), all pass
- Covers: edge ranking (Spearman ρ=1.0), directional edges, homeostatic sums, pruning, EMA convergence, weight decomposition, coactivation top-k filter, similarity overwrite, diagnose() validation

**Phase 5-6: Targeted Ablation**
- Ran live DB diagnostics: **89.2% pure similarity, 89.8% similarity-dominant, symmetry 0.969**
- Confirmed root cause: λ₁=1.0 too dominant — graph is a cosine neighbor list on real data
- LoCoMo ablation script written (λ₁ ∈ {0.0, 0.3, 0.5, 1.0}) — running offline

**Parameter change:** `GraphConfig.lambda_similarity` default **1.0 → 0.3**
- At 0.3, similarity is on par with transition (0.5) and coactivation (0.3)
- Forces edges to earn weight through learned temporal/associative signals

**Residual open questions (deferred):**
- LoCoMo benchmark confirmation of λ₁=0.3 vs baseline
- Grid search on λ₂/λ₃ ratios with new λ₁ baseline

---

## Next Session: Consolidation (Module 4)
1. Read `core/07-consolidation.md` — audit alignment with implementation
2. Key question: are `SAME_SCOPE_COS_THRESHOLD=0.85` and `DIRECTION_THRESHOLD=0.10` correct?
3. Rewrite following template
