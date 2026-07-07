# WikiScenarios: Ablation Analysis & Slowave Performance Directions

**Date**: 2026-06-16  
**Branch**: `feature/wiki-cognition-benchmark`

---

## Four Signals from the Ablation Matrix

```
Ablation           R      I      G      D      S    sal_expected
full               3/4    3/3    3/3    3/3    2/2  0.41
no_salience        4/4    3/3    3/3    3/3    2/2  0.01 (floor)
no_graph           3/4    3/3    3/3    3/3    2/2  0.41
no_consolidation   3/4    3/3    3/3    3/3    2/2  0.41 (unfixed v1)
```

**Signal 1 — Embedding geometry provides isolation without help from any component**  
I-family 3/3 across ALL ablations. At Wikipedia-scale domain diversity, cosine alone
separates ML/Rome/Music/Physics. Graph, salience, and schemas add zero marginal isolation.

**Signal 2 — Salience is a ranking margin, not a gate; but the formula is unnormalised**  
D-family sal_expected: 0.41 (full) vs 0.01 (no_salience). Signal works. Problem:
`cosine + 0.1 * raw_salience` where raw salience ranges 0.01–4.0+. The R-2 miss→hit
flip under no_salience exposes this: salience_weight=0.4 nudges marginal keyword `"legion"`
just outside top_k=10. Fix: normalise salience to [0,1] before mixing.

**Signal 3 — Supersession fires at retrieval level, not schema mutation level**  
S-family 2/2 (correct new fact in answer) but `v1_kw_still_active=True` always.
`"now uses"` pattern surfaces the new fact correctly. Old schema not auto-deprecated
because Wikipedia schemas contain old terms in broad text, scoring below
`AUTO_SUPERSEDE_THRESHOLD=0.85`. Fix: add cosine-similarity fallback for same-scope schema pairs.

**Signal 4 — Graph and consolidation need harder tests**  
no_graph = full because all queries have strong direct cosine hits. Graph is for
indirect-cue queries ("what do I usually do after standup?") — none exist in current scenarios.
no_consolidation = full because at 1-2 pages episodic retrieval suffices; schema value
appears at 50+ sessions with decayed episodes.

---

## What This Means for Slowave Overall

Cross-referencing against `docs/benchmarks.md` (LME 93.4%, LoCoMo 81%, StaleMemory 86–89%):

- WikiScenarios retrieval 93% = consistent with LME 93.4% — not a corpus artefact
- Isolation 100% = new measurement, no prior baseline, genuine strength
- Temporal decay = consistent with LME temporal-reasoning 96.2%
- Supersession retrieval = consistent with LME knowledge-update 94.9%
- Supersession schema mutation gap = explains ~5% residual miss rate in knowledge-update
- 20pp preference gap vs Mem0 = structural/architectural, requires semantic inference

---

## Five Improvement Directions

### P1 — Normalise salience in ranking *(effort: S, impact: M)*

Fix in `slowave/core/services/retrieval.py` line ~270:
```python
import math
_norm = lambda s: 2.0 / (1.0 + math.exp(-s / 2.0)) - 1.0  # [0,∞) → [0,1)
schemas = sorted(filtered_schemas,
    key=lambda s: schema_scores.get(s.id, 0.0) + salience_weight * _norm(s.salience),
    reverse=True)[:top_k]
```
**Measurable**: R-2 stable (hit) across all ablations.

### P2 — Cosine-based supersession fallback *(effort: M, impact: H)*

After `find_superseded_candidates` returns empty in `engine.remember()`:
```python
if not supersession_candidates and emb is not None:
    for sid, score in self.schemas.search_embedding(emb, limit=5, scope_id=scope_id):
        if score > 0.90:
            self.schemas.adjust_feedback_state(sid, needs_review=True)
```
Doesn't auto-supersede (avoids false positives) but flags for review.  
**Measurable**: WikiScenarios S-family `v1_kw_still_active` → False.

### P3 — Add WikiScenarios-Completion family (C) *(effort: S → ✅ DONE)*

3 indirect-cue scenarios following `tests/temporal_eval/scenarios/completion.py` pattern.
Only way to measure graph spreading activation's contribution.
→ **Details under ## P3 — ✅ IMPLEMENTED below.**

### P4 — WikiScenarios-L: scale test for consolidation *(effort: M, impact: answers key question)*

G-family variant with 6 pages × 6 sessions over 30 simulated days. Old episode salience
decays to floor; only schema-level retrieval can answer. Confirms or denies consolidation's
value for long-term memory.

### P5 — Sweep salience_weight via D-family *(effort: S, impact: principled calibration)*

Sweep [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]. Pick value where sal_expected > sal_anti
maximally AND R-family stable. Currently 0.4 is hand-tuned.

---

### P3 — ✅ IMPLEMENTED: WikiScenarios-Completion family (C)

**Status:** Implemented 2026-06-17. 3 scenarios in `tests/wiki_scenarios/scenarios.py`.

**Design:**

| Scenario | Page | Fact (different aspect) | Query matches | Keyword |
|----------|------|------------------------|---------------|---------|
| C-1 | Ancient_Rome | Thermacrete formula (chemistry) | Military construction | Thermacrete |
| C-2 | Artificial_neural_network | NeuroSync ASIC chips (hardware) | Error propagation | NeuroSync |
| C-3 | Jazz | ChromaShift notation (publishing) | Melodic solos | ChromaShift |

Each scenario ingests the Wikipedia page and a synthetic fact in separate `consolidate=True` sessions, ensuring both get prototype mappings. The query targets a different page aspect than the fact, producing low cosine overlap (0.43–0.59).

**Key architectural finding:** `remember()` schemas have NO prototype mapping (`schema_prototype_map` is empty for them). The graph path (`get_many_by_prototypes`) is a dead end for `remember()`-created facts. The fact MUST be ingested via a `consolidate=True` session to get prototype assignment.

**Current results:** All 3 scenarios MISS in both `full` and `no_graph` modes. The graph contributes **zero measurable boost** at Wikipedia scale — even with correct prototype mappings, the 0.15 bonus from `get_many_by_prototypes` is insufficient to lift the fact schema above the page schemas that dominate the top-5.

**Diagnostic detail recorded:** `cos_qf` (query–fact cosine distance), `proto_id` (confirms prototype mapping exists). These serve as a measurement baseline — any future graph improvement should show:
- `hit=True` under `full` where `no_graph` still misses, OR
- Measurable rank delta (graph boosting the fact schema's position)

**Why graph doesn't help:** The geometric constraint is fundamental. For graph edges to form between the fact prototype and page prototypes, `cos(fact, page)` must be high. But cosine is transitive: `cos(fact, page) ≈ 0.7` and `cos(page, query) ≈ 0.7` implies `cos(fact, query) ≈ 0.5` — enough for cosine to rank the fact in the top-20 schemas. The graph's 0.15 bonus doesn't change the top-5 outcome. The only way graph beats cosine is if `cos(fact, query) ≈ 0` — but then `cos(fact, page)` is also ≈ 0, and no prototype edges form.

→ **Full analysis: [`docs/iterations/20260617_graph_utility_analysis.md`](20260617_graph_utility_analysis.md)**

---

## Status Table

| Capability | Status | Bottleneck |
|-----------|--------|-----------|
| Semantic retrieval | ✅ Strong | Ranking formula unnormalised (P1) |
| Domain isolation | ✅ Strong | No bottleneck found |
| Cross-session recall | ✅ Works | Schema value unproven at scale (P4) |
| Temporal decay | ✅ Works | Small time gaps untested |
| Supersession (retrieval) | ✅ Works | Old schema not deprecated (P2) |
| Supersession (schema mutation) | ⚠️ Partial | 6 patterns only (P2) |
| Graph/completion queries | ⚠️ Measured (zero boost) | Graph marginal contribution = 0 (P3) |
| Consolidation at scale | ❓ Untested | Needs WikiScenarios-L (P4) |
| Implicit preference inference | ❌ Gap | Structural; needs semantic inference |
