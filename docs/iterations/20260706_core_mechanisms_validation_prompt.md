# Replay prompt v2: core-mechanism validation (retrieval, promotion ladder, demotion, decay)

Supersedes `20260706_context_noise_replay_prompt.md` for full-mechanism validation.
Feed the fenced prompt to a Claude Code session in the slowave repo with the slowave
MCP connected and a **wiped-clean database**. The cold-start-ignore rule is inside the
prompt itself — the DB is wiped manually, and the agent must not seed it from docs.

## What v2 adds over v1

v1 validated ranking quality (MRR/P@1), cross-scope leak blocking, consolidation
hygiene, and promotion **stage 0 → 1 only** (evidence path). Stages 2 and 3 were
structurally unreachable: with only 3 active scopes the `min_distinct_scopes` floors
(4 for stage 2, 8 for stage 3) can never be met. v2 adds:

- a 9-scope registry so the full ladder 0→1→2→3 is arithmetically reachable
- retrieval validation via `slowave_recall` (not just activate/context)
- an engineered `needs_review` demotion (v1's dataset was too sparse to trigger it)
- salience decay via sanctioned backdating (the same trick the unit tests use)
- negative controls: a never-shared memory must stay stage 0; exposure-only must not promote
- validation of the `kind_bonus` session-floor softener (Step E)

## Current promotion thresholds (GeneralizationConfig defaults)

| Stage | scope_breadth_pct | min_distinct_scopes | min_distinct_sessions | kind_bonus available |
|-------|------------------|---------------------|-----------------------|----------------------|
| 1     | ≥ 0.25           | ≥ 2                 | ≥ 2                   | no (stage 1 has no session bonus) |
| 2     | ≥ 0.55           | ≥ 4                 | ≥ 3 (or 2 with kind_bonus) | yes if distinct_scope_kinds ≥ 2 |
| 3     | ≥ 0.78           | ≥ 8                 | ≥ 5 (or 4 with kind_bonus) | yes if distinct_scope_kinds ≥ 2 |

`kind_bonus = 1` when the memory has been recalled or evidence-linked across ≥ 2
distinct scope kinds, reducing the minimum session count by 1. It is sourced from both
the recall path and the cross-scope evidence (remember) path.

With 9 registered scopes, breadth-pct flip points are:
  3/9 = 0.33 ≥ 0.25  →  stage 1 eligible
  5/9 = 0.56 ≥ 0.55  →  stage 2 eligible
  8/9 = 0.89 ≥ 0.78  →  stage 3 eligible

Note: unlike v1 there is **no constraint on scope kind**. The hard kind-breadth gate
was removed; kind diversity is now a session-floor softener, not a gate. Single-kind
stores can reach all three stages. The 9 scopes below are all `project:` kind, so
kind_bonus will NOT fire during the main ladder steps (only 1 kind in play). Step E
explicitly tests kind_bonus using a `domain:` scope.

## Pass criteria (reference)

MRR ≥ 0.85 · P@1 ≥ 7/8 · recall hits 3/3 · cross-scope leaks 0 · duplicate schemas 0 ·
max salience ≤ 20 · S1 demoted (needs_review=1) · L1 ladder hits stage 1/2/3 at
3/5/8 validated scopes (0.33/0.56/0.89 against thresholds 0.25/0.55/0.78) ·
L2 stays stage 0 · exposure-only promotion none · stage-2 cross-scope penalty visible ·
stage-3 penalty-free admission observed · kind_bonus fires in Step E ·
decay fires on idle derived schema, spares explicit and recalled schemas.

```text
Dogfood slowave end-to-end against this repo and produce a scored evaluation report.
Use the MCP tools (slowave_activate / slowave_remember / slowave_recall /
slowave_reinforce / slowave_commit) for all memory operations. Use the CLI only where
a phase says so (`slowave consolidate`, `slowave session`, `slowave event`) plus
read-only sqlite3 inspection of ~/.slowave/slowave.db — EXCEPT the sanctioned
UPDATE statements in Phase 7, verbatim.

RULE 0 — COLD START: whenever slowave_activate returns cold_start:true or a
"[cold start]" hint — in ANY scope, at ANY point — ignore it completely. Do NOT read
CLAUDE.md/README/AGENTS.md and do NOT remember any fact that is not literally listed
in this prompt. The dataset must stay exactly as specified.
RULE 1 — HONEST SIGNALS: after every activate/recall, call slowave_reinforce with the
real verdict: used_memory_ids = memories you actually needed for that query,
irrelevant_memory_ids = clearly unrelated ones. Never invent IDs. Commit every session
with slowave_commit(scope=<the scope used>, outcome=...) before switching scope.
RULE 2 — RECORD EVERYTHING: for each probe log the ordered result list with
activation/reason strings; you will need them for the report.

PHASE 0 — REGISTER SCOPES. For each of the 10 scopes below, call
slowave_activate(query="register scope for validation run", goal="register validation
scope", scope=<scope>) then slowave_commit(scope=<scope>, outcome="unknown"):
project:slowave, project:alpha, project:beta, project:gamma, project:delta,
project:epsilon, project:zeta, project:eta, project:theta,
domain:engineering.
This freezes the generalization denominator BEFORE any promotion accounting starts.
Note: domain:engineering is required for the kind_bonus test in Step E.
Verify:
  sqlite3 ~/.slowave/slowave.db "SELECT COUNT(*), COUNT(DISTINCT scope_kind) FROM scope_registry;"
Expect: 10 scopes, 2 scope kinds.
With 10 scopes: stage flip counts are still 3/6/8 validated scopes (0.30/0.60/0.80
against thresholds 0.25/0.55/0.78 — 6 scopes gives 0.60 ≥ 0.55, 8 gives 0.80 ≥ 0.78).

PHASE 1 — INJECT. Via slowave_remember, one call per fact, exact types and scopes.

project:slowave — probe targets:
 T1 fact      "SessionReaper runs as a daemon thread in the HTTP server, scanning every 60s for sessions idle beyond SLOWAVE_SESSION_IDLE_TIMEOUT (default 3600s) and closing them with outcome=unknown."
 T2 decision  "SlowaveConfig groups per-subsystem configs; new tunables must be plumbed through core/config.py and read from env vars at engine construction, never at import time."
 T3 procedure "To test the RetrievalPipeline in isolation, use synthetic embeddings from latent/synthetic.py and assert on prototype activation ordering, not raw scores."
 T4 lesson    "Scope filtering happens in two places: candidate fetch in context_brief (retrieval service) and the strict_scope wall in WorkingMemoryGate._eligible; a bug in either causes cross-project bleed."
 T5 warning   "FAISS index rebuild loads all embeddings into RAM; refresh_indices is O(n) and should not be called per-event, only after consolidation batches."
 T6 fact      "The dashboard (slowave/dashboard/app.py) is a zero-dependency stdlib HTTP server on port 8765; charts are rendered client-side from JSON endpoints, no build step."
 T7 procedure "LongMemEval baseline procedure: run tests/integration/longmemeval_eval.py --out /tmp/lme_run.json and compare recall@5 against the committed baseline JSON before merging retrieval changes."
 T8 fact      "The HTTP MCP daemon binds SLOWAVE_MCP_HOST:SLOWAVE_MCP_HTTP_PORT (default 127.0.0.1:8766) and enforces single-instance via a PID file at SLOWAVE_DAEMON_PID."

project:slowave — distractors:
 D1 preference "Matteo prefers black with line-length 100 and isort profile black for all Python formatting in slowave."
 D2 constraint "The LLM is output-only in slowave; consolidation must never route through an LLM call — memory operations are pure geometry over embeddings."
 D3 fact       "TextEncoder wraps sentence-transformers all-MiniLM-L6-v2 with dim=384 and is lazy-loaded to keep import time low."
 D4 decision   "Compact MCP responses target 150-200 tokens via CompactSchema (mcp/compact.py) to keep context injection cheap."
 D5 fact       "SemanticStore keeps prototypes at two thresholds: fine 0.85 (CA3-like) and coarse 0.55 (CA1-like); agreement between scales is a confidence signal."
 D6 warning    "On macOS, faiss and ONNX both bundle libomp; set KMP_DUPLICATE_LIB_OK=TRUE or imports segfault."
 D7 decision   "Release flow uses release-please on main with a Homebrew formula bump commit after each tagged release."
 D8 fact       "The TransitionModel is a graph successor-representation model over prototypes, trained by Hebbian co-occurrence during replay; it also produces the prediction-error surprise signal."
 D9 constraint "Every test is auto-isolated via the SLOWAVE_DB env var set in conftest.py; integration benchmarks require external datasets and are skipped in clean checkouts."
 D10 procedure "Development uses uv as the package manager: uv sync to install, uv run pytest to test, uv run slowave doctor to check daemon health."

project:slowave — special roles:
 L1 lesson (PROMOTION LADDER) "API retry loops must use exponential backoff with jitter, starting at 2 seconds and capping at 60 seconds, to avoid thundering-herd retry storms."
 L2 lesson (STAGE-0 CONTROL)  "Database connection pools should be sized to roughly twice the CPU core count and always verified under load before release."
 S1 fact  (DEMOTION TARGET)   "The team retrospective happens every second Friday and alternates between an online call and the office meeting room."

project:alpha:
 A1 fact       "Alpha is a FastAPI monolith with two domains: ingestion and agent; the domains must not import from each other."
 A2 constraint "Alpha tenant isolation: SQL always uses a :company_id placeholder bound server-side, never an inlined literal."
 A3 decision   "Alpha uses BedrockClient with AsyncAnthropicBedrock for all LLM calls."
 A4 fact       "Alpha production database password rotation happens every 90 days via Vault."

project:beta:
 B1 fact       "Beta is a CLI tool distributed via Homebrew that generates vector embeddings for bank transaction descriptions."
 B2 warning    "Beta's pipenv update silently no-ops when transitive dependency constraints block an upgrade — always verify the lockfile diff."

Record the sch_ id assigned to L1, L2, S1 (from an SQL lookup on content) — later
phases reference them.

PHASE 2 — CONTEXT RANKING. For each probe call slowave_activate with
scope="project:slowave", task_type="coding", the stated goal and verbatim query; the
TARGET must rank #1. Reinforce honestly and commit after each.
 P1 goal "fix session reaper race"    target T1  query "The session reaper thread sometimes closes a session that just received an event. Fix the race between touch and reap in slowave/mcp/session_reaper.py"
 P2 goal "add config option"          target T2  query "Add a SlowaveConfig option to tune the working-memory gate min_activation threshold and expose it via env var"
 P3 goal "write retrieval tests"      target T3  query "Write unit tests for the RetrievalPipeline spreading activation step covering prototype graph edge cases"
 P4 goal "debug scope bleed"          target T4  query "Users report memories from other projects appearing in strict_scope activate calls. Debug scope filtering in context_brief"
 P5 goal "optimize faiss index"       target T5  query "FAISS index rebuild is slow on large stores. Profile and optimize refresh_indices in the episodic store"
 P6 goal "update dashboard chart"     target T6  query "Add a salience-over-time chart to the dashboard app for schemas"
 P7 goal "run longmemeval bench"      target T7  query "Run the LongMemEval benchmark and compare recall@5 against the last baseline"
 P8 goal "fix http daemon port"       target T8  query "The HTTP MCP daemon fails to start when port 8766 is taken; add a clear error and env override docs"
Metrics: P@1 (>= 7/8), MRR (>= 0.85), foreign-scope leaks (0), "(peripheral)" labels
present in the rendered brief whenever more than 8 candidates were admitted.

PHASE 3 — RECALL. Validate slowave_recall independently of activate. Reinforce each
recall's retrieval_id honestly.
 R1 scope="project:slowave" query "how is the HTTP daemon port configured"
    -> T8 in top 3.
 R2 scope="project:slowave" query "background thread that closes inactive sessions"
    -> T1 in top 3 (paraphrase, near-zero lexical overlap — embedding path).
 R3 scope="project:beta" query "tenant isolation SQL placeholder company id"
    -> A2 (stage 0, foreign) must NOT appear.
Expect 3/3.

PHASE 4 — ENGINEERED DEMOTION. Three activates in scope="project:slowave", queries
chosen to semantically attract S1 while S1 is genuinely useless for them:
 N1 "schedule a meeting with the design team next Friday"
 N2 "when is the next team retrospective happening and who facilitates it"
 N3 "plan the sprint review calendar for this quarter"
In each: if S1 appears, mark it in irrelevant_memory_ids (never used); reinforce,
commit. S1 must appear in at least 3 of them for the gate to arm — if it misses one,
add a fourth query in the same family. Then:
  sqlite3 ~/.slowave/slowave.db "SELECT needs_review, json_extract(facets_json,'$.context_noise_score') FROM schemas WHERE id = <S1>;"
Expect needs_review=1 and noise >= 0.75. Re-run N2 and confirm S1 is absent from the
default-mode brief. Other probe targets (T1-T8) must still be active (not demoted) —
they carry used marks.

PHASE 5 — CONSOLIDATION HYGIENE. Record schema count; run `slowave consolidate`
twice (env KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1). Expect: no new schema whose
text duplicates or concatenates injected memories (remember-only episodes are skipped
entirely); any schema formed from activate-session episodes must be class
episodic_summary; max(salience) <= 20. Re-run P1, P5, P7 — targets still #1.

PHASE 6 — PROMOTION LADDER (the core of v2). L1's origin schema is in
project:slowave. The ladder validates that scope breadth drives promotion and that
kind diversity (kind_bonus) softens the session floor but does not block promotion.
After every step: run `slowave consolidate`, then check:
  sqlite3 ~/.slowave/slowave.db "SELECT id, generalization_stage,
    json_extract(facets_json,'$.distinct_scope_count'),
    json_extract(facets_json,'$.distinct_session_count'),
    json_extract(facets_json,'$.distinct_scope_kind_count'),
    json_extract(facets_json,'$.scope_breadth_pct')
  FROM schemas WHERE id IN (<L1>, <L2>);"

 Step A (evidence path -> stage 1). In project:gamma then project:delta: activate
 (query "how should API retries be implemented for flaky upstream services", goal
 "implement api retry logic"), then slowave_remember the near-identical claim —
 IMPORTANT: keep wording verbatim (the cross-scope evidence link requires >=0.78
 cosine): "API retry loops must use exponential backoff with jitter, starting at 2
 seconds and capping at 60 seconds, to avoid thundering-herd retry storms."
 (type lesson, scope = that project). Reinforce, commit. Consolidate.
 All scopes are project: so kind_bonus=0; stage 1 has no session bonus anyway.
 EXPECT: L1 stage 1 (3 validated scopes: slowave evidence=1.0, gamma=1.0, delta=1.0;
 3/10=0.30 >= 0.25; distinct_scopes >= 2; sessions >= 2). L2 stage 0.

 Step B (validated recall use — stage 1 admission cross-scope). In project:epsilon
 (L1 was never remembered here): activate "implementing retry logic for the payments
 API - what backoff strategy should we use", goal "add payment retry backoff".
 L1-origin is now stage 1 and project: kind, so it should be ADMITTED in
 project:epsilon (also project: kind). Record its activation and reason — expect
 "scope_mismatch" token (stage-1 cross-scope admission still applies a penalty).
 Mark the ORIGIN sch_ id in used_memory_ids (epsilon now counts 1.0 validated use).
 Commit. Do NOT consolidate here — consolidation happens in Step C.
 EXPECT: L1 surfaced; if it did not, run mode="debug" and report the activation trace.

 Step C (-> stage 2, single-kind path). Remember the L1 claim (verbatim) in
 project:zeta (activate, remember, reinforce, commit). Consolidate.
 All scopes still project: only, so kind_bonus=0 and session floor stays at 3.
 EXPECT: L1 stage 2 (6 validated scopes: slowave, gamma, delta, epsilon, zeta + one
 of the earlier remembers; 6/10=0.60 >= 0.55; distinct_scopes >= 4; sessions >= 3).
 Verify stage-2 behavior in project:eta:
   - Activate "choose a retry backoff strategy for the ingestion worker" ->
     L1 admitted with reason containing "scope_mismatch:stage2".
   - Activate "pick a color palette for the marketing site" ->
     L1 absent (cross-scope relevance floor blocks low-cosine cross-scope items).
 Reinforce honestly (used in the first, nothing in second), commit both.

 Step D (-> stage 3, single-kind path). Remember the L1 claim (verbatim) in
 project:eta, project:theta, and project:alpha (activate, remember, reinforce,
 commit in each). Consolidate.
 All scopes still project: only, kind_bonus=0, session floor stays at 5.
 EXPECT: L1 stage 3 (>= 8 validated scopes; 8/10=0.80 >= 0.78; distinct_scopes >= 8;
 sessions >= 5). L2 still stage 0.

 Step E (kind_bonus test + global behavior). This step uses domain:engineering
 to test kind_bonus and also verifies stage-3 global admission.

   E1 — Global admission. In project:beta (the only project: scope with no L1
   history): activate "what retry strategy should the embedding batch job use when
   the bank API rate-limits us" -> L1 admitted with NO scope_mismatch token (stage 3
   is globally admitted without penalty). Reinforce (used), commit.

   E2 — Negative control. Activate "rotate production database credentials" in
   project:beta -> A4 (project:alpha, stage 0) must NOT appear. Check A4 stage = 0.
   Reinforce (nothing used), commit.

   E3 — kind_bonus. In domain:engineering: activate "what is the right retry strategy
   for flaky microservice calls in our platform", goal "design retry strategy",
   scope="domain:engineering". L1 is stage 3 and must appear without scope_mismatch.
   Mark L1 in used_memory_ids, reinforce, commit. Consolidate. Check:
     sqlite3 ~/.slowave/slowave.db "SELECT
       json_extract(facets_json,'$.distinct_scope_kind_count'),
       json_extract(facets_json,'$.distinct_session_count')
     FROM schemas WHERE id = <L1>;"
   Now distinct_scope_kind_count should be 2 (project + domain). That means
   kind_bonus=1 in compute_stage. Verify by constructing a hypothetical: if L1 were
   only at stage 2 with 4 sessions, kind_bonus would let it clear the 5-session floor.
   Report: distinct_scope_kind_count, kind_bonus eligibility (>= 2 kinds? yes/no).

PHASE 7 — DECAY. Decay only touches consolidation-derived schemas that were never
recalled (explicit_remember schemas and recurrence_count>0 schemas are exempt).
Build a derivable schema:
  slowave session start --scope project:slowave --agent decay-test   # prints <session_id>
  slowave event --session <session_id> --type user_message --content "The legacy build rack in the basement uses purple cable ties to mark decommissioned machines."
  slowave event --session <session_id> --type user_message --content "Purple cable ties on the basement rack mean the machine is decommissioned and safe to unplug."
  slowave event --session <session_id> --type user_message --content "Facilities asked us to keep using purple ties for decommissioned basement machines."
  slowave session end <session_id>
Run `slowave consolidate`; find the derived schema id by content ("purple cable ties").
Run EXACTLY these three sanctioned updates (test-harness backdating, same technique as
tests/unit/test_schema_utility.py):
  sqlite3 ~/.slowave/slowave.db "UPDATE schemas SET first_formed_ts = strftime('%s','now') - 40*86400, salience = 0.40 WHERE id = <derived>;"
  sqlite3 ~/.slowave/slowave.db "UPDATE schemas SET first_formed_ts = strftime('%s','now') - 40*86400 WHERE id = <D7>;"
  sqlite3 ~/.slowave/slowave.db "UPDATE schemas SET first_formed_ts = strftime('%s','now') - 40*86400 WHERE id = <T1>;"
Run `slowave consolidate` once more, then check all three:
  EXPECT derived: salience dropped by ~0.15 (to ~0.25) AND needs_review=1 (below the
         0.30 review threshold).
  EXPECT D7 (explicit_remember): salience unchanged — explicit memories never decay.
  EXPECT T1 (recalled and used in Phase 2): salience unchanged — recalled schemas
         never decay.

PHASE 8 — REPORT. Write your findings to a new file at:
  docs/iterations/20260706_core_mechanisms_validation_results.md
Use this structure:
  # Core-mechanism validation results
  **Date:** <today>  **Branch:** fix/context-noise-ranking  **Verdict:** PASS|FAIL
  ## Summary table
  | Phase | Criterion | Expected | Observed | Status |
  ## Phase 2 — Context ranking  (MRR, P@1, per-probe rank table)
  ## Phase 3 — Recall  (R1/R2/R3 hit/miss)
  ## Phase 4 — Demotion  (S1 noise score, needs_review, suppression confirmed)
  ## Phase 5 — Consolidation  (schema count before/after, max salience)
  ## Phase 6 — Promotion ladder
    Ladder trace table: step | consolidate # | L1 stage | distinct_scopes |
    distinct_sessions | distinct_scope_kinds | scope_breadth_pct
    Stage-2 penalty token observed (yes/no + raw reason string)
    Stage-3 penalty-free admission observed (yes/no + raw reason string)
    kind_bonus eligibility after E3 (distinct_scope_kind_count, fires yes/no)
  ## Phase 7 — Decay  (derived salience before/after, D7 unchanged, T1 unchanged)
  ## Verdict  PASS if every expectation holds; FAIL with phase, evidence, numbers.

Then output the same content as your final reply.
```

## Notes for the operator

- Runtime ~25–30 minutes; ~50 remember calls, ~35 activates, 10+ consolidate passes.
- The ladder arithmetic above assumes 10 registered scopes. If extra scopes get
  registered mid-run the breadth denominators shift — the report should recompute
  expected flip counts from the actual `scope_registry` count.
- With 10 scopes and thresholds 0.25/0.55/0.78 the flip counts are 3/6/8, not 3/5/8.
  Step C now requires 6 validated scopes (not 5) to reach stage 2.
- Phase 7's UPDATEs are the only sanctioned writes outside MCP/CLI.
- If Step B fails admission, likely causes: cosine below the 0.25 cross-scope gate
  for that query phrasing (try an alternate phrasing), or Stage A flip didn't happen
  (check SQL trace first: distinct_scopes=3 and scope_breadth=0.30 must both be true).
- kind_bonus does NOT fire during Steps A–D because all scopes there are project:
  kind — distinct_scope_kind_count stays at 1 throughout. It only fires after Step E3
  when domain:engineering adds a second kind. This is by design: it confirms kind
  breadth is not required for promotion (stage 3 reached without it) and then shows
  the bonus fires once a second kind is observed.
