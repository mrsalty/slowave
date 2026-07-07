# Brain-Inspired Procedural Memory v4: Unified Implementation Plan

**Date:** 2026-06-23
**Status:** Design — implementation-ready
**Supersedes (merged into this doc):**
- `20260623_0719_brain_inspired_procedural_memory_v3.md` (acquisition + enforcement, boundary-hardened)
- `20260623_0719_procedure_cross_scope_generalization.md` (cross-scope generalization)
**Background:**
- `20260622_procedural_memory_redesign.md` (auto-detection classifier — still a separate workstream, summarized in §10)
- v1/v2 of the procedural plan (superseded; see §0 for what changed)
**Review source:** Three rounds of Opus code-level review against the full repo.

---

## 0. What this document is

A single, self-contained plan for procedural memory in Slowave, covering four mechanisms that all
feed one `ProceduralMemoryStore` with one lifecycle:

1. **Acquisition** — how procedures are born (implicit mining + explicit classifier).
2. **Enforcement** (Tier 1) — detecting when a session followed a procedure, and applying dopamine-style feedback.
3. **Enrichment** (Tier 2) — replacing generic placeholder steps with real content.
4. **Generalization** — letting a proven procedure earn cross-scope visibility.

### Version history (corrections already absorbed)

| Step | Issue found in code review | Resolution (now baked in) |
|---|---|---|
| v1→v2 | Event stream too sparse for subsequence mining; ignored the existing `promote_candidates_from_feedback()` | Pivot to *evolving* the existing miner; lower coverage threshold; drop LCS order check |
| v2→v3 | `encode()` called inside the embedding-free `procedural.py`; §3 example oversold Option B | Move all embedding work up a layer; realistic Option-B example; exclude `task_complete` from scorer |
| generalization v1→v4 | §1 mischaracterized scope affinity as a hard multiplier; reused schema thresholds despite far sparser signal; wrong `ScopeRegistry` API; SQL referenced a non-column; `or 0.2` falsy bug; `track()` never passed `scope_id` so evidence stayed scope-less | All corrected inline (§5). Notably: **`track()` now threads the session scope into `apply_feedback`** — without this the cross-scope signal never exists. |

---

## 1. Core thesis

Procedural memory in the brain is the **crystallization of repeated, successful action sequences** —
the basal ganglia records `input1 → input2 → input3 → outcome(success) → store procedure`. The
feedback (dopamine reward) is the encoding trigger, not a content classification.

What Slowave already has (verified in code):
- `ProceduralMemoryStore` with a `candidate → active → deprecated` lifecycle (procedural.py:23, 431-436).
- `apply_feedback()` with `success_alpha`/`failure_beta` reinforcement (procedural.py:389).
- Promotion gate `success_count >= 3 AND confidence >= 0.7` (procedural.py:431).
- `promote_candidates_from_feedback()` — implicit acquisition by grouping `context_feedback_events`
  on `(goal, task_type)` (procedural.py:467, wired at engine.py:669).
- A free consolidation hook (`consolidate_once`, services/consolidation.py:40).
- A complete schema-generalization stack reused in §5 (`GeneralizationConfig.compute_stage`,
  `ScopeRegistry`, schema_store.py:32-188).

What is missing: enforcement tracking (Tier 1), step enrichment (Tier 2), and procedure
generalization (§5).

---

## 2. Architectural boundary (applies to everything below)

`slowave/core/procedural.py` has a hard contract (module docstring): *"No LLM is used here.
Matching is deterministic lexical/metadata scoring."* `ProceduralMemoryStore.__init__(self, db, cfg)`
takes **no encoder**.

**Rule:** `procedural.py` never calls `encode()`, `cosine()`, or imports `numpy`. All embedding work
lives in the new modules that receive a `TextEncoder` via constructor injection
(`procedural_enforcement.py`, `procedural_enrichment.py`, `latent/classifier.py`). They pass
*pre-computed* values (step lists, coverage floats) across the store boundary. The store stays pure.

---

## 3. Tier 1 — Enforcement tracking

### Event-stream reality

Under the cognitive-cycle API a session has ~3–7 `raw_events`:
`[context_query, remember:decision, remember:fact, …, task_complete]`. `slowave_recall` and
`slowave_reinforce` log nothing. The `remember:*` events are the semantically richest. Coverage
scoring matches procedure steps against `remember:*` content only —  `context_query` is the task
text and `task_complete` content is literally `"outcome=X"` (tools.py:528), so both are excluded.

### Mechanism (`slowave/core/procedural_enforcement.py`)

```python
class ProceduralEnforcement:
    """Session-end adherence tracking. Owns embedding work; procedural.py stays pure."""

    def __init__(self, store: ProceduralMemoryStore, encoder: TextEncoder, db: SQLiteDB):
        self.store = store
        self.encoder = encoder
        self.db = db

    def compute_step_coverage(
        self,
        procedure_steps: list[str],
        session_events: list[RawEvent],
        match_threshold: float = 0.65,
    ) -> float:
        """Fraction of procedure steps with at least one matching remember:* event."""
        relevant = [e for e in session_events if e.type.startswith("remember:")]
        if not relevant or not procedure_steps:
            return 0.0
        step_embs = [self.encoder.encode(s) for s in procedure_steps]
        matches = 0
        for step_emb in step_embs:
            scores = [cosine(step_emb, e.embedding) for e in relevant if e.embedding is not None]
            if scores and max(scores) >= match_threshold:
                matches += 1
        return matches / len(procedure_steps)

    def track(self, session_id: str, goal: str | None, outcome: str) -> dict:
        """Called from session_end. Correlates session goal + events against active procedures."""
        if not goal:
            return {"tracked": False, "reason": "no_goal"}

        # CRITICAL: resolve the session's own scope so feedback evidence is scope-attributed.
        # Without this, procedural_memory_evidence.scope_id is NULL and §5 generalization
        # can never observe scope_id != origin_scope_id. (This was the v3 track() bug.)
        session_scope = self._get_session_scope(session_id)   # SELECT scope_id FROM sessions WHERE id=?
        events = self._get_session_events(session_id)
        procs = self.store.retrieve(goal=goal, scope_id=session_scope, limit=5, mode="default")

        results = []
        for match in procs:
            if match.score < 0.3:
                continue
            coverage = self.compute_step_coverage(match.procedure.procedure_steps, events)
            feedback = None
            if coverage >= 0.5:
                feedback = "useful" if outcome == "success" else "wrong"
                self.store.apply_feedback(
                    procedure_id=match.procedure.id,
                    feedback=feedback,
                    outcome=outcome,
                    session_id=session_id,
                    scope_id=session_scope,            # <-- threads scope into the evidence row
                    goal=goal,
                )
            results.append({
                "procedure_id": f"proc_{match.procedure.id}",
                "coverage": round(coverage, 2),
                "feedback": feedback,
            })
        return {"tracked": True, "goal": goal, "results": results}
```

### Feedback routing

| Condition | Action |
|---|---|
| `coverage >= 0.5` AND `outcome == success` | `apply_feedback(useful)` |
| `coverage >= 0.5` AND `outcome == failure` | `apply_feedback(wrong)` |
| `coverage < 0.5` | no signal (too sparse to judge) — **logged, not silent** |

`coverage < 0.5` will be common under sparse events. That is correct behavior, not failure: no
signal → no feedback → procedure neither reinforced nor penalized. The tracker emits a metric so
"nothing to score" is distinguishable from "scorer no-oped." 1-step procedures are binary
(any match → 1.0); the 0.5 threshold means "any match → signal," which is right for an atomic policy.
The 0.5/0.65 constants are **starting points pending calibration** (§11.4).

---

## 4. Tier 2 — Evolve the existing miner (enrichment)

### What exists vs. what changes

`promote_candidates_from_feedback()` already groups successful feedback by `(goal, task_type)` and
crystallizes candidates — but with generic placeholder steps (procedural.py:514-519):

```python
steps = ["Reuse the memory cluster that was useful before: sch_12, sch_34.",
         "Preserve recurring requirements: testing, authentication.",
         "Apply this workflow for goal 'fix auth bug' and task type 'debugging'."]
```

The miner **stays lexical and stays in `procedural.py`**. Enrichment happens one layer up, in a new
`ProceduralEnrichment` helper owned by `ConsolidationService` (which has the encoder). Enriched,
deduplicated steps are passed *into* `promote_candidates_from_feedback()` via an optional
`enriched_steps` parameter.

```python
# slowave/core/procedural_enrichment.py  (owns the encoder)

def enrich(self, db, session_ids: list[str]) -> list[str]:
    """Extract + dedup remember:* content from the sessions behind a feedback group."""
    rows = db.connect().execute(
        "SELECT content FROM raw_events WHERE session_id IN ({}) "
        "AND type LIKE 'remember:%' ORDER BY ts, id".format(",".join(["?"] * len(session_ids))),
        session_ids,
    ).fetchall()
    return self._deduplicate_steps([r["content"] for r in rows])

def _deduplicate_steps(self, candidates: list[str], threshold: float = 0.7) -> list[str]:
    """Keep first representative of each semantic cluster. Order = cross-session arrival order
    (NOT within-procedure sequence order) — fine for presence-based coverage, not strict sequencing."""
    if not self.encoder or len(candidates) <= 1:
        return candidates
    embs = [self.encoder.encode(c) for c in candidates]
    kept, result = [], []
    for i, emb in enumerate(embs):
        if not any(cosine(emb, c) >= threshold for c in kept):
            kept.append(emb)
            result.append(candidates[i])
    return result
```

### Honest scope: Option B vs Option A

**Option B (recommended default, no new event types).** `remember:*` content is *declarative*
(facts/decisions/lessons), because the global guidance tells the agent not to log ephemeral task
state. Realistic enriched output for goal "implement oauth login":

```python
steps = ["use JWT with 15min access token and 7-day refresh token",
         "auth endpoint at POST /api/auth/token, returns {access_token, refresh_token}",
         "passport.js oauth2 strategy requires explicit session: false"]
```

These are **fact-shaped**, not "do X then Y" — they surface the knowledge cluster useful for the
goal. That is the real ceiling of Option B; the plan does not pretend otherwise.

**Option A (opt-in).** To get action-shaped steps ("run tests before committing"), the agent must
log `remember:action` events with action narration. Cost: more rows, friction with the
"don't log ephemeral state" guideline. Recommendation: ship Option B; offer Option A as an opt-in
system-prompt flag. The fidelity gap is tracked in §9.

---

## 5. Cross-scope generalization

### 5.1 The actual problem (corrected)

Cross-scope retrieval is governed by `_scope_affinity()` (procedural.py:538-547):
`same=1.0, related(same kind)=0.5, different=0.0`. **Correction to the original generalization doc:**
this is an **additive term weighted at `scope_affinity_weight = 0.10`** (procedural.py:303/358), *not*
a multiplier, and `retrieve()` has **no hard scope filter** — it scores everything and keeps
`score >= min_procedure_score`. So a cross-scope procedure with `affinity = 0.0` loses ~0.10 of
additive contribution (and adds 0.10 to the normalizer denominator); it is **softly penalized, not
blocked**. A strong universal procedure can already fire cross-scope today.

Implication: the feature is worth adding (a proven procedure should shed even the soft penalty and
gain a positive cross-scope contribution), but its leverage is bounded by the 0.10 weight. If
stronger scope-locking is desired, that requires a separate change (e.g. a stage-0 hard gate), which
this plan does **not** silently assume. We keep the additive model, consistent with schemas.

### 5.2 Reuse the schema generalization stack

| Element | Reuse? | Verified |
|---|---|---|
| `GeneralizationConfig.compute_stage(distinct_scopes, distinct_scope_kinds, scope_breadth_pct, scope_kind_breadth_pct, distinct_sessions=0)` | **Yes** | signature matches exactly (schema_store.py:104-140) |
| `ScopeRegistry.active_counts(window_days=90) -> (total_active_scopes, total_active_scope_kinds)` | **Yes** | **single tuple-returning method** — there is no `active_scope_count()` (schema_store.py:188) |
| `procedural_memory_evidence` for cross-scope counts | **Yes** | already stores `scope_id, scope_kind, session_id, outcome` per feedback (schema.sql:369) |
| `WorkingMemoryGate` scope-gating | **No** | procedures have their own retrieval path |

### 5.3 Procedure-specific thresholds (do NOT reuse schema thresholds verbatim)

The schema thresholds assume *abundant* recall signal (`scope_registry.record(is_recall=True)` fires
on every `activate`). Procedure signal is far sparser: it fires only when a procedure was *followed*
(`coverage >= 0.5`) cross-scope with `outcome == success`. Reusing schema stage-3 (8 distinct scopes
+ 5 sessions) would make stages 2–3 effectively unreachable.

Introduce a `ProcedureGeneralizationConfig` with lower thresholds (starting points, calibrate in §11.4):

| Stage | Min distinct cross-scopes | Min distinct sessions | Min scope-kind breadth |
|---|---|---|---|
| 1 Portable | 2 | 2 | — |
| 2 Contextual | 3 | 2 | 40% |
| 3 Global | 4 | 3 | 60% |

`compute_stage()` itself is reused unchanged; only the config thresholds differ.

### 5.4 Schema + promotion

```sql
ALTER TABLE procedural_memories ADD COLUMN generalization_stage INTEGER NOT NULL DEFAULT 0;
-- 0=scoped, 1=portable, 2=contextual, 3=global
```

Promotion runs during consolidation, for each active procedure, querying the **evidence already
written by Tier 1** (note `origin_scope_id` is bound as a parameter — it is a column on
`procedural_memories`, not on the evidence table):

```python
row = db.execute(
    """SELECT COUNT(DISTINCT scope_id)      AS distinct_scopes,
              COUNT(DISTINCT scope_kind)     AS distinct_scope_kinds,
              COUNT(DISTINCT session_id)     AS distinct_sessions
       FROM procedural_memory_evidence
       WHERE procedure_id = ? AND outcome = 'success' AND scope_id != ?""",
    (proc.id, proc.origin_scope_id),
).fetchone()

total_scopes, total_kinds = registry.active_counts()          # tuple unpack — corrected API
breadth      = row["distinct_scopes"] / total_scopes if total_scopes else 0.0
kind_breadth = row["distinct_scope_kinds"] / total_kinds if total_kinds else 0.0
new_stage = proc_gen_cfg.compute_stage(
    row["distinct_scopes"], row["distinct_scope_kinds"], breadth, kind_breadth, row["distinct_sessions"]
)
if new_stage > proc.generalization_stage:
    store.set_generalization_stage(proc.id, new_stage)
```

This depends entirely on Tier 1 having written scope-attributed evidence (§3 `track()` fix). If
`track()` did not pass `scope_id`, every evidence row has `scope_id = NULL`, the `!=` filter matches
nothing, and no procedure ever generalizes.

### 5.5 Stage-aware retrieval gating

Replace the constant `_scope_affinity()` with a stage-aware version. Note this **changes the method
signature** from `(current, origin)` to `(current_scope, proc)` — the caller in `score()`
(procedural.py:278) must be updated to pass the whole procedure. Use explicit config fields instead
of the `x or 0.2` idiom (since `0.0` is falsy, `different_scope_affinity or 0.2` silently overrides a
configured zero — a latent bug):

```python
# new config fields on ProceduralMemoryConfig:
#   stage1_cross_affinity: float = 0.5   # same scope_kind only
#   stage2_cross_affinity: float = 0.3   # any kind, penalized
#   stage3_cross_affinity: float = 1.0   # global, no penalty

def _scope_affinity(self, current_scope: str | None, proc: ProceduralMemory) -> float:
    if not current_scope or not proc.origin_scope_id:
        return 0.0
    if current_scope == proc.origin_scope_id:
        return self.cfg.same_scope_affinity                    # 1.0
    gs = proc.generalization_stage
    if gs == 0:
        return 0.0
    if gs == 3:
        return self.cfg.stage3_cross_affinity                  # 1.0
    same_kind = scope_kind(current_scope) == proc.origin_scope_kind
    if gs == 1:
        return self.cfg.stage1_cross_affinity if same_kind else 0.0
    return self.cfg.stage2_cross_affinity                      # gs == 2, any kind
```

Remember the leverage ceiling: even stage 3 only restores ~0.10 of additive score (§5.1).

---

## 6. Dual-pathway model & lifecycle

| Pathway | Brain analogue | Slowave mechanism |
|---|---|---|
| Implicit (experience) | Basal ganglia | `promote_candidates_from_feedback()` (enriched, §4) |
| Explicit (declared) | Prefrontal override | `slowave_remember(type="procedure")` → latent classifier (§10) |

```
BIRTH
 ├─ Explicit: remember("when X, do Y then Z") → classifier → procedure (conf=0.6)
 └─ Implicit: miner finds 3+ successes for a goal → procedure (conf=0.5–0.65)

VALIDATION  (Tier 1, every session_end)
   coverage ≥ 0.5 + success → reinforce ;  + failure → penalize ;  < 0.5 → no signal

PROMOTION (confidence)         success_count ≥ 3 AND confidence ≥ 0.7 → active
GENERALIZATION (scope breadth) cross-scope success evidence → stage 0→1→2→3 (§5)
DEMOTION / SUPERSESSION         confidence < 0.55 → candidate ;  < 0.35 OR failures ≥ 3 → deprecated
```

Confidence-promotion and scope-generalization are **orthogonal axes**: one governs *whether* a
procedure fires, the other *where*.

---

## 7. Schema changes (consolidated)

```sql
ALTER TABLE sessions ADD COLUMN goal TEXT;
ALTER TABLE sessions ADD COLUMN outcome TEXT;
ALTER TABLE procedural_memories ADD COLUMN source TEXT NOT NULL DEFAULT 'implicit';   -- implicit|explicit
ALTER TABLE procedural_memories ADD COLUMN superseded_by_id INTEGER;                  -- retroactive interference
ALTER TABLE procedural_memories ADD COLUMN generalization_stage INTEGER NOT NULL DEFAULT 0;
```

No new tracking table. `procedural_memory_evidence` (schema.sql:369) already records
`(procedure_id, session_id, scope_id, scope_kind, goal, outcome, feedback)` per `apply_feedback()`
call — both enforcement and generalization read it. Migrations go in `sqlite_db.py`.

---

## 8. Files & changes (consolidated)

### New files (all own a `TextEncoder`; none of this lives in `procedural.py`)

| File | Purpose |
|---|---|
| `slowave/core/procedural_enforcement.py` | `ProceduralEnforcement`: `compute_step_coverage()`, session-end `track()` (threads scope) |
| `slowave/core/procedural_enrichment.py` | `ProceduralEnrichment`: `enrich()`, `_deduplicate_steps()` |
| `slowave/latent/classifier.py` | `MemoryTypeClassifier` (§10 / 20260622) |

### Modified files

| File | Change |
|---|---|
| `slowave/storage/schema.sql` | the five columns in §7 |
| `slowave/storage/sqlite_db.py` | migration entries for those columns |
| `slowave/core/engine.py` | persist `goal` in `session_start`, `outcome` in `session_end`; instantiate `ProceduralEnforcement` and call `track()` in `session_end`; instantiate `ProceduralEnrichment`; wire classifier in `remember()` |
| `slowave/core/procedural.py` | `promote_candidates_from_feedback()` accepts optional pre-computed `enriched_steps`; `_scope_affinity` becomes stage-aware (signature change → update `score()` caller); new affinity config fields; `set_generalization_stage()` + `promote_generalization()` (pure SQL, no encoder); use `source`/`superseded_by_id` |
| `slowave/core/services/consolidation.py` | call `ProceduralEnrichment.enrich()` and pass steps into the miner; call `promote_generalization()` |
| `slowave/mcp/tools.py` | pass `goal` through `activate → session_start`; pass `outcome` through `commit → session_end`; make `type` optional on `remember` |

### Data flow

```
activate(goal="fix auth bug")
  → session_start(goal=…)                 ← NEW: goal on sessions row
  → context_brief(goal=…)                 ← existing: goal in context_recall_events

[agent works]
  → remember("use JWT 15min expiry")      → raw_events: remember:decision
  → reinforce(feedback=useful)            → context_feedback_events (scope_id from recall event)

commit(outcome="success")
  → session_end(outcome=…)                ← NEW: outcome on sessions row
     → form_episodes                       ← existing
     → ProceduralEnforcement.track()      ← NEW (Tier 1; resolves session scope, writes scoped evidence)

[worker]
  → replay_once() / consolidate()          ← existing
  → ProceduralEnrichment.enrich()          ← NEW; feeds steps into …
  → promote_candidates_from_feedback()     ← existing, now with real steps
  → promote_generalization()               ← NEW (§5); reads scoped evidence
```

---

## 9. Brain-fidelity review

| Property | Implementation | Fidelity | Notes |
|---|---|---|---|
| Implicit acquisition | enriched `promote_candidates_from_feedback()` | High | feedback-gated; encoder used only outside procedural.py |
| Dopamine learning | `apply_feedback()` (`success_alpha`/`failure_beta`) | High | |
| Context gating | `goal` + `trigger_pattern` | High | |
| Gradual automation | candidate(0.5) → active(0.7) | High | |
| Cross-context transfer | stage 0→3 generalization (§5) | Medium | leverage bounded by 0.10 affinity weight; honest about that |
| Retroactive interference | supersession via `superseded_by_id` | High | |
| Sequence chunking | step extraction | Low–Medium | Option B steps are declarative, not action sequences; no hierarchy; weak ordering |
| Trace richness | sparse `remember:*` (Option B) | **Gap** | the load-bearing risk; gated behind the Option A/B decision (§11.1) |

---

## 10. Relationship to the 20260622 classifier (separate workstream)

| Source | Mechanism | Fires |
|---|---|---|
| `slowave_remember(content)` | latent `MemoryTypeClassifier` | at remember time |
| feedback events + enriched steps | `promote_candidates_from_feedback()` (this doc) | during consolidation |
| `slowave_remember_procedure(steps)` | explicit (to be deprecated) | user declares |

The classifier requires the multilingual encoder upgrade (`paraphrase-multilingual-MiniLM-L12-v2`)
**before** it can route non-English content (20260622 review gap #8). Make that a hard prerequisite
of step 5 below. The classifier's embedding work also lives outside `procedural.py`.

---

## 11. Implementation order

1. **Decide event granularity + confirm encoder placement.** (a) Option A vs B (recommend B, Option A
   opt-in); (b) confirm every `encode()`/`cosine()` call is in `procedural_enforcement.py`,
   `procedural_enrichment.py`, or `classifier.py` — never `procedural.py`.
2. **Schema migration** (§7) — needed by everything.
3. **Tier 1 enforcement** (`procedural_enforcement.py` + `session_end` hook). Smallest surface,
   highest leverage. **Must thread session scope into `apply_feedback`** (§3) — this is also the
   precondition for §5.
4. **Tier 2 enrichment** (`procedural_enrichment.py` + miner change).
5. **Generalization** (§5): `generalization_stage` column, `ProcedureGeneralizationConfig`,
   stage-aware `_scope_affinity`, `promote_generalization()` consolidation hook. Enhancement on top
   of Tier 1; not a dependency of Tiers 1–2.
6. **Latent classifier** (§10) — gated on the multilingual encoder upgrade.
7. **Deprecate `slowave_remember_procedure`** — only after all acquisition paths work.

### Tests (Level 1, per mechanism)

- Enforcement: `test_coverage_exact/partial/no_match`, `test_coverage_excludes_task_complete`,
  `test_coverage_excludes_context_query`, `test_coverage_one_step_binary`, `test_feedback_routing`,
  `test_feedback_no_signal`, `test_track_writes_scoped_evidence` (scope_id non-null).
- Enrichment: `test_extract_remember_content`, `test_deduplicate_steps`,
  `test_deduplicate_order_is_arrival`, `test_encode_lives_outside_procedural` (no encode/cosine import).
- Generalization: `test_procedure_stage0_scope_locked`, `test_procedure_stage_promotion_from_evidence`,
  `test_generalization_needs_scoped_evidence` (NULL scope → no promotion),
  `test_stage3_cross_scope_fires`.
- Lifecycle: `test_candidate_promotion`, `test_supersession_chain`, `test_cold_start`.

### Open questions (calibration)

- Coverage thresholds (0.5 / 0.65) and procedure-generalization thresholds (§5.3) need empirical
  calibration against real session data; report the coverage distribution before fixing them.
- Goal clustering: embedding-similarity grouping vs exact `(goal, task_type)` string match — decided
  upstream of the lexical miner, so it doesn't touch the `procedural.py` boundary.
- Is the 0.10 affinity weight enough leverage for generalization to change retrieval outcomes, or is
  a stage-0 hard gate warranted (§5.1)?
