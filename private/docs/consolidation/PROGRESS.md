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
| 3 | Graph | ✅ generated | — | — | not started | — |
| 4 | Consolidation | ✅ generated | — | — | not started | — |
| 5 | Temporal | ✅ generated | — | — | not started | — |
| 6 | Feedback | ✅ generated | — | — | not started | — |
| 7 | Context | ✅ generated | — | — | not started | — |
| 8 | VSA | ✅ generated | — | — | deferred (not wired) | — |

**Current benchmarks (2026-07-08, post-salience-tuning full run):**
- LoCoMo: 79.7% | LongMemEval: 87.8% | DMR: 95.8% | Temporal: 86.7% | StaleMemory: 45.2% | Wiki: 83.3%

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

## Next Session: Pick Up at Graph (Module 3)

**Starting point:**
1. Read `core/04-graph.md` — audit alignment with implementation
2. Rewrite following template (same process as retrieval + salience)
3. Key diagnostic question: are edge weights reflecting actual semantic/temporal relationships, or is similarity dominating everything?
4. Ablation: `use_spreading=True` vs `False` on full LoCoMo (retrieval plan had this but on wiki only)
