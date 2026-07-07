# Procedural Architecture Decisions

**Date:** 2026-06-24
**Status:** CONCLUSION — pause procedural layer development. Existing memory dynamics sufficient. Three rounds of GPT 5.5 review (§2, §6, §8).
**Context:** Multi-turn investigation of how slowave processes Karpathy coding guidelines from 3 projects. Culminates in the conclusion that the procedural layer is unnecessary — existing memory dynamics (episodes + schemas + prototypes + transition-biased retrieval) already solve the behavioral structure problem.

---

## 1. Investigation Arc

### 1.1 Phase 1: Initial Evaluation

Three projects ingested Karpathy guidelines ([andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills/blob/main/skills/karpathy-guidelines/SKILL.md)). The initial evaluation revealed:

- Only high-level category summaries were stored (sch_10: 4 category names)
- Project-specific applications captured (sch_19, sch_20, sch_32) but with content bleed
- **18+ atomic sub-rules were missing** — the individual behavioral rules under each category
- Brain alignment score: **~40%**

### 1.2 Phase 2: Granular Storage

All 22 atomic sub-rules stored individually via `slowave_remember()`:

| Category | Count | Type | Schema IDs |
|---|---|---|---|
| Think Before Coding | 4 | `constraint` | sch_37-40 |
| Simplicity First | 6 | `constraint` | sch_41-46 |
| Surgical Changes | 7 | `constraint`/`preference` | sch_47-53 |
| Goal-Driven Execution | 3 | `constraint`/`procedure` | sch_54-56 |
| Tradeoff (caution vs speed) | 1 | `fact` | sch_57 |
| Usage context | 1 | `fact` | sch_58 |

### 1.3 Phase 3: Consolidation Effect

After `slowave consolidate` CLI run:

| Metric | Before | After |
|---|---|---|
| Edges | 208 | **238** (+30) |
| Prototypes | 18 | **20** (+2 emergent category centroids) |
| Meta-schemas | — | +1 (sch_59) |
| Procedures promoted | 0 | 0 |
| Brain alignment | ~55% | **~75%** |

The +2 prototypes discovered "Think Before Coding" and "Simplicity First" without being told the categories exist.

### 1.4 Phase 4: Deprecate `remember_procedure()`

**Decision:** Deprecate `remember_procedure()` in favor of unified `remember()` endpoint. Rationale: `remember_procedure()` with explicit metadata fields contradicts slowave's core thesis ("memory consolidation does not require language"). LLM agents execute verbal descriptions directly — they don't need a separate procedural store.

---

## 2. Four Architecture Decisions

### 2.0 GPT 5.5 External Review

An external review surfaced a fundamental critique:

> "The moment you introduce concepts like `sequence_group`, `sequence_index`, `next_step`, `goal`, `task_type` — you are already encoding a specific theory of what a 'procedure' is. That theory fits software development workflows and checklists, but does not obviously fit language learning, cooking, chess, driving, social interaction, scientific reasoning, medical diagnosis, or artistic creation."

**The brain does not store procedures explicitly.** It accumulates context→action→outcome triples. From repetition emerge habits, policies, expectations, skills, and procedures. The procedure is **inferred later**, not stored first.

**Two routes, one conversion:**

| Route | Mechanism | Brain System | Slowave analog |
|---|---|---|---|
| Route 1: Told the procedure | Declarative: "I know about this" | Hippocampus | schema with type="instruction" |
| Route 2: Repeatedly performed | Procedural: "I can do this" | Basal ganglia | Observed trajectory in sessions |
| Conversion: Declarative→procedural | "Mirror,signal,maneuver"→automatic | Cortex→striatum | instruction + trajectory + outcomes → stronger |

**Core insight:** temporal order already exists in session event streams. The ReplayEngine (replay_engine.py:338-355) already sorts episodes by timestamp, maps to prototypes, and counts prototype→prototype transitions as P(dst|src) stored in `prototype_edges.w_transition`. The `TransitionModel` (transition_model.py) already uses these w_transition weights at retrieval time to predict next-prototype embeddings — this is wired into the retrieval pipeline as "predictive completion" (retrieval.py:203-257). The **prototype-level** infrastructure exists end-to-end. The gap is only at the **schema level**: there is no mechanism to surface prototype transitions as schema-to-schema trajectory relations.

### 2.1 Sequence Encoding: REVISED — Do NOT add sequence metadata to `remember()`

**Original decision (evt_75, SUPERSEDED):** Add `sequence_group`/`sequence_index` to `remember()`.

**Why it was wrong:**

1. **Domain-specific:** `sequence_group`/`sequence_index` encode a software-procedure theory. A brain doesn't annotate step numbers — it experiences events in order.
2. **Confuses experienced vs declared order:** Theta-phase precession encodes the *experienced* sequence, not a *declared* one.
3. **Redundant:** Temporal order already exists in session event streams.
4. **Symbolic labels are English-bound:** `next_step` is a named relation. The brain just has "A followed by B" many times.

**Revised decision (evt_79):**

1. **Keep `remember()` pure** — no sequence metadata, no procedure-specific params.
2. **Stated procedures → regular schemas** — store as `type="instruction"` or `type="constraint"`. Regular embedding.
3. **Leverage existing prototype-level transition graph** — ReplayEngine discovers temporal transitions; TransitionModel already uses them for predictive completion in retrieval. Domain-agnostic.
4. **Add schema-level trajectory derivation** (NEW consolidation step, must be built): when prototype transitions are strong AND specific schema pairs co-occur in sequence, create `schema_relation` edges with `relation="trajectory"` (add to `VALID_RELATIONS`).
5. **Trajectory retrieval:** the existing TransitionModel predictive-completion path (retrieval.py:203-257) already surfaces "what comes next" at the prototype level. Schema-level trajectory edges would provide a complementary, more granular signal — but the retrieval traversal loop ("schema → prototype → w_transition → next prototype's schemas → repeat") does NOT exist yet and would need to be built as part of Step B.

**Existing infrastructure (prototype-level, already functioning):**

| Component | Location | Status |
|---|---|---|
| Transition counting | replay_engine.py:338-355 | ✅ Counts P(dst\|src) from time-sorted episodes |
| Transition storage | prototype_edges.w_transition | ✅ Conditional probabilities persisted |
| Predictive completion | retrieval.py:203-257 | ✅ TransitionModel.predict() → next-embedding → cosine seed |
| TransitionModel | transition_model.py:66-112 | ✅ Graph-based successor representation, reads w_transition |
| Spreading activation | retrieval.py:259-262 | ✅ graph.neighbors() uses combined weight |

**What must be built (schema-level, does NOT exist):**

| Component | Description |
|---|---|
| `"trajectory"` relation type | Add to `VALID_RELATIONS` in schema_store.py:22 |
| Schema-level trajectory derivation | New consolidation step: map strong prototype transitions → `schema_relation` edges |
| Trajectory retrieval traversal | Optional: ordered traversal of trajectory edges for sequence-aware recall |
| Trajectory embedding | Mechanism to represent a sequence as a single comparable vector (needed for §2.3) |

### 2.2 Content Bleed: Pattern Separation

**Problem:** sch_19, sch_20, sch_32 conflate Karpathy tags with unrelated project CRITICAL rules.

**Root cause:** `canonical_schema_text()` doesn't include scope in embedding input. all-MiniLM-L6-v2 sees all content in the same semantic space.

**Solution (evt_76):** Scope-prefix canonical text — mirrors dentate gyrus context-dependent orthogonalization:
```python
# Before: parts = [f"Claim: {claim.strip()}"]
# After:
parts = [f"Scope: {scope_id or 'global'}", f"Claim: {claim.strip()}"]
```
Secondary: consider raising `CROSS_SCOPE_COS_THRESHOLD` 0.78→0.85.

### 2.3 Stated vs Observed: Outcome-Anchored Matching

**Problem:** If user states "run tests → lint → push" and sessions show "pytest → ruff → git push", how does Slowave know they're equivalent? Zero word overlap.

**Solution (evt_80):** Match through outcome space, not step labels. "Verify → check → submit" and "pytest → ruff → git push" both produce *clean validation before submission* — close in embedding space.

| Layer | What | How |
|---|---|---|
| Declarative | Instruction schema | Regular schema with embedding |
| Episodic | Observed sessions | Session event order → prototype transitions |
| Consolidated | Trajectory schema | w_transition edges between prototypes |
| Match | Compare embeddings | Cosine similarity in outcome space |
| Reinforcement | If close → stronger | Co-activation during replay |

No foreign keys. No step correspondence. Scales across cooking, chess, driving, language learning.

**Open implementation gap:** There is no "trajectory embedding" mechanism — no way to represent a sequence of prototypes/schemas as a single comparable vector. Prototypes have centroids, but a trajectory is a *path* through multiple prototypes. Options to evaluate:
- Mean-pool the centroids along the trajectory (simple, loses order)
- Positional-weighted mean (preserves rough order, still a bag-of-centroids)
- Learned sequence encoder (most expressive, most complex)
This is a prerequisite for the outcome-matching layer and must be designed before Step B.

**Open risk (evt_85):** Outcome-space matching collapses functional equivalence (same outcome) with procedural equivalence (same method). "pytest→ruff→push" and "manual QA→review→deploy" both achieve "clean validation" but have different risk profiles and failure modes. Cosine similarity alone over-generalizes. A concrete fix requires a risk-profile representation that does not exist yet — this is a deeper problem deferred to a future design pass.

### 2.4 Procedure Extraction from Feedback

**Current state:** `promote_candidates_from_feedback()` (procedural.py:473) works but creates entries in deprecated `procedural_memories`. It groups feedback by `(goal, task_type)` — lexical fields that contradict the domain-agnostic thesis (see §2.0 GPT 5.5 critique).

**Revised approach:**
1. Replace `(goal, task_type)` lexical grouping with **geometric grouping**: cluster feedback events by prototype trajectory similarity (sessions that followed similar prototype transition paths)
2. Create trajectory schemas from recurrent prototype transitions (ReplayEngine already tracks w_transition)
3. Associate feedback outcomes with trajectories via outcome space (requires trajectory embedding — see §2.3 gap)
4. Promote when supported by stated procedures AND observed success

**Dependency chain:**
```
A: Add "trajectory" to VALID_RELATIONS
B: Add schema-level trajectory derivation in consolidation
   (includes trajectory embedding mechanism — see §2.3 gap)
C: Modify promote_candidates_from_feedback():
   - replace (goal, task_type) grouping with prototype trajectory similarity
   - output schema store + trajectory relations instead of procedural_memories
D: Remove procedural_memories table + ProceduralMemoryStore
```

**Note on `goal`/`task_type`:** These fields still exist in `context_feedback_events` and are populated by the cognitive-cycle API. They should not be removed from the schema (they carry useful provenance), but they should no longer be the *grouping key* for procedure candidate discovery. The grouping key becomes geometric.

---

## 3. System State Summary

| Metric | Value |
|---|---|
| Episodes | 57 |
| Prototypes | 20 |
| Schemas | 62 |
| Procedures (separate store) | 0 |
| Edges | 238 |
| Brain alignment | ~75% |

### Decisions stored this session

| Event ID | Content | Type | Status |
|---|---|---|---|
| evt_75 | `sequence_group`/`sequence_index` on `remember()` | decision | **SUPERSEDED** by evt_79 |
| evt_76 | Fix content bleed via scope-prefixed canonical text | decision | Active |
| evt_77 | Dependency chain for procedure extraction | decision | Active (revised §2.4) |
| evt_79 | REVISED: Do NOT add sequence metadata to `remember()` | decision | Active |
| evt_80 | Outcome-anchored matching: stated vs observed | decision | Active |
| evt_81 | ReplayEngine already has emergent trajectory learning | lesson | Active |
| evt_82 | Trajectory edges EXPLANATORY ONLY — never prescriptive | constraint | Active |
| evt_83 | Gap: no causal direction filter for transitions | open_question | Open |
| evt_84 | Gap: prototype lifecycle instability → non-stationary graph | open_question | Open |
| evt_85 | Gap: outcome-space collapses functional vs procedural equivalence | open_question | Open |
| evt_86 | System is a temporal behavioral graph, not a procedural engine | fact | Active |

### Schemas reinforced
sch_62, sch_60, sch_34, sch_36, sch_59, sch_1, sch_23, sch_9

---

## 4. Prior State

- `20260622_procedural_memory_redesign.md` — remove `remember_procedure()` from MCP
- `20260623_0719_brain_inspired_procedural_memory_v4.md` — unified implementation plan
- `20260624_brain_inspired_gaps.md` — gap analysis
- `20260624_geometry_only_supersession.md` — language-independent supersession

---

## 5. Open Risks

1. **Trajectory edges as hidden procedures (CRITICAL):** Without the explanatory-only constraint, trajectory edges silently become a procedural engine — "procedures with no name." Mitigation: evt_82 — trajectories CAN explain (describe what tends to happen) but must NEVER prescribe (tell the agent what to do). The LLM is the decision-maker.

2. **No causal direction filter:** "A followed by B" counts as an edge regardless of whether B was caused by A or both triggered by external context ("open IDE → run tests" both caused by "user starts debugging"). Spurious edges overconnect into false policies. Mitigation: context-conditioned transition weighting — weight by session context embedding or event-type conditioning. Separate co-occurrence (weak), transition (strong), causality (inferred).

3. **Prototype lifecycle instability:** Prototypes updated incrementally per replay batch — no stability guarantee. Schema moving from prototype A→B between epochs makes w_transition edges stale and transition graph non-stationary. **Note:** freezing prototypes per epoch would break the dentate-gyrus pattern separation mechanism (replay_engine.py:194-218) which depends on incremental centroid drift to accommodate novel episodes. **Revised mitigation:** edge-weight decay proportional to centroid drift magnitude — when a prototype's centroid shifts, its old w_transition edges decay proportionally to the drift, preserving incremental learning while preventing stale edges.

4. **Outcome-space collapses functional vs procedural equivalence:** "pytest→ruff→git push" and "manual QA→review→deploy" both achieve "clean validation" but have different risk profiles, toolchains, failure modes. Cosine similarity alone over-generalizes. Mitigation: outcome similarity weighted by risk profile similarity (what fails, what invariants hold), not just embedding closeness.

5. **`canonical_schema_text()` scope change:** Adding scope to canonical text changes all embeddings. Consolidation replay rebuilds relations naturally (hippocampal re-encoding).

6. **`promote_candidates_from_feedback()` migration:** Table-switch from procedural_memories to schemas must preserve candidate→active→deprecated lifecycle.

---

## 6. Second External Review: Hidden Procedural Reintroduction

**Review source:** GPT 5.5 analysis of the revised §2.1 decision (evt_79).

**Verdict:** Architecture coherence 8/10, biological plausibility 7.5/10, moderate risk of implicit procedural reintroduction.

**The most important conceptual clarification:**

> "Your system is converging to a multi-scale temporal graph of behavioral regularities — not a brain-like procedural memory system. That is good, but different. There are no true 'procedures' — only stable subgraphs, attractor paths, and high-probability transitions under context."

**Three places where procedural theory leaks back in:**

| Location | Risk | Fix |
|---|---|---|
| `schema_relation="trajectory"` | Becomes "procedures with no name" | Explanatory only — never prescriptive (evt_82) |
| Outcome-space matching | Collapses functional vs procedural equivalence | Risk-profile-weighted similarity (evt_85) |
| Prototype transitions as policy | Non-stationary graph → noise-amplified trajectories | Epoch-based prototype freezing (evt_84) |

**Missing infrastructure identified:**

- **Causal direction filter:** distinguishes "A caused B" from "A and B share a cause" (evt_83)
- **Context-conditioned transition weighting:** session context embedding or event-type conditioning
- **Prototype stability per epoch:** freeze membership during consolidation, decay-sensitive re-clustering

**Critical design choice (not yet decided):**

> Do you want trajectories to be explanatory artifacts only, or active inference objects in planning?

If explanatory only: system stays emergent, LLM remains decision-maker, thesis preserved.
If active inference: system reverts to a procedural engine, thesis violated.

The default is explanatory-only (evt_82). Changing this would require a separate, explicit design decision with brain-alignment justification.

---

## 7. Technical Review: Infrastructure Accuracy & Unresolved Tensions

**Review source:** Code-level audit of the plan against the actual retrieval and consolidation codebase.

### 7.1 "No new code needed" was false — corrected in §2.1

The original §2.1 claimed "Existing infrastructure (no new code needed)." This was inaccurate. The plan has been revised (§2.1) to distinguish:

- **Prototype-level (exists):** transition counting, w_transition storage, TransitionModel predictive completion, spreading activation — all functioning end-to-end.
- **Schema-level (must be built):** `"trajectory"` relation type, schema-level trajectory derivation, trajectory retrieval traversal, trajectory embedding.

The TransitionModel (transition_model.py) is the existing mechanism by which "what comes next" influences retrieval today. It reads `w_transition` directly from `prototype_edges` (line 133-136), finds the nearest prototype to the query, looks up successor prototypes, and returns a weighted average of successor centroids. This predicted embedding is then used as a second cosine seed in retrieval (retrieval.py:203-257), discounted by `transition_score_weight` (0.7) so it never overrides a real cue match.

The proposed schema-level trajectory edges would **complement, not replace** the TransitionModel. The TransitionModel operates at prototype granularity (coarse, domain-agnostic). Schema-level trajectory edges would operate at schema granularity (fine, more specific). Both feed the same retrieval pipeline.

### 7.2 The explanatory/prescriptive tension — resolved

§6 posed the question: "explanatory artifacts only, or active inference objects in planning?" and left it unresolved. The tension is real: if trajectory edges influence retrieval (surfacing "what tends to come next" to working memory), they influence agent behavior — which is prescriptive in effect.

**Resolution:** Trajectory-influenced retrieval IS acceptable and does NOT violate the thesis, because:

1. **The LLM can override.** Unlike a motor reflex (basal ganglia → spinal cord, unconscious), surfaced memories reach the LLM's conscious decision-making. The LLM sees "what usually comes next" and can choose to ignore it.
2. **The existing TransitionModel already does this.** Predictive completion (retrieval.py:203-257) already surfaces next-state predictions to working memory. This has been in production since Stage 3. If this were prescriptive in the violating sense, the system would already be a procedural engine.
3. **The distinction is "surfaces" vs. "executes."** Memory surfaces context; the LLM executes decisions. A trajectory edge that surfaces "after tests, you usually lint" is no different from a constraint schema that surfaces "always run tests before pushing" — both are context, neither is a command.

**Therefore:** trajectory edges may participate in retrieval (like the TransitionModel does), but must never be formatted as directives. The constraint is not "don't use in retrieval" but "don't format as imperative."

### 7.3 Missing evaluation plan

The plan describes what to build but not how to measure whether it works. Required before implementation:

| Test | What it measures | Success criterion |
|---|---|---|
| Trajectory discovery | N sessions following a known pattern (e.g., pytest→ruff→push across 5 sessions) | Trajectory edges formed matching ground truth within 2 consolidation passes |
| False positive rate | Sessions with unrelated sequential events | < 10% spurious trajectory edges |
| Outcome matching | Stated procedure "verify before submit" vs observed "pytest→ruff→push" | Cosine similarity of trajectory embeddings > 0.7 |
| Scope-prefix effect | sch_19/sch_20/sch_32 before/after canonical text change | Cross-scope cosine for unrelated rules drops below 0.70 |

### 7.4 Missing embedding migration plan for scope-prefix change (§2.2)

Changing `canonical_schema_text()` to prepend scope changes every existing embedding. Unresolved questions:

- **When:** immediately on deploy, or lazily during next consolidation? Recommend: immediately, with a one-time migration script that re-embeds all active schemas.
- **Existing relations:** `schema_relations` edges formed under old embeddings will have stale confidence. Recommend: mark all existing `reinforces`/`refines` edges for re-evaluation during the next consolidation pass (don't delete — let the geometric judge re-evaluate).
- **Self-healing:** over N consolidation passes, relations rebuild naturally. But the first post-migration retrieval may be degraded. Recommend: run `slowave consolidate` immediately after migration.

### 7.5 Summary of corrections applied

| Section | Issue | Fix |
|---|---|---|
| §2.1 | "No new code needed" was false | Split into "existing (prototype-level)" and "must be built (schema-level)" tables |
| §2.1 step 5 | Described a retrieval traversal that doesn't exist | Clarified: TransitionModel predictive completion exists; schema-level traversal must be built |
| §2.3 | No trajectory embedding mechanism | Added open implementation gap with 3 options to evaluate |
| §2.3 | evt_85 risk had no concrete fix | Acknowledged as deferred — risk-profile representation doesn't exist yet |
| §2.4 | `(goal, task_type)` grouping contradicts domain-agnostic thesis | Replaced with geometric grouping (prototype trajectory similarity) |
| §5 risk 3 | Prototype freezing would break DG pattern separation | Replaced with edge-weight decay proportional to centroid drift |
| §6 | Explanatory/prescriptive tension unresolved | Resolved in §7.2: trajectory retrieval is acceptable (LLM can override, TransitionModel already does this) |
| §7.3 | No evaluation plan | Added 4 test scenarios with success criteria |
| §7.4 | No embedding migration plan | Added migration steps: immediate re-embed, mark relations for re-evaluation, run consolidate |

---

## 8. Final Conclusion: Pause Procedural Layer Development (evt_90)

**Review source:** GPT 5.5 third analysis — "Maybe procedures are not first-class memory objects at all."

### 8.1 The Karpathy experiment proved the opposite of what was expected

Expected: guidelines → procedure extraction → reusable coding behavior.
Actual: guidelines → 22 schemas → consolidation → emergent category prototypes.

**The system already generalized without any procedural machinery.** The interesting result was not that procedures failed — it was that they weren't needed.

### 8.2 The "rarely triggered" signal

- Episodes: used every session
- Schemas: used every session
- Pattern separation: used every consolidation pass
- Supersession: used every `remember()` call
- Procedures: never naturally triggered, need contrived examples, hard to evaluate

If a memory mechanism were biologically essential, you would constantly encounter situations that need it. After 4 design iterations, procedures have never been naturally triggered. **This indicates the abstraction itself is unnecessary, not that the implementation is wrong.**

### 8.3 The two-types confusion (root cause)

| Type | Examples | Already handled by |
|---|---|---|
| Type A: explicit instructions | "Run tests before pushing", "Think before coding" | Schemas (constraint type), recalled when relevant |
| Type B: repeated trajectories | "read code → understand → test → implement → commit" | Transition graph + TransitionModel predictive completion |

The procedural layer sat between these two, serving neither well.

### 8.4 What the existing system already provides

| Procedural need | Already solved by |
|---|---|
| "Do step 1, then step 2" | TransitionModel predictive completion (retrieval.py:203-257) |
| "When situation X, do Y" | Schema recall (constraint type) |
| "Repeated success becomes automatic" | w_transition strengthening + salience + consolidation |
| "Category-level behavioral structure" | Prototype emergence (proven by Karpathy) |
| "Related behaviors co-activate" | Spreading activation over prototype graph |

No concrete failure case has been identified that the existing system cannot solve.

### 8.5 Recommendation

1. **Do NOT build:** trajectory schemas, trajectory embeddings, outcome-space matching, `"trajectory"` relation type, schema-level trajectory derivation
2. **Do NOT remove yet:** `procedural_memories` table and `ProceduralMemoryStore` — unused (0 procedures), harmless. Cleanup, not architecture.
3. **DO implement:** scope-prefix fix (evt_76) — real bug, real impact on pattern separation
4. **DO test:** verify scope-prefix fix improves content bleed for sch_19/20/32

The question to return to: **can you demonstrate a concrete failure that episodes + schemas + prototypes + transition-biased retrieval cannot solve?** If no, the procedural layer stays dormant — and that's the correct outcome.
