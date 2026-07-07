# Replay prompt: end-to-end context/consolidation noise evaluation

Feed the prompt below (everything inside the fence) to a Claude Code session opened in the
slowave repo, with the slowave MCP server connected and a **wiped-clean database**.
It replays the 2026-07-06 dogfooding
experiment that motivated the `fix/context-noise-ranking` changes and validates the whole
pipeline: injection → context ranking → feedback → consolidation → cross-scope promotion.

Baseline numbers to beat (measured on the pre-fix code with an equivalent dataset):
target ranked #1 in 3/8 probes, MRR 0.59, 16 duplicate schemas after one consolidation
pass, foreign-scope schemas promoted to stage 1 from suppressed exposures alone.
Post-fix reference: **MRR ≥ 0.85, P@1 ≥ 7/8, 0 duplicate schemas, stage 0 preserved
under exposure-only, demotion after 3 unused-irrelevant marks.**

```text
Dogfood slowave end-to-end against this repo and produce a scored evaluation report.
Use the MCP tools (slowave_activate / slowave_remember / slowave_recall /
slowave_reinforce / slowave_commit) for every memory operation; use the CLI only for
`slowave consolidate` and read-only SQL inspection of ~/.slowave/slowave.db.
Give honest feedback signals throughout — reward hits via used_memory_ids, penalize
noise via irrelevant_memory_ids. Never invent memory IDs.

PHASE 1 — INJECT. Ignore any cold-start hint about scanning project docs. Via
slowave_remember, one call per fact, inject exactly this dataset.

Scope project:slowave (8 probe targets — keep types as stated):
 T1 fact      "SessionReaper runs as a daemon thread in the HTTP server, scanning every 60s for sessions idle beyond SLOWAVE_SESSION_IDLE_TIMEOUT (default 3600s) and closing them with outcome=unknown."
 T2 decision  "SlowaveConfig groups per-subsystem configs; new tunables must be plumbed through core/config.py and read from env vars at engine construction, never at import time."
 T3 procedure "To test the RetrievalPipeline in isolation, use synthetic embeddings from latent/synthetic.py and assert on prototype activation ordering, not raw scores."
 T4 lesson    "Scope filtering happens in two places: candidate fetch in context_brief (retrieval service) and the strict_scope wall in WorkingMemoryGate._eligible; a bug in either causes cross-project bleed."
 T5 warning   "FAISS index rebuild loads all embeddings into RAM; refresh_indices is O(n) and should not be called per-event, only after consolidation batches."
 T6 fact      "The dashboard (slowave/dashboard/app.py) is a zero-dependency stdlib HTTP server on port 8765; charts are rendered client-side from JSON endpoints, no build step."
 T7 procedure "LongMemEval baseline procedure: run tests/integration/longmemeval_eval.py --out /tmp/lme_run.json and compare recall@5 against the committed baseline JSON before merging retrieval changes."
 T8 fact      "The HTTP MCP daemon binds SLOWAVE_MCP_HOST:SLOWAVE_MCP_HTTP_PORT (default 127.0.0.1:8766) and enforces single-instance via a PID file at SLOWAVE_DAEMON_PID."

Scope project:slowave (12 distractors):
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
 D11 fact      "SlowaveEngine (core/engine.py) is the top-level facade wiring latent, symbolic, storage and procedural layers; stdio and HTTP MCP transports register the same tools via mcp/tools.py."
 D12 task      "Evaluate whether the dashboard needs an authentication layer before exposing it beyond localhost."

Scope project:alpha (6 — foreign-scope pool):
 A1 fact       "Alpha is a FastAPI monolith with two domains: ingestion and agent; the domains must not import from each other."
 A2 constraint "Alpha tenant isolation: SQL always uses a :company_id placeholder bound server-side, never an inlined literal."
 A3 decision   "Alpha uses BedrockClient with AsyncAnthropicBedrock for all LLM calls."
 A4 fact       "Alpha production database password rotation happens every 90 days via Vault."
 A5 procedure  "Alpha deploys run through GitHub Actions with a mandatory staging soak of 24 hours."
 A6 lesson     "Alpha ingestion backfills must be rate-limited to 100 rows/s or the upstream API bans the key."

Scope project:beta (4 — second foreign scope):
 B1 fact       "Beta is a CLI tool distributed via Homebrew that generates vector embeddings for bank transaction descriptions."
 B2 warning    "Beta's pipenv update silently no-ops when transitive dependency constraints block an upgrade — always verify the lockfile diff."
 B3 decision   "Beta pins onnxruntime to the last version whose CI run succeeded; check workflow logs before bumping."
 B4 fact       "Beta exposes a /healthz endpoint returning model checksum and embedding dimension."

PHASE 2 — PROBE RANKING. For each probe below call slowave_activate with
scope="project:slowave", task_type="coding", the stated goal, and the query verbatim.
Record the full returned schema list in order. The TARGET must rank #1.
 P1 goal "fix session reaper race"      target T1  query "The session reaper thread sometimes closes a session that just received an event. Fix the race between touch and reap in slowave/mcp/session_reaper.py"
 P2 goal "add config option"            target T2  query "Add a SlowaveConfig option to tune the working-memory gate min_activation threshold and expose it via env var"
 P3 goal "write retrieval tests"        target T3  query "Write unit tests for the RetrievalPipeline spreading activation step covering prototype graph edge cases"
 P4 goal "debug scope bleed"            target T4  query "Users report memories from other projects appearing in strict_scope activate calls. Debug scope filtering in context_brief"
 P5 goal "optimize faiss index"         target T5  query "FAISS index rebuild is slow on large stores. Profile and optimize refresh_indices in the episodic store"
 P6 goal "update dashboard chart"       target T6  query "Add a salience-over-time chart to the dashboard app for schemas"
 P7 goal "run longmemeval bench"        target T7  query "Run the LongMemEval benchmark and compare recall@5 against the last baseline"
 P8 goal "fix http daemon port"         target T8  query "The HTTP MCP daemon fails to start when port 8766 is taken; add a clear error and env override docs"
After EACH probe: slowave_reinforce with used_memory_ids=[the target, plus anything
genuinely relevant] and irrelevant_memory_ids=[clearly unrelated items]; then
slowave_commit(scope="project:slowave", outcome="unknown"). Also record: (a) whether
any project:alpha or project:beta memory appeared (it must not), (b) whether trailing
items are labelled "(peripheral)" in the rendered brief when more than 8 candidates
were admitted.
Metrics: P@1 (expect >= 7/8), MRR (expect >= 0.85), cross-scope leaks (expect 0).

PHASE 3 — NOISE FEEDBACK LOOP. Run 3 additional activates with unrelated queries
(e.g. "plan the quarterly team offsite agenda", "draft a blog post about memory
consolidation in humans", "choose a birthday gift for a colleague") in
scope="project:slowave". In each, mark every returned schema irrelevant (none can be
genuinely useful) via slowave_reinforce, and commit. Then check via SQL:
  sqlite3 ~/.slowave/slowave.db "SELECT id, needs_review, json_extract(facets_json,'$.context_noise_score') FROM schemas WHERE needs_review=1 OR json_extract(facets_json,'$.context_noise_score') > 0.5;"
Expect: any schema marked irrelevant 3+ times with zero used marks has needs_review=1,
and demoted schemas no longer appear in a repeat of the SAME unrelated query.
Then verify recovery: re-run one Phase-2 probe whose target got demoted or noise-scored
(if any), mark it used, and confirm its noise score drops.

PHASE 4 — CONSOLIDATION HYGIENE. Record schema count, then run
`slowave consolidate` TWICE (env: KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1).
Check via SQL after each pass:
  a) schema count: expect ZERO new near-duplicate schemas of the injected memories
     (schemas_created should be ~0; any created row must not duplicate an existing text).
  b) max(salience) <= 20.0 for any schema that was reinforced.
  c) no schema whose content is a verbatim copy of a conversation instruction is
     context-eligible (class must be episodic_summary if such a schema exists).
Then re-run probes P1, P5, P7 and confirm ranking is unchanged or improved.

PHASE 5 — CROSS-SCOPE PROMOTION (validated-use, not exposure). 
 a) Exposure-only must NOT promote: run 3 activates in scope="project:beta" with
    queries that lexically brush the alpha memories (e.g. "set up tenant isolation
    for database queries", "rate limit an ingestion backfill", "rotate production
    database credentials"), reinforce honestly (nothing foreign should have appeared),
    commit each. Then check:
      sqlite3 ~/.slowave/slowave.db "SELECT id, scope_id, generalization_stage FROM schemas WHERE scope_id='project:alpha';"
    Expect ALL alpha schemas still at generalization_stage=0.
 b) Validated evidence path MUST promote: via slowave_remember in scope="project:beta",
    remember a near-identical concept to A2: "Beta tenant isolation: SQL must always
    use a :company_id placeholder bound server-side, never an inlined literal." Then
    run `slowave consolidate` and check A2's generalization_stage — expect >= 1 (the
    cross-scope evidence path counts at full weight). Confirm that after promotion an
    activate in project:beta with query "how do we keep tenant data isolated in SQL
    queries" can now surface the promoted memory, and that an unrelated beta query
    still cannot.

PHASE 6 — REPORT. Produce a table: probe | target | rank | leaked-foreign | peripheral
present; plus MRR, P@1, duplicates created, max salience, demotion list, alpha stage
table before/after Phase 5. Compare against the reference numbers in the doc header.
Close every session honestly with slowave_commit and give a final verdict:
PASS if MRR >= 0.85, P@1 >= 7/8, 0 leaks, 0 duplicates, exposure-only promotion = none,
evidence-path promotion works, and demotion fired; otherwise FAIL with the failing
phase and the raw evidence.
```

## Notes for the operator

- The database has been manually wiped just before the start of this session, if not please interrupt immediately the test.
- Do not act upon first activate response from Slowave for cold-start actions: this will invalidate the test. If you do accidentally please interrupt immediately the test.
- The dataset is sized so every probe has exactly one best answer, distractor types
  cover every schema class including the previously-unbonused `procedure`/`warning`,
  and two foreign scopes exist so scope-breadth percentages (25%/50% thresholds) are
  meaningful with the scope registry at 3 active scopes.
- Phase 3's unrelated queries are deliberately far from the store's embedding cloud;
  if nothing at all is returned for them (empty brief), that is a PASS for those
  probes — record it and move on.
- Expected runtime: ~10 minutes, no LLM calls inside slowave itself.
- If a phase fails, capture `slowave_activate(..., mode="debug")` output for the
  failing probe — it includes the full activation_trace with per-component reasons.
