# Supersession Direction Score + Cross-Scope Generalization from `remember`

**Date:** 2026-06-24  
**Branch:** `fix/supersession-direction-generalize`  
**Status:** Implemented — pending benchmark evaluation

---

## 1. Problem Statement

Two connected bugs discovered through analysis of cross-scope Karpathy Guidelines feeding:

### Bug 1: P3 auto-supersession ignores the SupersessionManifold

`engine.py` (P3 block, cosine-based auto-supersession) fires on any schema pair with cosine ≥ 0.85, using a no-op timestamp guard:

```python
if candidate.last_updated_ts < int(time.time()):   # always True
    self.schemas.update_status(candidate_id, status="superseded", ...)
```

The `SupersessionManifold` SVD1 axis — which was explicitly built to distinguish value substitution from restatement — was imported but never consulted. Result: stable behavioral guidelines, preferences, and semantic paraphrases are silently superseded by re-remembering the same concept.

### Bug 2: Cross-scope `remember` of identical content has no generalization path

When the same memory is stored via `remember` across N project scopes:
- `find_duplicate` is scope-locked → N separate stage-0 schemas created
- Stage-0 schemas are scope-locked at retrieval → never recalled cross-scope
- `_update_utility_scores` only counts generalization from `context_recall_items` (recall events)
- `remember` events never advance the generalization stage counter

Bootstrap deadlock: a schema needs cross-scope recalls to reach stage 1, but can only be recalled cross-scope after stage 1.

Additionally, `Consolidator._scope_for_episodes()` assigns consolidated schemas the most-recent-episode's scope, discarding the cross-scope grouping that the latent prototype already represents.

---

## 2. Root Cause Analysis

### Why the manifold existed but wasn't used

The manifold was added to detect value substitution in the P2 path (needs_review flagging) but was never wired into P3 (auto-supersession). The investigation (`20260618_encoder_supersession_geometry_investigation.md`) showed SVD1 is domain-local with a small seed set — the conclusion was "not production-ready." However, the domain coverage is sufficient for the core use case: behavioral guidelines and preferences are **anti-aligned** (direction_score ≈ −0.17), meaning the manifold would correctly block their supersession.

### Why find_duplicate is scope-locked (and should stay that way)

`find_duplicate` scope-locking is correct for deduplication: it prevents a memory from scope:A accidentally matching and reinforcing a completely different schema in scope:B that happens to share normalized text. The bug is not in dedup — it's in the absence of a cross-scope reinforcement signal downstream.

---

## 3. Design: Three-Signal Decision Tree

Three LLM-free signals determine the outcome for any `remember` call with cosine ≥ 0.85 to an existing schema:

```
cosine(new, old) >= 0.85?
├── NO  → unrelated → create new schema (no change)
└── YES → same topic
    direction_score(new, old) >= DIRECTION_THRESHOLD (0.10)?
    ├── YES → value substitution  → SUPERSEDE old           [P3]
    └── NO  → same concept
        same scope?
        ├── YES → REINFORCE existing, leave new coexisting  [P3]
        └── NO  → REINFORCE existing + cross-scope evidence [P4]
```

**Why synonyms are handled automatically**: `paraphrase-multilingual-MiniLM-L12-v2` encodes semantically, not lexically. Synonyms of the same concept produce high cosine similarity. Their direction score is near zero (no value substitution). They fall into the reinforce path without LLM involvement.

**Why the manifold is sufficient**: The manifold was calibrated on 104 pairs across tech, medical, business, financial, HR, legal, and science domains (+ multilingual). Personal preferences and behavioral guidelines are anti-aligned (SVD1 score ≈ −0.17). For ambiguous cases (direction score 0.05–0.15), the P2 `needs_review` flag is the right response — not auto-supersession.

---

## 4. Implementation

### 4.1 `engine.py` — P3 and P4 blocks

**New imports:**
```python
from slowave.core.supersession_manifold import DIRECTION_THRESHOLD, SupersessionManifold
```

**New helpers:**
- `_get_manifold()`: lazy-init SupersessionManifold when encoder available
- `_fetch_schema_embedding(schema_id)`: fetch stored embedding from DB for direction score computation

**P3 (same-scope, was: no-op timestamp guard)**:
Replace `if candidate.last_updated_ts < int(time.time()):` with:
```python
dir_score = manifold.direction_score(emb, candidate_emb)
if dir_score >= DIRECTION_THRESHOLD:
    # value substitution → supersede (existing behavior preserved)
else:
    # restatement/paraphrase → reinforce existing only
```

**P4 (cross-scope, new)**:
After P3, search `search_embedding(emb, limit=10, scope_id=None)` (all scopes).  
For high-cosine, low-direction-score matches in a *different* scope:
- Call `reinforce_schema(candidate_id, salience_delta=0.05, evidence=[(None, event_id, content, 0.5)])`
- The `raw_event_id` in evidence links the cross-scope remember event to the existing schema

### 4.2 `schema_store.py` — `_update_utility_scores`

Add secondary query counting distinct scopes from cross-scope `remember` evidence:

```sql
SELECT COUNT(DISTINCT ses.scope_id) AS ev_scopes,
       COUNT(DISTINCT ses.id)       AS ev_sessions
FROM schema_evidence se
JOIN raw_events re ON re.id = se.raw_event_id
JOIN sessions ses ON ses.id = re.session_id
WHERE se.schema_id = ?
  AND ses.scope_id IS NOT NULL
```

Merge with existing `context_recall_items`-based counts. This lets `remember` events advance the generalization stage without requiring actual recall events first, breaking the bootstrap deadlock.

---

## 5. Files Changed

| File | Change |
|---|---|
| `slowave/core/engine.py` | Import `DIRECTION_THRESHOLD`; add `_get_manifold()`, `_fetch_schema_embedding()`; rewrite P3; add P4 |
| `slowave/symbolic/schema_store.py` | `_update_utility_scores`: add evidence-scope secondary query; merge counts |

---

## 6. Benchmark Expectations

### Expected improvements
- **StaleMemory**: stable/same-concept re-remembering should reinforce instead of supersede → recall accuracy improves when querying reinforced memories
- **WikiScenarios**: same-concept cross-session reinforcement → better schema salience → more reliable recall
- **Cross-scope generalization**: schemas stored in multiple scopes should advance generalization stage faster → surfaced in `activate` across scopes

### Expected regressions (watch for)
- **LongMemEval knowledge-update**: if direction_score mis-classifies a genuine value update as restatement → schema not superseded → stale fact survives → factual recall error
  - Mitigation: manifold was calibrated on this domain; threshold 0.10 leaves headroom
- **StaleMemory (concrete prefs)**: preference supersession — manifold explicitly excludes personal preferences (anti-aligned). P3 will now REINFORCE preferences that it previously superseded. If test expects suppression of old preferences, this could regress.
  - This is the most likely regression point: need to check StaleMemory preference-update scenarios

### Metrics baseline (pre-fix)
To be captured from `main` before merge:

| Benchmark | Baseline | Post-fix | Delta |
|---|---|---|---|
| LongMemEval | — | — | — |
| StaleMemory | — | — | — |
| LoCoMo | — | — | — |
| WikiScenarios | — | — | — |

---

## 7. Open Questions

1. **Preference supersession**: The manifold anti-aligns personal preferences. After this fix, "I prefer tea" → "I prefer coffee" will NOT auto-supersede because direction_score < 0.10 for preferences. Is this acceptable, or do we need a preference-specific supersession path? P1 (pattern-based) still fires on explicit update language ("I now prefer..."), so only implicit preference changes are affected.

2. **Direction score fallback when encoder unavailable**: currently defaults to `DIRECTION_THRESHOLD` (boundary case → neither supersede nor reinforce). Should this be configurable?

3. **Consolidation cross-scope merge gap**: `Consolidator._scope_for_episodes()` still discards cross-scope prototype information by assigning the most-recent episode's scope. This is a separate issue — fixing it would require consolidation to detect when a prototype spans multiple scopes and promote the resulting schema accordingly.
