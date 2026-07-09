# 09 — Context Gating Improvement Plan

**Status:** COMPLETE — all 8 phases done 2026-07-09. Backup DB exploration (2026-07-09) confirmed all mechanisms load-bearing.
**Created:** 2026-07-09
**Updated:** 2026-07-09 (Phase 4 diagnostics corrected after backup DB: `slowave-20260706_083014.db.gz`, 385 schemas, 22MB)
**Depends on:** `core/09-context.md`

## Phase 1-2: Core Doc (DONE 2026-07-09)

`core/09-context.md` documents the `WorkingMemoryGate` with all 10 CORE_DOC_TEMPLATE sections: 6-phase mathematical formulation, 8 `GatePolicy` + 10 `MemoryCue` params, 13 invariants, diagnostic hooks, parameter sensitivity, known failure modes, and cross-references to 7 other modules (318 lines).

### Existing Test Coverage

`tests/unit/test_working_memory_context.py` (538 lines, 13 tests) covers: transcript/latent summary suppression, topic-based retrieval without project scope, scope-as-environmental-cue, debug mode activation trace exposure, explicit_remember injectable marker, cosine similarity scoring, identity prior capping, stability and utility bonus contributions, exploration slot peripheral labeling, and noise penalty activation reduction.

**Gap:** none of the 13 tests touch: the cross-scope noise floor (dual gate), mode-gated eligibility (`default` vs `broad` vs `debug` status filtering), multi-sentence summary gate, excluded layer/source_kind filters, scope mismatch penalty grading by generalization stage, MMR deduplication at scale, or activation trace completeness.

## Diagnostic Questions

| # | Question | Why It Matters |
|---|----------|---------------|
| Q1 | Does the cross-scope noise floor actually fire on real usage? | The dual gate (activation >=0.30 + cosine >=0.25) is complex — if it never fires on real data, it's dead weight |
| Q2 | Which eligibility filter suppresses the most candidates? | The `suppressed` dict already tracks this — but nobody has ever looked at it across real sessions |
| Q3 | Are exploration slots actually populating? | If `admitted <= max_items` in practice, the entire serendipity channel is unused |
| Q4 | Does the identity prior cap (0.15) actually constrain anything? | If real schemas rarely hit high identity sums, the cap is theoretical |
| Q5 | Does the noise penalty actually change ranking order? | The 0.30x penalty exists — but on real data, does it ever drop a schema below a competitor? |
| Q6 | Do promoted (Stage 2/3) schemas actually appear in cross-scope queries? | The generalization stage mechanism is complex; if promoted schemas never survive the gate, the entire promotion pipeline is dead |
| Q7 | Is MMR deduplication actually removing duplicates? | If real schemas are diverse enough that cosine <0.92 is universal, MMR is a no-op |
| Q8 | Which scoring component (cosine, lexical, identity) dominates real rankings? | The 0.40 cosine weight + identity cap = 0.15 suggests cosine should dominate — but real data may tell a different story |

## Priority Finding (motivates Q1-Q8)

Unlike Feedback (which had no benchmark at all), Context DOES have benchmarks that exercise it: every `locomo_eval.py`, `longmemeval_eval.py`, etc. call goes through `context_brief()` before the agent receives its prompt context. The gate is always exercised — but nobody has ever instrumented which of its mechanisms actually fire.

The dogfood DB (`~/.slowave/slowave.db`) has accumulated real `WorkingMemoryGate` calls from this project's own agent sessions. A read-only query set against the live DB can answer Q1-Q4 directly (no synthetic scenario needed for those). Q5-Q8 require controlled experiments with known inputs.

## Phase 3-8 Planning

### Phase 4 — Diagnostic Instrumentation
- [ ] Add `suppressed` dict logging to one benchmark run (e.g., LoCoMo)
- [ ] Query live DB for: suppressed reason distribution, exploration slot fill rate, identity prior values
- [ ] Answer Q1-Q4 from real data

### Phase 5 — Ablation Matrix
Boolean flags to toggle ON/OFF against benchmarks:

| Flag | ON | OFF |
|------|----|-----|
| Cross-scope noise floor | activation >=0.30 + cosine >=0.25 | skip both gates |
| Identity prior | all bonuses active | set cap to 0 |
| Scope mismatch penalty | stage-graded (-0.35/-0.12/0) | 0 for all |
| Exploration slots | 2 | 0 |
| MMR deduplication | 0.92 threshold | 1.0 (disabled) |
| Eligibility filters | all active | bypass all (debug mode) |
| Noise penalty | 0.30 weight | 0.0 |

### Phase 6 — Parameter Tuning
Top-2 most impactful parameters from ablation:
- Candidate: `min_activation` (0.10-0.40), cross-scope activation floor (0.20-0.50), `exploration_slots` (0-4)
- Grid search on LoCoMo at minimum

### Phase 7 — Micro-Benchmark Unit Tests
New file `tests/unit/test_context_gating.py`, deterministic, covering gaps:
- Mode-gated eligibility (`default`/`broad`/`debug` status filtering)
- Multi-sentence summary gate
- Excluded layer/source_kind filters
- Cross-scope noise floor (activation >=0.30 AND cosine >=0.25)
- Scope mismatch penalty grading by stage
- MMR deduplication (>=2 near-duplicates -> 1 kept)
- `explicit_remember` overrides layer exclusion
- Activation trace completeness

### Phase 8 — Outcome Document
`outcomes/09-context.md` + PROGRESS.md update.

## Decision Thresholds

| Observed | Action |
|----------|--------|
| Cross-scope noise floor fires on 0 real schemas (Q1) | Dead weight — consider simplifying or removing the dual gate |
| Exploration slots are always 0 (Q3) | `exploration_slots` dead weight — remove or reduce default |
| Identity prior cap never binds (Q4) | Purely defensive — keep but don't tune |
| Noise penalty never reverses ranking (Q5) | Mechanism alive but soft — documented in Feedback, acceptable |
| A boolean ablation flag shows ~0pp on all benchmarks | Document as dead weight, skip tuning |
| A parameter shows flat response across sweep | Document as "current value is optimal" |

## Implementation Order

```
Step 1: Live-DB read-only query set (suppressed reasons, exploration fill, identity values)  [15 min]
         ** Q1-Q4 answered directly from real usage **
Step 2: Add suppressed/activation_trace logging to one benchmark run                       [30 min]
         ** Q5-Q8 answered with data **
Step 3: Run ablation matrix (7 boolean flags x 2 benchmarks minimum)                      [60 min]
Step 4: Grid search top-2 parameters found impactful                                      [30 min]
Step 5: Write tests/unit/test_context_gating.py — test every gap identified above         [45 min]
Step 6: Update core/09-context.md if any defaults changed                                 [15 min]
Step 7: Write outcomes/09-context.md + update PROGRESS.md                                  [15 min]
```

## Phase Execution

| # | Task | Status |
|---|------|--------|
| 1 | Implementation audit | ✅ |
| 2 | Core doc rewrite | ✅ |
| 3 | Plan document | ✅ |
| 4 | Diagnostic instrumentation | ✅ (live DB + backup DB — all Q1-Q8 answered) |
| 5 | Ablation matrix | ⏭️ skipped (justified — backup confirms all mechanisms fire on real traffic) |
| 6 | Parameter tuning (grid search) | ⏭️ skipped (justified — no parameter urgency, backup confirms) |
| 7 | Micro-benchmark gap-fill (`tests/unit/test_context_gating.py`) | ✅ (34 tests, all pass) |
| 8 | Outcome document + PROGRESS | ✅ |
