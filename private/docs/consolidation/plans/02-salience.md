# Salience — Measurement & Improvement Plan

**Based on:** `iteration-strategy.md` (Layer 1 Diagnostics + Layer 2 Ablations) + `02-salience.md` code audit
**Status:** CLEANUP DONE — diagnostic + ablation work pending

---

## 0. What's Already Done

Three changes shipped on 2026-07-08 (cleanup only — no benchmark impact):

| Change | Effect |
|--------|--------|
| Removed dead `recall_reinforcement` / `reinforce_on_recall()` | Config cleanup — was never called |
| Added `surprise_weight: float = 0.3` to `SalienceConfig` | Hardcoded 0.3 is now tunable |
| `tau_seconds` default 3600 → 604800 (7 days) | Production UX only — **benchmarks hardcode their own tau** |

**Key finding from code audit:** Every benchmark overrides tau explicitly:
- `locomo_eval.py`: `tau=86400 * 30` (30 days)
- `longmemeval_eval.py`, `dmr_original_eval.py`, `stalememory_eval.py`: `tau=86400` (1 day)

These were tuned by hand at some point and never swept systematically. The salience_weight default (0.3) was also never ablated — we don't know if salience ranking helps or hurts on any benchmark.

---

## 1. Key Diagnostic Questions

| # | Question | Why It Matters |
|---|----------|---------------|
| Q1 | Does salience_weight > 0 actually improve any benchmark over salience_weight = 0? | If the delta is ~0pp everywhere, salience ranking is dead weight in retrieval |
| Q2 | What is mean_salience at query time? If near min_salience (0.01), salience contributes ~nothing to ranking | Low mean → tau too short or episodes never recalled |
| Q3 | What fraction of episodes are at floor (salience ≤ 0.015)? | High fraction → floor saturation, salience not differentiating |
| Q4 | Does surprise_weight > 0 produce higher initial salience for "interesting" episodes vs redundant ones? | If not, the transition model isn't trained or surprise is always 0 |
| Q5 | Are per-benchmark tau values optimal? Is locomo's 30d better than 7d? Does stalememory benefit from a shorter tau? | No one has swept this — we're flying blind |
| Q6 | Does the salience gate (`salience_gate=True` in RetrievalConfig) help independently of salience_weight? | These are two separate mechanisms; the retrieval ablation left salience_gate untested |

---

## 2. Phase 1 — Diagnostic Instrumentation

The iteration strategy calls for emitting per-benchmark diagnostics. Salience needs three scalars added to benchmark JSON output.

### Step 2.1: Add salience diagnostic to locomo_eval.py (pilot)

After each query, capture from the retrieved `RecallResult`:
```python
"salience": {
    "mean_salience_at_query": mean([m.salience for m in result.episodes]),
    "below_floor_pct": mean([m.salience <= 0.015 for m in result.episodes]),
    "max_salience": max([m.salience for m in result.episodes], default=0.0),
}
```

Add to the per-question JSON row and aggregate to benchmark summary.

### Step 2.2: Verify surprise > 0 fires during ingest

Add a debug flag or one-off script that ingests a session and logs `(novelty, surprise, s0)` per episode. Check that `surprise > 0` for at least some episodes (requires transition model trained after ≥1 replay). If `surprise = 0.0` everywhere, the transition model is cold and `surprise_weight` is currently a no-op too.

---

## 3. Phase 2 — Ablation Matrix

### Step 3.1: salience_weight ablation (most important)

Run LoCoMo + StaleMemory with:

| Config | salience_weight |
|--------|----------------|
| baseline | 0.3 (current) |
| no_salience | 0.0 |

**Why these two benchmarks:** LoCoMo tests general recall quality (salience ranking should help if it amplifies useful memories). StaleMemory tests suppression of outdated content (salience should help here if stale memories naturally decay to floor).

If `baseline ≈ no_salience` on both: salience ranking contributes nothing → Q1 answered negatively → skip sweeps, focus elsewhere.

### Step 3.2: salience_gate ablation

`salience_gate` (`RetrievalConfig`) is a separate Hebbian boosting mechanism — not controlled by `SalienceConfig`. Run LoCoMo with `salience_gate=False` to separate the two signals.

| Config | salience_weight | salience_gate |
|--------|----------------|---------------|
| baseline | 0.3 | True |
| no_salience_weight | 0.0 | True |
| no_salience_gate | 0.3 | False |
| no_salience_both | 0.0 | False |

---

## 4. Phase 3 — Parameter Sweeps

**Gate:** Only proceed if Q1 shows salience_weight > 0 helps by ≥ 0.5pp on any benchmark.

### Step 4.1: salience_weight sweep (LoCoMo)

```python
grid = {"salience_weight": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0]}
```

### Step 4.2: surprise_weight sweep (temporal_eval, fast)

Run temporal_eval harness — it tests recall of episodic content across simulated time gaps, exactly where surprise-based initial salience should help:

```python
grid = {"surprise_weight": [0.0, 0.1, 0.2, 0.3, 0.5, 0.8]}
```

If `surprise_weight=0.0` ≈ `surprise_weight=0.3`: the transition model isn't trained well enough to make surprise meaningful at typical ingest time → Q4 answered negatively.

### Step 4.3: tau sweep per benchmark

All benchmarks hardcode tau but none swept it. Quick grid on LoCoMo (most important benchmark):

```python
# locomo currently uses tau=86400*30; sweep:
grid = {"tau_seconds": [86400, 86400*3, 86400*7, 86400*14, 86400*30, 86400*60]}
```

For StaleMemory: shorter tau should help (stale memories decay naturally). Sweep:
```python
grid = {"tau_seconds": [3600*4, 86400, 86400*3, 86400*7]}
```

---

## 5. Phase 4 — Micro-Benchmark: `test_salience_calibration`

**Location:** `tests/unit/test_salience_calibration.py`

**What it tests:** Does the salience decay curve match the expected exponential at each time step? Deterministic, no external data, runs in < 2s.

```
Setup:
  - Ingest 10 episodes with known s0 values via controlled novelty
  - Record actual stored salience

Advance time:
  - t=0: measure salience distribution → assert s_i in [min_sal, 1.5]
  - t=τ: advance 1 tau (7 days); trigger decay; assert mean(s) ≈ mean(s0) * e^-1
  - t=2τ: advance 1 more tau; assert mean(s) ≈ mean(s0) * e^-2
  - floor: advance 20τ; assert all s == min_salience

Reinforcement test:
  - Recall 3 specific episodes; assert their salience increased by salience_weight (0.3)
  - Recall only cosine-direct (not graph-harvested) episodes → assert non-recalled unchanged

Consolidation penalty test:
  - Trigger replay/consolidation; assert penalized episodes s' ≈ s * 0.5, clamped to min_sal
```

**Invariants verified:**
- Floor is always respected
- Decay is monotone between reinforcement events
- Only cosine-direct episodes get reinforced (not graph-harvested)
- Consolidation penalty is exactly `* consolidation_penalty`

---

## 6. Implementation Order

```
Step 1: Add salience diagnostics to locomo_eval.py                  [30 min]
Step 2: RUN LoCoMo once → read mean_salience, below_floor_pct       [3 min]
         ** Q2, Q3 answered **
Step 3: Run salience_weight ablation (LoCoMo + StaleMemory)          [45 min]
         ** Q1 answered — GO/NO-GO gate **
         -- If Q1 = no-op → STOP, document, move to graph (module 3)
         -- If Q1 = meaningful → continue below
Step 4: Run salience_gate ablation (Step 3.2)                        [15 min]
Step 5: Sweep salience_weight (Step 4.1)                             [20 min]
Step 6: Check surprise > 0 fires (Step 2.2)                         [15 min]
         -- If surprise always 0 → skip surprise_weight sweep
Step 7: Sweep surprise_weight (Step 4.2)                             [10 min]
Step 8: Tau sweep on LoCoMo + StaleMemory (Step 4.3)                 [30 min]
Step 9: Write test_salience_calibration                              [1.5 hr]
Step 10: Update 02-salience.md defaults if anything changed          [15 min]
```

---

## 7. Decision Thresholds

| Observed | Action |
|----------|--------|
| `salience_weight=0 ≈ salience_weight=0.3` on all benchmarks | Salience ranking is decorative → set `salience_weight=0.0` as default, move to graph module |
| `mean_salience_at_query < 0.05` | Tau too short for benchmark's time span → tau is the primary lever |
| `below_floor_pct > 0.80` | Severe floor saturation → tau too short or salience_weight too low |
| `surprise = 0` always | Transition model untrained → surprise_weight tuning premature |
| StaleMemory improves with shorter tau | Natural decay is doing suppression work → tune tau, not feedback |

---

## 8. Success Criteria

1. **Q1 answered:** salience_weight ablation run on LoCoMo + StaleMemory, delta documented
2. **Salience diagnostics emitted** per benchmark run (mean_salience, below_floor_pct)
3. **At least one parameter tuned** from ablation data (or documented as no-op)
4. **`test_salience_calibration` written and passing** (deterministic decay/reinforce/penalize checks)
5. **02-salience.md defaults updated** to reflect any changed values
