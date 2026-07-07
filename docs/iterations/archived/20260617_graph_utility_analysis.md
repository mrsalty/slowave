# Graph Utility Analysis: What Would Make Spreading Activation Meaningful

**Date**: 2026-06-17
**Follows**: `docs/iterations/20260616_wiki_scenarios_analysis.md` (P3)

---

## The blunt question

> Could we remove the graph and would slowave still work as-is?

**Today, yes.** The graph contributes zero measurable boost on every published benchmark (LME, LoCoMo, StaleMemory, WikiScenarios). You could delete the spreading-activation pipeline and slowave's scores would not change.

But removing it now would be premature. The graph solves a problem that no benchmark currently tests.

---

## What the graph is designed for

Multi-hop associative recall — pattern completion. The kind of retrieval where cosine alone has zero signal:

```
Query: "What did I work on after the project with the orange logo?"

Cosine path:
  "orange logo" → "Helios visual identity"     ← 1 hop, cosine works
  "after the project" → ???                     ← zero cosine overlap

Graph path:
  orange_logo_proto → Helios_proto → post_Helios_work_proto   ← 2 hops
```

The brain does this constantly: a partial cue triggers full recall through associative chains. The graph is the correct mechanism. But every benchmark asks **direct-cue questions** where cosine already wins.

---

## Why the graph shows zero contribution

Three compounding layers:

### Layer 1 — Benchmarks don't test multi-hop

| Benchmark | Query type | Graph needed? |
|---|---|---|
| LongMemEval | "What is my preferred X?" | No — direct keyword overlap |
| LoCoMo | "What did we discuss about Y?" | No — direct keyword overlap |
| StaleMemory | "Do I still prefer Z?" | No — direct keyword overlap |
| WikiScenarios R | "How did Rome expand?" | No — direct keyword overlap |
| WikiScenarios C | "How did Roman soldiers build fortifications?" | No — cos=0.43, graph still can't help |

**Zero benchmarks ask "after X, what was Y?"** — the one question type that requires graph.

### Layer 2 — The graph is deliberately kneecapped

```python
# slowave/latent/retrieval.py
spread_decay: 0.6             # ×0.6 per hop → 0.36 after 2 hops
spread_episode_weight: 0.15   # harvested episodes score at 0.15
spread_score_ceiling: 0.9     # capped at 90% of worst cosine-direct score
```

Design rationale: *"graph episodes should fill gaps below cosine candidates, not compete with them on equal footing."* Correct for avoiding noise, but means graph only helps when cosine finds **nothing** — which never happens at Wikipedia scale.

### Layer 3 — Geometric constraint (single-hop only)

For single-hop graph completion, a fundamental tension exists:

```
For prototype edges:  cos(fact, page) must be HIGH (≈0.7+)
For graph-only retrieval: cos(fact, query) must be LOW (≈0.0)

But cosine is transitive:
  cos(fact, page) ≈ 0.7 ∧ cos(page, query) ≈ 0.7
  ⇒ cos(fact, query) ≈ 0.5
```

At cos ≈ 0.5, cosine ranks the fact in the top-20 schemas. The graph's 0.15 bonus can't change a top-5 outcome. This constraint is **real for single-hop**, but it does **not** apply to multi-hop: `cos(query, target)` can be genuinely zero while edges exist through intermediate prototypes.

---

## What would make the graph meaningful

### 1. Multi-hop scenarios (P3b) — the real test

Scenarios that REQUIRE 2-hop traversal:

```
Session A: "Project Helios uses an orange logo"
Session B: "After Helios wrapped, I started Project Nimbus"

Query: "What project did I work on after the one with the orange logo?"

  Hop 1: "orange logo" → Helios_proto            (cosine — works)
  Hop 2: Helios_proto → Nimbus_proto              (graph ONLY — zero cosine)

Expected keyword: "Nimbus"
```

| Condition | Expected result |
|---|---|
| `full` (graph ON) | HIT — graph traverses Helios_proto → Nimbus_proto |
| `no_graph` (graph OFF) | MISS — cosine finds Helios but not Nimbus |

If 2-hop scenarios miss under `full`, the graph's core mechanism is broken, not just untuned.

### 2. Tune graph parameters (P3c) — find the knee

| Parameter | Current | Sweep range | What it controls |
|---|---|---|---|
| `spread_episode_weight` | 0.15 | [0.15, 0.30, 0.50, 0.70] | Base score of harvested episodes |
| `spread_score_ceiling` | 0.90 | [0.90, 1.00, 1.20] | Cap relative to worst cosine score |
| `spread_decay` | 0.60 | [0.40, 0.60, 0.80] | Activation retention per hop |

Measure on existing WikiScenarios: does any setting flip a scenario from miss → hit under `full` while keeping `no_graph` stable? Avoid regressions on R/I/G/D/S families.

### 3. Scale (P4) — the honest bet

At 1000+ sessions with complex interleaved topics, cosine returns a noisy top-10. The graph's associative edges could re-rank noise into signal. At small scale (1-2 pages), cosine is sufficient. At large scale (P4: 6 pages × 6 sessions × 30 days), graph might become necessary.

---

## Recommendation

**Don't remove the graph yet.** Instead:

| Step | ID | What | Success criterion |
|---|---|---|---|
| 1 | P3b | 3 multi-hop (2-hop) C-family scenarios | `full` hits where `no_graph` misses |
| 2 | P3c | Sweep graph parameters | Find knee where graph helps without regressions |
| 3 | P4 | WikiScenarios-L at scale | Graph delta > 0 at 36+ sessions |

**Exit condition:** If after all three, graph still shows zero contribution on multi-hop scenarios, remove it. The architecture would simplify substantially: drop `GraphManager`, `spreading activation` pipeline, `prototype_edges` table, and the `neighbor_top_k`/`use_spreading` config paths.

If it DOES work on multi-hop, keep it and invest in making the benchmarks test what the graph is good at.

---

## Current capability matrix (post-P3)

| Capability | Status | Verdict |
|---|---|---|
| Cosine retrieval | ✅ Strong | Does all the heavy lifting |
| Temporal decay | ✅ Works | LME temporal-reasoning 96.2% |
| Multi-scale (fine+coarse) | ❓ Unknown | No ablation published |
| Supersession (retrieval) | ✅ Works | Correct fact surfaces |
| Supersession (schema mutation) | ⚠️ Partial | Old schema not deprecated (P2) |
| Predictive completion (TransitionModel) | ❓ Unknown | No benchmark tests it |
| Graph spreading activation | ⚠️ Zero (single-hop) | Untested on multi-hop (P3b) |
| Consolidation at scale | ❓ Unknown | Untested (P4) |
