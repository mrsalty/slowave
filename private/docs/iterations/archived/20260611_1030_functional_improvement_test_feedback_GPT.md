Yes. I re-ran the same synthetic evaluation against the updated slowave.zip.

Full JSON report:

Download updated synthetic evaluation report⁠￼

Important caveat

The new zip only contains the slowave/ package. It does not include:

pyproject.toml
tests/
README.md
docs/

So I could not re-run the original pytest suite from the repo. I did run the same synthetic functional test harness locally against the updated package.

Also, the zip still contains release debris:

__MACOSX/
__pycache__/
*.pyc

and slowave/__init__.py still reports:

__version__ = "0.1.18"

⸻

Synthetic test result

Previous run:

7 / 7 basic recall checks passed

Updated run:

6 / 7 basic recall checks passed

The failed check was:

What database does Slowave use?

Reason: the answer did retrieve the expected Slowave SQLite fact, but it also retrieved the forbidden unrelated Payments/PostgreSQL fact, so the scope-leakage-sensitive check failed.

However, the more important scope result is positive: strict scope now works in context_brief().

⸻

What improved

1. Strict scope mode works

This is the best improvement.

For:

context_brief(
    query="Payments database queues",
    scope="project:payments",
    mode="strict_scope"
)

Returned items were:

The Payments project uses RabbitMQ queues for enrichment requests.
Payments project stores bookkeeping data in PostgreSQL.
User prefers concise direct answers with concrete code-level actions.

It correctly excluded the Slowave SQLite memory.

In default and broad mode, the Slowave SQLite memory still appeared, as expected.

Verdict:

P1 strict scope: mostly fixed for context brief.

One limitation: engine.recall() does not expose mode, so plain recall can still mix scopes.

⸻

2. Supersession improved, but is too aggressive

After adding:

Slowave primary database has moved to DuckDB for local storage.

the old SQLite memory was marked:

status = superseded
salience = 0.05

That is a real improvement over the previous run.

But the supersession logic also marked unrelated Slowave memories as superseded:

Slowave uses FAISS for local vector retrieval.
Slowave must not call an LLM during ingest, consolidation, or recall.
We reviewed slowave setup and decided dry-run must show exact modified files.

That is too aggressive.

Root cause: the pattern extractor treats the subject as broadly as "Slowave primary database" / first-word matching, and the fallback geometric supersession path also seems to supersede semantically nearby Slowave memories.

Verdict:

P3 supersession: partially fixed, but currently unsafe.

Suggested fix: disable or tighten the geometric fallback in remember() and make pattern supersession require stronger subject/value alignment.

⸻

3. Episode deduplication improved

The updated run returned:

episode_count = 3
unique_norm_count = 3

So episode-to-episode duplication is improved.

However, there is still schema/episode overlap:

schema: Slowave uses FAISS for local vector retrieval.
episode: [2026-06-11] Remember: Slowave uses FAISS for local vector retrieval.

So deduplication works inside the episode list, but not yet fully across schemas and episodes.

Verdict:

P5 episode dedup: partially fixed.

⸻

4. needs_review / default recall filtering looks improved

The retrieval code now filters statuses by mode:

default/strict_scope -> active only
broad -> active + needs_review
debug -> active + needs_review + superseded

That is the right direction.

Verdict:

P2 status gating: improved.

⸻

What is still broken

1. Procedural retrieval still fails

The procedure was created successfully:

procedures = 1
status = active
confidence = 0.85

Auto-trigger extraction also worked:

prepare, slowave, public, release, release_review, remove, generated, artifacts, ...

But retrieval returned:

retrieved_count = 0

I ran debug retrieval and found the score:

score = 0.6478
threshold = 0.65

So it misses by a tiny margin.

This is actually good news: the active-status issue is fixed, but the score threshold is still too brittle.

Recommended fix:

min_procedure_score: float = 0.60

or reduce the requirement mismatch penalty when at least one requirement matches.

Current problem:

requirements requested: ["clean repo"]
procedure requirements: ["clean repo", "run tests"]
requirements_match = 0.50
requirement_mismatch = 0.50

That penalizes a partial requirement query too hard. Querying with a subset of procedure requirements should not be treated as a mismatch.

Verdict:

P4 procedural memory: partially fixed, retrieval still fails due to threshold/penalty.

⸻

2. Wrong feedback did not fully behave as planned

I passed:

feedback="wrong"
outcome="failed"

The returned result normalized outcome to:

outcome = "unknown"

So the wrong + failed escalation path did not trigger.

The memory was marked review:

marked_review = ["sch_1"]

but because it was already superseded, the more important test was inconclusive.

Likely issue: code expects:

outcome = "failure"

not:

outcome = "failed"

The plan used both terms inconsistently.

Recommended fix: normalize aliases.

if outcome in {"failed", "failure", "fail", "task_failed"}:
    outcome = "failure"

Verdict:

P2 feedback suppression: partially fixed, but outcome aliasing bug remains.

⸻

3. Plain recall still has scope leakage

The basic recall check:

What database does Slowave use?

returned both:

Slowave primary database is SQLite, not Postgres.
Payments project stores bookkeeping data in PostgreSQL.

This caused the only failed baseline recall check.

This is less severe than context leakage because coding-agent injection usually goes through context_brief(), but it still matters.

Recommended fix: expose mode/scope in engine-level recall:

def recall(
    self,
    query: str,
    *,
    scope: str | None = None,
    mode: str = "default",
    top_k: int = 5,
    evidence: bool = False,
)

Then MCP/CLI can use:

mode = strict_scope
scope = project:x

Verdict:

P1 strict scope: fixed for context_brief, not for recall.

⸻

4. Broad consolidated summaries still compete

The run still returned broad consolidated schemas like:

We found pyproject version is 0.4.9 while __init__ version was stale.
We agreed benchmark reproduction should produce summary.json and summary.md artifacts.

and:

We reviewed slowave setup...
We found pyproject version...
We agreed benchmark reproduction...
We discussed not exposing too much brain jargon...

They were active and ranked highly in recall.

So P6 either has not been implemented or is not active in this path.

Verdict:

P6 broad summary separation: not fixed yet.

⸻

Updated scorecard

Feature	Previous	Updated	Notes
Explicit remember/recall	8.5	8.0	Still works, but unsafe supersession harmed existing facts
Evidence traceability	8.0	8.0	Stable
Cross-session continuity	8.0	8.0	Stable
Working-memory context brief	8.0	8.5	Strict scope improves it
Scope handling	6.5	8.0	Fixed in context brief, not recall
Consolidation	6.5	6.5	Broad summaries still compete
Feedback learning	5.5	6.5	Better status machinery, but outcome alias bug
Contradiction / supersession	4.5	6.0	New fact wins, but supersession is over-aggressive
Procedural memory retrieval	4.5	6.5	Active + triggers fixed, threshold still blocks retrieval
Release readiness	6.0	6.5	Functional improvements, but zip hygiene still poor

Bottom line

The updated version is directionally better. The most meaningful improvement is strict-scope context gating, which directly helps the coding-agent use case.

But two issues should be fixed before considering this sprint done:

1. Supersession is too aggressive and incorrectly supersedes unrelated Slowave memories.
2. Procedural retrieval still misses by threshold/penalty despite active status and good trigger extraction.

The next two code changes I would make:

- Tighten/disable geometric supersession fallback in explicit remember().
- Lower procedural min score to 0.60 or remove penalty for subset requirement matches.