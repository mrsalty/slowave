# Slowave Functional Improvement Plan — v2

> Derived from: `slowave_functional_evaluation_review.md`  
> v1 plan: `20260611_0827_functional_improvement_plan.md`  
> GPT review incorporated: 2026-06-11  
> Status: Revised — implementation-ready

---

## What Changed from v1

| v1 | v2 |
|---|---|
| P7 (eval harness) was last | **P0 (eval harness) is first** — run before any code change |
| Strict scope defaulted globally | Strict scope default only for **MCP project activation**; engine/CLI stays `default` |
| Strict scope allowed only `profile` layer cross-scope | Also allows **`scope_id = None` (global) memories** |
| `needs_review` down-ranked 0.20× in recall | **`needs_review` fully excluded** from default recall; visible only in `broad`/`debug` |
| Feedback: bigger flat deltas | **Feedback: nuanced policy** — `wrong+failed` vs `wrong` vs `stale` vs `irrelevant` differ |
| Supersession included `X uses Y` / `X is Y` | **Strong patterns only**; weak patterns deferred |
| Supersession returns `list[int]` | **`SupersessionCandidate` dataclass** with confidence + reason; auto-supersede only ≥ 0.85 |
| Broad summary: sentence count alone | **Provenance (consolidation source) + sentence count**; explicit memories never filtered |
| Projected supersession score 7.0 | Realistic projection **6.5** |
| Release readiness projected 8.0 | Realistic projection **7.5** |

---

## Revised Scorecard

| Feature | Current | v1 Projected | v2 Realistic |
|---|---|---|---|
| Explicit remember/recall | 8.5 | 8.5 | 8.5 |
| Evidence traceability | 8.0 | 8.0 | 8.0 |
| Cross-session continuity | 8.0 | 8.0 | 8.0 |
| Working-memory context brief | 8.0 | 8.5 | 8.5 |
| Scope handling | 6.5 | 8.5 | **8.5** |
| Consolidation | 6.5 | 7.5 | **7.5** |
| Feedback learning | 5.5 | 7.5 | **7.0** |
| Contradiction / supersession | 4.5 | 7.0 | **6.5** |
| Procedural memory retrieval | 4.5 | 7.5 | **7.5** |
| Release readiness | 6.0 | 8.0 | **7.5** |

> Supersession capped at 6.5 until pattern extractor validated against false-positive cases.

---

## Root Cause Analysis (unchanged from v1)

| Issue | Root Cause |
|---|---|
| Scope leakage | `context.py` `_activation()` penalises `-0.35` for `scope_mismatch` but never hard-blocks. |
| Wrong feedback doesn't suppress | `context_feedback_weight=0.5` halves signals. Wrong delta becomes `-0.125`. Schema stays above `min_activation=0.20`. |
| `needs_review` in recall | `recall()` queries `status IN ('active','needs_review')`. **A memory system is judged by what appears in recall, not by internal metadata.** |
| No contradiction/supersession | `status=superseded` exists in schema store but no code path sets it during `remember()`. |
| Procedural retrieval failure | `retrieve()` defaults to `status=active` only. Newly seeded procedures are `candidate`. Never returned unless `include_candidates=True` or `mode=broad/debug`. |
| Duplicate episodes | `recall()` builds `episode_dicts` without deduplication. `remember()` creates both a schema AND an episodic trace. |
| Broad summaries compete with precise schemas | Consolidated multi-fact summaries pass the eligibility gate at equal rank to precise explicit memories. |

---

## Implementation Sequence

| Phase | Items | Effort | Risk |
|---|---|---|---|
| **Phase 0** — Regression harness (failing tests first) | P0 | Small | None |
| **Phase 1** — Low-risk quality fixes | P1 (dedup), P2 (procedural) | Small | Low |
| **Phase 2** — Retrieval trust fixes | P3 (scope), P4 (feedback) | Medium | Low-Medium |
| **Phase 3** — Context precision | P5 (broad summary) | Small-Medium | Low |
| **Phase 4** — Conservative supersession | P6 | Medium-Large | Medium |
| **Phase 5** — Full eval metrics | P0 expanded | Medium | None |

---

## P0 — Synthetic Regression Harness (Do First)

**New file: `tests/eval/test_synthetic_long_session.py`**

Phase 0 — write these as **currently-failing** tests before any fix:

```
test_strict_scope_excludes_other_project
test_wrong_feedback_removes_memory_from_top_3
test_new_fact_supersedes_old_fact
test_procedure_retrieved_by_goal_and_requirement
test_recall_dedupes_episode_texts
test_broad_summary_not_ranked_above_precise_fact
```

Phase 5 (after all fixes) — expand to full metrics:

```text
explicit_recall@k          — explicitly remembered facts in top-k
scope_precision@k          — project queries exclude other-project facts
profile_injection@k        — user profile memories in context brief
temporal_update_accuracy   — new fact supersedes old and ranks first
wrong_feedback_suppression — wrong-marked schema drops below top-3
procedural_recall@k        — seeded procedure surfaces for matching query
context_token_budget       — context brief within budget
duplicate_rate             — fraction of duplicate episode texts in recall
evidence_coverage          — evidence=True returns >0 raw events per schema
```

---

## P1 — Episode Deduplication

**Low-risk. Immediate quality win. Elevated from v1 P5.**

**`slowave/core/services/retrieval.py` — `recall()` method:**

Normalise more aggressively than v1 (strip date prefix AND role prefixes):

```python
def _normalize_episode_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"^\[\d{4}-\d{2}-\d{2}\]\s*", "", text)
    text = re.sub(r"^(remember|user|assistant|system|note):\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text
```

Deduplicate episodes:

```python
seen_norm: set[str] = set()
deduped: list[dict] = []
for ep in episode_dicts:
    key = _normalize_episode_text(ep.get("content_text", ""))
    if key and key not in seen_norm:
        seen_norm.add(key)
        deduped.append(ep)
episode_dicts = deduped
```

Also dedupe episodes against already-returned schemas (unless `evidence=True`):

```python
schema_texts = {_normalize_episode_text(s.content_text) for s in schemas}
episode_dicts = [
    ep for ep in episode_dicts
    if _normalize_episode_text(ep.get("content_text", "")) not in schema_texts
    or evidence
]
```

**New tests:**
```
test_explicit_remember_no_duplicate_episodes
test_episode_dedup_normalized_against_schemas
test_context_brief_has_no_duplicate_items
```

---

## P2 — Fix Procedural Memory Retrieval

### P2-A — User-seeded procedures default to `active`

**`slowave/mcp/server.py` and/or `slowave/core/engine.py` `remember_procedure` path:**
```python
status = kwargs.pop("status", "active")   # explicit user seed -> active
```

`promote_candidates_from_feedback()` retains `status="candidate"` unchanged.

Rationale: promotion ladder is for inferred habits, not user instructions.

### P2-B — Auto-trigger extraction

**`slowave/core/procedural.py` — `ProceduralMemoryStore.create()`:**

```python
if not trigger_pattern:
    auto_text = " ".join([goal or "", task_type or ""] + procedure_steps)
    trigger_pattern = _terms(auto_text)[:15]
    # Mark as auto-generated in situation_signature for debuggability
```

### P2-C — `include_candidates` default

Change `ProceduralMemoryConfig.include_candidates: bool = True` (from `False`). Safety net for legacy candidate procedures.

**New tests:**
```
test_explicit_seeded_procedure_retrieved_by_goal
test_procedure_retrieved_by_task_type_match
test_auto_trigger_extraction_from_goal_and_steps
```


---

## P3 — Strict Scope Mode

**Apply selectively by surface, not globally.**

### P3-A — MCP `activate` default (surface-level, not engine-level)

```python
# slowave/mcp/server.py — activate() handler:
def activate(scope: str | None = None, mode: str | None = None, ...):
    if mode is None and scope and scope.startswith("project:"):
        mode = "strict_scope"
    else:
        mode = mode or "default"
```

Surface defaults:

| Surface | Default mode |
|---|---|
| MCP `activate(scope="project:x")` | `strict_scope` |
| MCP `activate(scope="user:x")` | `default` |
| MCP `activate(scope=None)` | `default` |
| CLI `recall` | `default` |
| Engine `context_brief()` | `default` unless caller passes `mode=` |
| Dashboard / debug | `broad` or `debug` |

### P3-B — Eligibility gate in `context.py`

Add `"strict_scope"` to `MemoryCue.mode`. In `WorkingMemoryGate._eligible()`, after debug check:

```python
if cue.mode == "strict_scope" and cue.scope:
    layer = (schema.facets or {}).get("memory_layer")
    is_profile = layer == "profile"
    is_global = not schema.scope_id   # None or "" both treated as global
    is_same_scope = schema.scope_id == cue.scope
    if not (is_same_scope or is_global or is_profile):
        return False, "strict_scope_excluded"
```

Note: verify `normalize_scope()` is consistently applied on insert so `scope_id=""` and `scope_id=None` are both handled as global.

**New tests:**
```
test_strict_scope_excludes_other_project_facts
test_strict_scope_allows_global_scope_none_memories
test_strict_scope_allows_profile_memories
test_default_mode_allows_cross_scope_with_penalty
test_mcp_activate_project_scope_defaults_strict
```

---

## P4 — Wrong/Stale Feedback Suppression

**Nuanced policy table, not blunt delta increases.**

### Feedback semantics

| Feedback | Meaning |
|---|---|
| `wrong` | Memory content is factually bad |
| `irrelevant` | Bad for this query, not globally wrong |
| `stale` | May have been true before, now outdated |
| `wrong + failed` | Retrieval actively caused task failure |

### P4-A — `wrong + failed` → `status = needs_review`

**`slowave/core/services/feedback.py` — `retrieval_feedback()`:**

```python
if fb_label == "wrong" and outcome == "failure":
    for schema_id in wrong_ids:
        try:
            self.schemas.update_status(schema_id, "needs_review")
        except KeyError:
            pass
```

`_eligible()` already hard-blocks `status != active`, so suppression is immediate.

### P4-B — `needs_review` excluded from default recall (mode-gated)

**`slowave/core/services/retrieval.py` — `recall()` method:**

```python
if mode == "debug":
    recall_statuses = ("active", "needs_review", "superseded")
elif mode == "broad":
    recall_statuses = ("active", "needs_review")
else:  # default, strict_scope
    recall_statuses = ("active",)
```

Apply to both FAISS schema retrieval path and profile-layer injection query.

Score multiplier as belt-and-suspenders for any `needs_review` that slips through:

```python
for s in schemas_all:
    if s.needs_review:
        schema_scores[s.id] = schema_scores.get(s.id, 0.0) * 0.20
```

### P4-C — `wrong` (without failed) → flag + score multiplier (reversible)

Set `needs_review=True` (current behaviour) + score multiplier. Keep `status=active` so one-off mistakes are reversible.

### P4-D — `irrelevant` feedback: query-local only

Do **not** apply global salience damage. Current `-0.05` delta is acceptable. No change.

### P4-E — Revised delta values (moderate, not -0.50)

```python
wrong_salience_delta: float = -0.30    # was -0.25
wrong_confidence_delta: float = -0.40  # was -0.30
stale_salience_delta: float = -0.20    # was -0.15
stale_confidence_delta: float = -0.20  # was -0.15
irrelevant_salience_delta: float = -0.05  # unchanged
```

Full policy summary:

```text
wrong + outcome=failed  → status=needs_review, conf-=0.40, score×0.20 in recall
wrong + outcome!=failed → needs_review flag=True, conf-=0.40, score×0.20
stale                   → needs_review flag=True, conf-=0.20, sal-=0.20
irrelevant              → sal-=0.05 (query-local, no global damage)
```

**New tests:**
```
test_wrong_feedback_removes_memory_from_top_3
test_wrong_failed_combo_sets_status_needs_review
test_needs_review_excluded_from_default_recall
test_needs_review_visible_in_broad_mode
test_irrelevant_feedback_does_not_globally_damage_schema
test_stale_feedback_demotes_but_reversible
```


---

## P5 — Broad Session Summary Demotion

**Classify by provenance + structure, not sentence count alone.**

### P5-A — Tag at consolidation time by provenance

**`slowave/core/services/consolidation.py`:**

```python
def _classify_consolidated_schema(text: str, source: str) -> str:
    if source == "explicit_remember":
        return None  # explicit memories never reclassified
    sentence_count = len(re.findall(r"[.!?]", text))
    if sentence_count >= 3 or len(text) > 300:
        return "episodic_summary"  # excluded by default context gate
    return "fact"
```

### P5-B — Belt-and-suspenders gate for untagged legacy schemas

**`slowave/core/context.py` — `_eligible()`:**

```python
schema_class = _lower(facets.get("schema_class"))
source_kind = _source_kind(facets)
if schema_class != "episodic_summary" and source_kind != "explicit_remember":
    text = schema.content_text or ""
    if len(re.findall(r'[.!?]', text)) >= 3 and len(text) > 300:
        if cue.mode not in {"broad", "debug"}:
            return False, "multi_sentence_summary"
```

**New tests:**
```
test_consolidated_broad_summary_excluded_from_default_context
test_explicit_long_memory_not_filtered
test_consolidated_short_schema_not_excluded
test_episodic_summary_visible_in_broad_mode
```


---

## P6 — Conservative Deterministic Supersession

**Most complex. Strong patterns only. No `X uses Y` or `X is Y`.**

### P6-A — New file: `slowave/core/supersession.py`

```python
"""Deterministic supersession. No LLM. Strong patterns only.
Runs only for explicit remember() calls, not consolidated schemas.
"""
from dataclasses import dataclass

STRONG_SUPERSESSION_PATTERNS = [
    r"(?P<subject>.+?)\s+(?:now uses|is now|has moved to)\s+(?P<new_value>.+)",
    r"(?P<subject>.+?)\s+(?:switched from)\s+(?P<old_value>.+?)\s+to\s+(?P<new_value>.+)",
    r"(?P<subject>.+?)\s+(?:replaced)\s+(?P<old_value>.+?)\s+with\s+(?P<new_value>.+)",
    r"(?P<subject>.+?)\s+(?:no longer uses|dropped)\s+(?P<old_value>.+)",
    r"Use\s+(?P<new_value>.+?)\s+instead of\s+(?P<old_value>.+)",
    r"Prefer\s+(?P<new_value>.+?)\s+over\s+(?P<old_value>.+)",
]
# Deferred (too broad): r"(?P<subject>.+?)\s+(?:uses|is)\s+(?P<new_value>.+)"

AUTO_SUPERSEDE_THRESHOLD = 0.85

@dataclass(frozen=True)
class SupersessionCandidate:
    old_schema_id: int
    confidence: float     # auto-supersede only if >= AUTO_SUPERSEDE_THRESHOLD
    reason: str
    old_subject: str
    new_subject: str
    old_value: str | None
    new_value: str | None
```

### P6-B — Integration in `IngestService.remember()`

```python
from slowave.core.supersession import find_superseded_candidates, AUTO_SUPERSEDE_THRESHOLD

# After creating new schema; guard: explicit_remember only:
if source_kind == "explicit_remember":
    for cand in find_superseded_candidates(content, scope_id, self.schemas):
        if cand.confidence >= AUTO_SUPERSEDE_THRESHOLD:
            self.schemas.update_status(cand.old_schema_id, "superseded")
            self.schemas.add_relation(cand.old_schema_id, new_schema_id, "supersedes")
        else:
            self.schemas.set_needs_review(cand.old_schema_id, True)
```

**New tests:**
```
test_new_fact_supersedes_old_fact_same_scope
test_superseded_fact_excluded_from_default_recall
test_supersession_pattern_now_uses
test_supersession_pattern_switched_from_to
test_supersession_pattern_no_longer_uses
test_supersession_pattern_prefer_over
test_unrelated_new_fact_does_not_supersede
test_weak_pattern_x_uses_y_not_applied_in_phase_1
test_below_threshold_sets_needs_review_not_superseded
test_supersession_blocked_across_scopes
```

---

## Resolved Design Questions

| Question | v2 Answer |
|---|---|
| Strict scope default | MCP `project:x` activation → `strict_scope`. Engine/CLI/dashboard → `default`. |
| Global memories in strict scope | `scope_id = None` AND `profile` layer memories both pass through. |
| Supersession aggressiveness | Conservative. Strong patterns only. Threshold 0.85. Weak patterns deferred. |
| Procedural status on creation | User-seeded → `active`. Auto-promoted from feedback → `candidate`. |
| Feedback weight for wrong | `wrong+failed` → `status=needs_review`. `wrong` alone → flag + score×0.20. Moderate deltas. |
| `irrelevant` feedback scope | Query-local only. No global schema damage. |
| Broad summary classification | Provenance (consolidation source) + sentence count. Explicit memories never filtered. |
| Episode dedup normalization | Date prefix + role prefixes stripped. Deduped against selected schemas too. |

---

## Files Modified Per Phase

| Phase | Files |
|---|---|
| P0 | `tests/eval/test_synthetic_long_session.py` (new) |
| P1 | `slowave/core/services/retrieval.py` |
| P2 | `slowave/mcp/server.py`, `slowave/core/procedural.py`, `slowave/core/engine.py` |
| P3 | `slowave/core/context.py`, `slowave/mcp/server.py` |
| P4 | `slowave/core/feedback.py`, `slowave/core/services/feedback.py`, `slowave/core/services/retrieval.py` |
| P5 | `slowave/core/services/consolidation.py`, `slowave/core/context.py` |
| P6 | `slowave/core/supersession.py` (new), `slowave/core/services/ingest.py` |

