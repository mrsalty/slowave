# Salience — Outcome Notes (2026-07-08)

## What Was Done

### Cleanup (no benchmark impact)
- Removed dead `SalienceConfig.recall_reinforcement` field and `reinforce_on_recall()` method — never called; reinforcement runs via `RetrievalConfig.salience_weight`
- Added `surprise_weight: float = 0.3` to `SalienceConfig` — was a hardcoded 0.3 in `IngestService._episode_salience()`
- Changed `tau_seconds` default `3600 → 604800` (7 days, half-life ≈ 4.8 days) — prior 1h half-life meant all memories were at floor within 4h; brain-analogue for hippocampal episodic is 1–30 days
- Made all 4 benchmark eval scripts accept `--tau-seconds`, `--salience-weight`, `--surprise-weight` via CLI (was hardcoded; unblocks parameter sweeps)

### Ablation (salience_weight 0.3 vs 0.0, LoCoMo + StaleMemory)
- **LoCoMo**: +2.0pp overall (79.6% vs 77.6%), driven by +11pp adversarial (81% vs 70%). Mild -2.1pp single-session, -1.4pp multi-session.
- **StaleMemory**: +0.07pp (noise). Salience irrelevant for stale detection — that's a schema-supersession problem, not episodic re-ranking.
- **Conclusion**: salience_weight is alive, primarily as adversarial distractor suppressor.

### Grid search (salience_weight ∈ {0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0}, LoCoMo limit=5)

| sw | overall | adversarial | single | multi |
|----|---------|-------------|--------|-------|
| 0.0 | 77.6% | 70.0% | 77.5% | 90.2% |
| 0.3 | 79.6% | 81.0% | 75.3% | 88.8% |
| **0.5** | **80.6%** | **89.0%** | 73.9% | 87.6% |
| 0.7 | 80.7% | 91.1% | 71.8% | 87.6% |
| 1.0 | 80.9% | 92.0% | 73.2% | 87.6% |

Elbow at 0.5: +1.0pp overall, +8pp adversarial vs 0.3, only -1.4pp single-session. Beyond 0.5, marginal overall gain while single-session keeps paying.

### Parameter change
- `RetrievalConfig.salience_weight` default: **0.3 → 0.5**
- All 4 eval script defaults updated to match

### Final benchmark (full 10-conv LoCoMo, sw=0.5)
- Overall: **79.7%** (+1.0pp vs prior 78.7%) — confirmed by independent full suite run
- Adversarial: **89.0%** | Multi-session: 86.4% | Single-session: 74.1% | Temporal: 61.4%
- Temporal eval (internal, 15 scenarios): **86.7%** (+6.7pp vs prior 80.0%) — likely correlated with salience_weight increase but only 15 scenarios

### Micro-benchmark (2026-07-08)
- `test_salience_calibration.py` written: 27 deterministic tests (0.04s)
- Verifies: decay curve, novelty, consolidation penalty, lifecycle, sampling, floor invariants
- All pass as part of `uv run pytest tests/unit/`

## Open Questions for Next Iteration
- `surprise_weight=0.3` is still the default — no sweep done yet (transition model cold-start at eval time means surprise is likely ~0 for most episodes)
- Tau per-benchmark still hardcoded (locomo=30d, others=1d) — not swept
- `salience_gate` ablation not run separately — folded into retrieval plan
