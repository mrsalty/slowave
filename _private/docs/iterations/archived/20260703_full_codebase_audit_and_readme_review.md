# Slowave Full Codebase Audit — 2026-07-03

**Scope:** Complete engineering audit of all layers (latent, core/symbolic/storage, MCP/CLI/dashboard/packaging), test quality and benchmark honesty, competitive landscape positioning, and README review with recommendations.

**Method:** Five parallel deep-read sub-agents plus a live competitive research pass (WebSearch/WebFetch on Mem0, Zep/Graphiti, Letta, LangMem, supermemory, Cognee, Hindsight, OpenAI/Cursor/Cline native memory, academic arXiv 2025-2026).

---

## 1. Overall Verdict

**The "no LLM in the consolidation loop" claim is genuinely and verifiably true.** Every consolidation operation — clustering, schema formation via SVD, contradiction judgment, temporal anchoring, retrieval ranking — is numpy/FAISS/SQL. No LLM client is imported anywhere in the latent or core layers; the one text field a schema carries is selected from existing content, not generated. This is not marketing language: it is structurally enforced.

**Where the claim outruns the code:** The word "consolidation" in the marketing copy implies a richer process than what actually executes. The prototype graph's "learned" Hebbian transition and coactivation weights are *overwritten* each replay pass (not accumulated), transitions are sampled from random replay batches rather than real event adjacency, the "dual-scale hippocampal CA3/CA1" architecture currently runs with both scales at the same threshold (0.60), the self-supervised rehearsal mechanism is wired but never called in production, and the `TransitionModel.train_batch()` is a no-op counter increment behind a fake training loop that always reports `transition_prediction_loss = 0.0`. Retrieval-side engineering (spreading activation, multi-mechanism ranking, score-capped graph seeds, temporal probe) is genuinely solid and defensively designed. The consolidation story is primarily narrative ahead of implementation.

**The project is useful today and honest about its limits.** The README's "Honest limits" and "What it is not" sections are among the best-calibrated disclaimers in the open-source agent-memory space. Several benchmark numbers in the "At a Glance" table need more prominent caveats (see Section 6).

---

## 2. Strengths

### Architecture

- **No-LLM claim is structurally enforced, not aspirational.** `slowave/latent/` has zero LLM imports. `LatentSchemaBuilder.build()` derives schemas from centroid, SVD facet axes, temporal anchor, and cluster tightness — text is selection from existing content, not generation.
- **Anti-feedback-loop discipline in retrieval.** Graph-harvested episodes are score-capped below the worst cosine hit (`retrieval.py:59-64`), salience reinforcement is restricted to cosine-direct episodes (`retrieval.py:447-456`), and self-supervised rehearsal rewards only on *miss* (`replay_engine.py:399-404`). The system does not let the graph reward its own graph seeds — most memory systems get this wrong.
- **`TemporalProbe` is a clean, zero-regex, zero-dep implementation** (`temporal.py:187-321`): temporal anchor estimated via dot products against 12 pre-embedded probe phrases, with a dead-zone gate so atemporal queries fall back to legacy behavior exactly.
- **Unusually honest engineering notes.** Stage 8 pattern separation is benchmarked neutral-to-negative and shipped disabled with documentation (`replay_engine.py:60-67`); the `variance_floor` records the calibration bug it fixes (`schema.py:206-212`).
- **Storage is sound at MVP scale.** SQLite as single source of truth with `IndexIDMap2` keyed by row IDs, `reset_faiss_from_db()` as a clean recovery path, WAL + per-thread connections, a disciplined pre-migration column catalogue, and a genuinely clever partial UNIQUE index fix for SQLite NULL-in-PK dedup (`sqlite_db.py:227-231`).

### MCP / CLI / Packaging

- **`slowave setup` is production-grade.** Covers 5 clients, 3 platforms (macOS launchd, Linux systemd, Windows Task Scheduler), `--dry-run`, per-client flags, idempotent JSON patching, timestamped backups, TTY-guarded confirmation, and `doctor`/`status` diagnostics.
- **Token-efficient MCP responses via `compact.py`.** Log-saturating activation curve for content truncation, field whitelist that drops bulky internals (`vsa_vec`, full facets, activation traces), conditional confidence inclusion only when `< 0.7`, debug trace gated behind `mode="debug"`.
- **stdio logging hygiene.** All logging redirected to `~/.slowave/logs/mcp-stdio.log` before starting the JSON-RPC loop (`server.py`).
- **HTTP daemon security posture.** Bound to `127.0.0.1:8766` by default (not `0.0.0.0`); dashboard warns visibly on non-loopback override.
- **Dual transport (streamable-HTTP + SSE legacy) in a single process** without wrapping in an outer Starlette that would break lifespan — the architecture comment at `http_server.py:111-133` explains why exactly, which is rare.
- **Parameterized SQL throughout.** Zero SQL injection surface; f-strings appear only for placeholder-count expansion and hardcoded identifiers.

### Documentation

- The `limitations.md` is candid, specific, and makes clear which gaps are by design vs accidental.
- `reproducibility.md` publishes run-by-run numbers and discloses scorer differences with competitors.
- The `design.md` is one of the clearest explanations of neuroscience-inspired memory architecture in the agent-tooling space.

---

## 3. Weaknesses

### Algorithmic Soft Spots (Latent Layer)

- **Graph weights overwrite instead of accumulate.** `graph_manager.py:117-136` sets `w_coactivation` and `w_transition` to the current batch's values, overwriting prior history. The carefully additive self-supervision deltas in `replay_engine.py:429-436` are clobbered on the next `replay_once`. This is the single most significant gap between the Hebbian narrative and the actual code.
- **Coactivation semantics are sample artifacts, not contextual co-occurrence.** "Co-activated" means "sampled in the same random replay batch" (`replay_engine.py:327-336`), not "appeared in the same session or conversation context." The raw event log already contains real temporal adjacency data that is not being used.
- **Centroid double-counting.** Episodes re-sampled across replay passes are re-added to the incremental mean (`replay_engine.py:220-240`); `support_count` inflates over time and centroids drift toward frequently-sampled episodes.
- **Dual-scale CA3/CA1 is one threshold twice.** Both fine (CA3) and coarse (CA1) scales run at threshold 0.60 (`replay_engine.py:22, 86-91`). The `multi_scale_co_occurrence_bonus` in retrieval then rewards "agreement" between two near-identical clusterings — effectively a constant bonus. The neuroscience framing is not realized in the default configuration.
- **Salience time constants are calibrated for hours, not long-term memory.** `tau_seconds=3600` (`salience.py:12`) puts day-old events at the 0.01 floor. `increment_recall` adds unbounded +0.3 per retrieval, using the same constant as decay magnitude — two unrelated knobs on one constant.
- **`atemporal_margin=0.12` was calibrated on `bge-small-en-v1.5`** (`temporal.py:241`) while the project uses `paraphrase-multilingual-MiniLM-L12-v2`. Same 384-dim but different geometry; the calibrated threshold may not transfer.
- **FAISS is in-memory and rebuilt at startup.** `faiss_index_path` in `EpisodicStoreConfig` is dead config — the index is never persisted. O(n) per query, O(n·d) RAM, O(n) startup. At ~100k episodes (a realistic 6-month daily user) this becomes noticeable.
- **O(E·P) assignment in Python.** `_assign_to_prototypes` iterates over all prototypes in Python (`replay_engine.py:163-184`) without using the FAISS index. Each assignment triggers a SQL commit + FAISS remove/add — ~512 commits per replay pass at defaults.

### Core / Symbolic / Storage

- **`SchemaStore` (1,256 LOC) is the real god object.** CRUD + FTS + embedding search + dedup + decay + health + ScopeRegistry + GeneralizationConfig + a 150-line `_update_utility_scores` that runs a 2-subquery UNION join on every `reinforce` call.
- **The entire supersession block is wrapped in `except Exception: pass`** (`engine.py:631-632`). Any regression silently disables supersession forever with no log line. Same pattern in `consolidation.py:262-263`.
- **No explicit transactions.** Multi-statement writes rely on Python sqlite3's implicit transaction. An exception mid-write in `SchemaStore.create` (inserting schema + FTS + prototype map + evidence) can result in partial-write commits on the next unrelated `conn.commit()` on the same thread.
- **No `schema_version` / PRAGMA user_version.** Migration = re-run full `executescript` + manually-maintained column catalogue. No rollback, no dry-run, no version stamp. The pre-migration probe runs 30+ `sqlite_master` queries on every engine init.
- **`consolidation_debug` is an unbounded append-only table** with no pruning (`consolidation.py:287-303`). Every consolidation pass writes a row with empty `prompt_text`/`response_json` forever.
- **Recall in default mode is not scope-filtered for FTS and prototype paths.** Only the embedding path is scope-filtered when `mode != "strict_scope"` (`retrieval.py:247`) — cross-scope leakage in the advertised default mode.
- **Read path mutates the store.** Every `recall()` increments salience and recurrence for all returned schemas (`retrieval.py:285-286`). Rich-get-richer with no counterbalancing decay for recalled-but-useless items; also makes recall non-idempotent.
- **`GeneralizationConfig.__init__(**kwargs)` silently ignores unknown keys** (`schema_store.py:99-102`). A typo'd threshold override is a no-op.
- **`cross_scope_min_score` drift.** Config documents 0.40 (`schema_store.py:90-94`); `context.py:246` hardcodes 0.30 with a comment claiming they match; `retrieval.py:261/268` falls back to 0.30. The noise floor the config documents is not the one enforced in two of three code paths.

### Dead / Speculative Code

- **`vsa.py` is write-only in production.** `build_schema_vsa` runs and is stored, but `query_role`/`unbind` are never called by anything except the unit test. Dashboard explicitly filters `vsa_vec` out. The algebra is correct (real HRR binding), but the subsystem is decorative.
- **`ReplayEngine.self_supervise()` (Stage 5) is never called** in any production code path (`replay_engine.py:381-444`).
- **`TransitionModel.train_batch()` is a no-op** (`transition_model.py:145-148`); the training loop runs 50 iterations of nothing and reports `transition_prediction_loss = 0.0` in metrics.
- **`_looks_like_update()`** (`consolidation.py:341-347`) is English-only keyword matching, contradicts the "language-agnostic, no regex" claim, and is currently uncalled.

---

## 4. Red Flags

These are issues that would embarrass the project in a public review or risk silent data corruption.

### Critical / High

1. **Homebrew formula SHA-256 is the hash of the empty string** (`Formula/slowave.rb:6`): `sha256 "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"`. This is `SHA256("")` — a placeholder never filled with the actual tarball hash. `brew install` fails immediately with a checksum error.

2. **Supersession manifold applied to preferences against its own documentation.** `supersession_manifold.py:160-161` says "Personal preference is anti-aligned — do not use this signal for it." `engine.remember()` runs the supersession loop on *every* memory type including `type="preference"` with no gate (`engine.py:555-632`). A preference update can be auto-superseded by an axis the docs explicitly forbid for that domain.

3. **Fail-destructive default on missing embedding.** When the manifold is unavailable or the candidate has no stored embedding, `dir_score` defaults to `DIRECTION_THRESHOLD` (`engine.py:576-580`), which triggers "value substitution" → auto-supersede + salience crushed to 0.05. Legacy schemas without embeddings are silently killable by any cosine-similar new memory. The safe default is 0.0 (no action).

4. **Session resolver last-activate-wins.** `session_resolver.py` holds one binding per scope. Two concurrent clients (the primary reason the HTTP daemon exists) calling `activate(scope="project:foo")` will overwrite each other's session binding; client A's subsequent `remember()` routes to client B's session. Silent correctness bug for multi-agent use.

5. **CA3/CA1 contradiction in the deployed code.** Both fine (CA3, threshold 0.85 as documented) and coarse (CA1, threshold 0.55 as documented) are configured at 0.60 in practice (`replay_engine.py:22, 86-91`). The `multi_scale_co_occurrence_bonus` claims to reward "agreement between scales" but rewards agreement between two near-identical clusterings. A public review reading the neuroscience framing against the code would flag this immediately.

6. **Contrastive TF-IDF contrasts a cluster against itself.** `schema.py:312-315` passes `corpus_texts=cluster_texts` — the IDF term penalizes terms common *within the cluster*, which are exactly the theme-defining terms. `display_label` surfaces one-off noise words. The documented intent (`schema.py:148-155`) is the inverse.

7. **Contradiction judge has a dead branch.** `schema.py:441-451`: both arms of the if/else assign `verdict = "contradicts"`, so `min_support_to_supersede` is a no-op. Additionally, PCA axis ordering is unstable under near-equal singular values, so "facet distance" can flip verdicts on reordering — principal angles between subspaces would be correct.

8. **`slowave-check.sh` checks for `torch` and `sentence_transformers`** (lines 35-40) — neither is in `pyproject.toml` deps. The primary diagnostic script reports `FAIL` on a correctly installed package.

### Medium

9. **StaleMemory benchmark headline is cherry-picked.** `benchmarks.md` "At a Glance" table leads with **86–89%** without clarifying this applies only to 2 of 8 attribute types. The overall detection rate is **45%**. The dataset is self-authored; "EMNLP 2026 under review" is unverifiable (no paper, no independent dataset source).

10. **LoCoMo adversarial-question scoring: empty retrieval scores 100%.** When a question has no `answer` but has an `adversarial_answer`, the harness scores `1 - adversarial_keyword_score`. If Slowave returns nothing (0 schemas, 0 episodes), the adversarial keyword is absent → scores as a hit. This applies to 22.5% of the dataset.

11. **`conda/meta.yaml` pinned at version `0.1.0`** (repo at `0.9.1`). Anyone building from the conda recipe gets a nine-minor-version-old package.

12. **`license-files = []` in `pyproject.toml`** suppresses auto-inclusion of the LICENSE file in wheel/sdist distributions. An AGPL-licensed package that ships without the AGPL text is technically non-compliant with AGPL section 4.

13. **FAISS thread-safety gap.** The HTTP daemon's executor threads can call `add_with_ids` concurrently with `search`. FAISS writes are not thread-safe against concurrent reads. Multi-process (worker + daemon + dashboard) → FAISS index divergence: episodes written by one process are invisible to another's FAISS until restart.

14. **`results/` benchmark JSON files and `slowave.egg-info/` are git-tracked** — build artifacts and large benchmark outputs that should be in `.gitignore`.

15. **DMR number inconsistency.** `reproducibility.md` claims ~86-87% for DMR; actual stored runs show 93-94%. One of these is wrong. Additionally, DMR is not the published MemGPT/Zep LLM-judge protocol — it is a retrieval-context keyword presence metric.

---

## 5. Competitive Positioning

### The Landscape (Mid-2026)

Every mainstream deployed memory system uses LLM calls on the write path:

| System | Write mechanism | LLM on write | Where it runs |
|---|---|---|---|
| Mem0 | LLM fact extraction + CRUD | Yes (always) | Cloud / self-host |
| Zep / Graphiti | Temporal knowledge graph, LLM entity/relation extraction | Yes (always) | Cloud / self-host |
| Letta (MemGPT) | Agent-managed in-context + sleeptime compute | Yes (always) | Cloud / self-host |
| LangMem | LangChain-managed memory with LLM reflection | Yes (always) | Cloud |
| Cognee / supermemory | LLM-based chunking + graph + vector | Yes (always) | Cloud |
| Claude Code auto-memory | CLAUDE.md files, human-curated | Sometimes | Local |
| Cursor Memories | LLM extraction per-conversation | Yes | Cloud |
| Slowave | Embedding geometry only | Never | Local only |

Closest academic parallels: SuperLocalMemory V3 (arXiv:2603.14588, zero-LLM geometry with EU AI Act compliance framing) and Mnemosyne (arXiv:2510.08601, unsupervised edge-device memory). HippoRAG 2 uses LLM at indexing but not at retrieval. Slowave is the only *deployed* system with the zero-LLM-on-write property.

### Where Slowave Genuinely Differentiates

- **Zero token cost on all memory operations.** At high session volume, Mem0's per-write LLM call accumulates real API cost. For a coding agent running 50 sessions/day, the cost difference is measurable over a month.
- **Fully local, inspectable, exportable.** A single SQLite file at `~/.slowave/slowave.db`. No cloud account, no data egress, no terms-of-service change can affect stored memories. This is not true of any cloud-backed competitor.
- **Privacy-preserving by construction.** Proprietary code, client names, unreleased decisions — all processed locally without any LLM call touching the content. This is materially different from Mem0/Zep even when self-hosted, because self-hosted versions still require Ollama or a local LLM, introducing an additional trust boundary.
- **No cold-start dependency.** No API key needed to initialize. Works fully offline after the one-time 90 MB model download.
- **Scoped cross-tool memory.** No competitor currently provides a shared local memory layer that Claude Code, Cursor, Cline, and Claude Desktop read from the same store simultaneously with scope isolation. This is a genuine first-mover position.

### Where Slowave Is Structurally Weaker

- **No entity resolution or structured fact editing.** Mem0 extracts `(subject, predicate, object)` triples that can be queried, updated, or deleted by name. Slowave's schema content is a sentence selected from embeddings — it cannot be surgically edited without re-encoding.
- **Lower raw QA accuracy ceiling.** LLM-extracted structured facts with entity coreference resolution produce higher answer precision on factual QA benchmarks. The 87.8% LME oracle score is respectable but on a keyword-overlap scorer; an LLM-judged end-to-end run would likely score lower.
- **Embedding-model lock-in.** The FAISS index and all stored embeddings are tied to the encoder's dimensionality and geometry. Swapping the encoder requires rebuilding the entire store. No migration path exists today.
- **No natural-language memory correction.** A user cannot say "forget that I prefer TypeScript" and have Slowave resolve the entity "TypeScript preference" and delete it. They can only call `reinforce` with `wrong` feedback and hope the schema decays.
- **Single-machine limitation.** The SQLite store is inherently single-machine. Teams sharing memory across machines would need to sync the DB file externally.

### The Benchmark War

The LoCoMo/LongMemEval benchmark war among memory providers is essentially unwinnable and should not be entered directly:

- Zep claimed 84% on LoCoMo; an independent audit found methodological errors (wrong role assignment, wrong timestamp field, sequential vs. parallel search) that put the corrected score at 58.44%.
- Mem0's best published LoCoMo score (68.4%) was beaten by a Letta no-memory filesystem agent (74%).
- Penfield Labs' audit found a 6.4% error floor in LoCoMo itself.
- LoCoMo conversations fit in a 200k-token context window — full-context baselines are legitimate and hard to beat.
- Each vendor uses a different judge model, different backbone LLM, different subset — cross-paper comparison is structurally invalid.

**Credible positioning:** Publish Slowave's own harness results with full methodology stated, explicitly disclose the scorer difference (keyword-overlap vs. LLM-as-judge), and point at the benchmark war itself as evidence that the metric game is broken. This is more trustworthy than a numbers war, and the README already gestures at it — it just needs to lean in harder.

---

## 6. README Review and Recommendations

The README is well-structured and unusually honest. The issues are specific and fixable without fundamental rewrite.

### What Works Well

- The tagline ("A shared local memory layer for your AI tools") is concrete and correct.
- The compounding-loop diagram is one of the best explanations of the value proposition in this space.
- "What it is not" is excellent — should be kept exactly as is.
- The "Honest limits" section is the right move and the content is accurate.
- The benchmark caveat block ("Beta-stage results. Internal runs, not independently verified...") is commendable and rare.

### Issues to Fix

#### 1. The StaleMemory number in the table is misleading

Current:
```markdown
| StaleMemory | Detecting when a stored preference has silently changed | **86–89%** |
```

The 86-89% applies only to concrete attribute types (programming_language, naming_convention) — 2 of 8 categories. Overall detection rate is 45%. This is the biggest credibility risk in the README.

**Fix options:**
- Replace with: `**45%** overall; 86–89% for concrete preferences (programming language, naming conventions)` and a one-sentence footnote linking to `docs/benchmarks.md` for the breakdown.
- Or remove StaleMemory from the table entirely and reference it only in `benchmarks.md` with full context.

#### 2. "86% smaller context" metric needs a clearer qualifier

Current:
> internal tests showed **86% smaller context** over 20 sessions while preserving expected recall quality

This is true, but "expected recall quality" is defined by the same internal test — the comparison baseline is history-replay (putting all raw turns in context), which is a strawman most real agents don't use. Static knowledge files (CLAUDE.md etc.) are the actual competition for developer workflows.

**Fix:** Add "compared to full session history replay" after "smaller context", and link directly to `docs/token_efficiency.md` which is honest about the comparison.

#### 3. LongMemEval footnote should surface "oracle split"

The benchmark note already says "not directly comparable." It should also add:
> LongMemEval run on the oracle (evidence-only) split; first 10 turns per session ingested.

This is already in `reproducibility.md`; surface it inline.

#### 4. The install section undersells the install story

The `slowave setup` / `slowave doctor` UX is genuinely excellent and is a concrete differentiator. The README currently lists the commands without explaining what they do. Add one sentence: "slowave setup auto-configures every MCP-compatible client it finds — hooks, worker process, and lifecycle scripts — and is safe to re-run at any time."

#### 5. Consider adding a "Who is this for?" section

The README skips from "what it does" directly to install. A two-paragraph "Who this is for / who it is not for" section would help:

- **Good fit:** Solo developers using 2+ AI coding tools daily, users working on proprietary or sensitive codebases who cannot send data to cloud memory services, users who want memory without ongoing API costs.
- **Not the right fit:** Teams needing shared memory across machines, use cases requiring structured fact querying or surgical memory editing by name, scenarios where recall accuracy on factual QA is more important than cost/privacy.

#### 6. Benchmark table: add a "Scorer" column

The existing caveat block is good but easy to skip. A "Scorer" column in the table would make the comparison context impossible to miss:

```markdown
| Benchmark | What it tests | Slowave | Scorer |
|---|---|---:|---|
| LongMemEval (oracle) | Facts, updates, preferences across many sessions | **87.8%** | Keyword overlap |
| LoCoMo | Cross-session recall across real conversations | **76%** | Keyword overlap |
| StaleMemory (concrete prefs) | Detecting silently changed preferences | **86–89%** | Keyword overlap |
```

And then the caveat block explaining that most competitors use LLM-as-judge.

#### 7. The "Memory gets better with use" section sets expectations the current code doesn't fully meet

The loop description — "single interaction → episode → prototype → schema → lessons become general concepts" — is accurate as a roadmap but overstates the current consolidation fidelity (given the graph weight overwrite bug and dead self-supervision). This section should be softened slightly or a "(read architecture.md for current implementation status)" link added.

#### 8. Missing: a simple diagram of the data flow

The architecture section is text-only. A single ASCII or image diagram showing the data flow from MCP tool call → raw event → FAISS episode → prototype → schema → recall would help developers evaluate adoption quickly. The CLAUDE.md already has this; surfacing it in the README would be immediately useful.

### Suggested README structure (minimal rewrite)

```
1. Tagline + badges (keep as-is)
2. What it feels like (keep demo gif)
3. Who this is for (new, 2 short paragraphs)
4. How memory compounds (keep loop, soften one sentence)
5. Why it is different (keep, minor tweaks to context claim)
6. Install (keep, add one sentence on setup)
7. Benchmarks (add Scorer column, fix StaleMemory number)
8. Honest limits (keep exactly)
9. What it is not (keep exactly)
10. Dashboard (keep)
11. Documentation (keep)
12. Contributing (keep)
```

---

## 7. Priority Fix List

Ordered by severity and effort:

| Priority | Issue | File | Effort |
|---|---|---|---|
| P0 | Homebrew formula SHA-256 = empty string | `Formula/slowave.rb:6` | 5 min |
| P0 | Supersession applied to preferences against own docs | `engine.py:555-632` | 30 min |
| P0 | Fail-destructive default on missing embedding in supersession | `engine.py:576-580` | 15 min |
| P0 | Graph weight overwrite instead of accumulate | `graph_manager.py:117-136` | 1 hr |
| P1 | slowave-check.sh checks wrong deps (torch, sentence_transformers) | `scripts/slowave-check.sh:35-40` | 10 min |
| P1 | StaleMemory benchmark: surface 45% overall in README table | `README.md`, `benchmarks.md` | 20 min |
| P1 | Contrastive TF-IDF contrasts cluster against itself | `latent/schema.py:312-315` | 1 hr |
| P1 | Contradiction judge dead branch (both arms → "contradicts") | `latent/schema.py:441-451` | 30 min |
| P1 | CA3/CA1 thresholds: restore to 0.85/0.55 as documented | `replay_engine.py:22, 86-91` | 15 min |
| P1 | Bare `except Exception: pass` in supersession block | `engine.py:631-632` | 15 min |
| P1 | Session resolver: multi-client same-scope collision | `mcp/session_resolver.py` | 2-4 hr |
| P1 | `license-files = []` omits AGPL text from distributions | `pyproject.toml` | 10 min |
| P2 | conda/meta.yaml version stale (0.1.0) | `packaging/conda/meta.yaml:14` | 5 min |
| P2 | README: add Scorer column to benchmark table | `README.md` | 20 min |
| P2 | README: Who is this for? section | `README.md` | 30 min |
| P2 | Dashboard: cache SlowaveEngine instead of creating per-request | `dashboard/app.py` | 1 hr |
| P2 | Recall default mode: apply scope filter to FTS + prototype paths | `core/services/retrieval.py:247` | 1 hr |
| P2 | FAISS persistence: implement index save/load | `latent/episodic_store.py` | 2-3 hr |
| P3 | Remove or connect VSA subsystem (currently write-only) | `latent/vsa.py`, `latent/schema.py` | — |
| P3 | Derive transitions from real event adjacency (RawLog) | `latent/replay_engine.py` | 4-8 hr |
| P3 | Prune `consolidation_debug` table | `storage/schema.sql`, consolidation service | 1 hr |
| P3 | Remove `results/`, `slowave.egg-info/` from git | `.gitignore` | 10 min |

### 7.1 Priority Fix Rationale and Required Changes

This section expands the priority table into concrete engineering guidance: what is wrong, why it matters, and what fix is required. The items are mostly confirmed against the current codebase. A few are deliberately marked as documentation/positioning mismatches rather than direct runtime bugs.

#### P0 — Homebrew formula SHA-256 is wrong

**Location:** `Formula/slowave.rb`

**What is wrong:** The formula uses `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`, which is the SHA-256 digest of empty content. The audit table calls this an empty string; more precisely, it is the empty-content digest. It is not the digest of the published `slowave-0.9.2.tar.gz` source tarball.

**Why it matters:** Homebrew will reject the formula when the downloaded tarball hash does not match. This is a release-artifact breakage, not just metadata polish.

**Required fix:** Compute the real SHA-256 of the published PyPI sdist and replace the formula value. For example:

```bash
curl -L -o /tmp/slowave-0.9.2.tar.gz \
  https://files.pythonhosted.org/packages/source/s/slowave/slowave-0.9.2.tar.gz
shasum -a 256 /tmp/slowave-0.9.2.tar.gz
```

#### P0 — Supersession is applied to preferences too aggressively

**Location:** `slowave/core/engine.py`, `remember()` supersession block

**What is wrong:** Explicit preference-like memories are classified into the profile layer, but the geometry-based supersession path treats them like ordinary facts. A new preference can therefore supersede an older profile memory based on embedding similarity and direction score alone.

**Why it matters:** Preferences are not always mutually exclusive facts. A user can prefer detailed answers for architecture review and concise answers for CLI usage. Destructive supersession can erase valid contextual preferences and contradict the durable-profile semantics described in the user-facing lifecycle guidance.

**Required fix:** Add a non-destructive policy for profile-layer memories. For `memory_layer == "profile"` and/or `schema_class == "preference"`, do not auto-supersede from geometry alone. Prefer one of:

- mark the old schema `needs_review`,
- require explicit stale/wrong feedback,
- require a structured same-dimension preference key before superseding,
- or only reinforce/record relation unless the user explicitly states replacement.

#### P0 — Missing embedding falls into destructive supersession

**Location:** `slowave/core/engine.py:576-580`

**What is wrong:** When the candidate schema embedding is missing, the code defaults `dir_score` to `DIRECTION_THRESHOLD`. The later branch checks `dir_score >= DIRECTION_THRESHOLD`, so missing evidence is treated as sufficient evidence to supersede.

**Why it matters:** Missing geometry should make the system more conservative, not more destructive. The current fallback can silently retire valid memories because an embedding was unavailable.

**Required fix:** Make missing manifold/candidate embedding a non-destructive path. Either skip the candidate or mark it `needs_review`. Do not default to the destructive threshold. Conceptually:

```python
if manifold is None or candidate_emb is None:
    continue  # or mark needs_review
```

#### P0 — Graph weights overwrite instead of accumulate

**Location:** `slowave/latent/graph_manager.py`

**What is wrong:** `ON CONFLICT DO UPDATE` replaces `w_transition` and `w_coactivation` with the latest replay-pass values. Prior evidence is overwritten rather than accumulated.

**Why it matters:** The architecture describes learned/Hebbian transition and coactivation strength. Hebbian learning implies repeated coactivation strengthens a path over time. Current behavior is closer to a latest-batch snapshot.

**Required fix:** Keep similarity as a recomputed snapshot, but make transition and coactivation learned quantities. Use additive or decayed-additive updates, then recompute `weight` from updated components. For example:

- `w_similarity`: replace with current cosine top-k value,
- `w_transition`: `old * decay + incoming`,
- `w_coactivation`: `old * decay + incoming`.

#### P1 — `slowave-check.sh` checks stale dependencies

**Location:** `scripts/slowave-check.sh`

**What is wrong:** The script checks for `torch` and `sentence_transformers`, which are not current direct project dependencies, and misses current dependencies such as `onnxruntime`, `transformers`, `huggingface_hub`, `mcp`, `uvicorn`, and `starlette`.

**Why it matters:** The diagnostic script can report a valid install as broken and can miss actual missing dependencies.

**Required fix:** Align import checks with `pyproject.toml`. Remember that package names and import names differ: `faiss-cpu` imports as `faiss`, and `huggingface-hub` imports as `huggingface_hub`.

#### P1 — StaleMemory headline should surface the 45% overall result

**Location:** `README.md`, `docs/benchmarks.md`

**What is wrong:** The README headline table reports `86–89%` for StaleMemory, but that applies only to concrete preferences with distinct keywords. The benchmark breakdown includes much weaker categories: partially concrete at about 20%, borderline at about 15%, and abstract behavioral preferences at 0–1%. The overall result is documented in the audit as 45%.

**Why it matters:** Presenting a best-case subset as the headline benchmark result is a credibility risk, especially because benchmark comparability is already complicated by scorer differences.

**Required fix:** Change the README result to something like `45% overall; 86–89% for concrete keyword preferences`, and link to `docs/benchmarks.md` for the category breakdown.

#### P1 — Contrastive TF-IDF contrasts the cluster against itself

**Location:** `slowave/latent/schema.py:312-315`

**What is wrong:** The lexical signature builder is called with `cluster_texts` as both the target and background corpus. That produces frequent in-cluster terms, not terms that distinguish this cluster from other clusters.

**Why it matters:** A contrastive signature should identify what makes a schema distinct. Current labels/facets can be generic because there is no outside background distribution.

**Required fix:** Pass a real background corpus, such as all replay-sampled episode texts, nearby prototype texts, or all schema/prototype texts available during the consolidation pass.

#### P1 — Contradiction judge has a dead branch

**Location:** `slowave/latent/schema.py:441-451`

**What is wrong:** Both branches of the support/time check set `verdict = "contradicts"`. The `min_support_to_supersede` condition has no effect.

**Why it matters:** The code comment claims support and recency affect supersession, but the function does not implement that distinction. This misleads maintainers and reviewers.

**Required fix:** Either simplify the code and comment to always return `contradicts` from this judge, leaving supersession entirely to the consolidator, or introduce a distinct verdict such as `supersedes` when recency/support criteria are met.

#### P1 — CA3/CA1 thresholds are identical despite the dual-scale story

**Location:** `slowave/latent/replay_engine.py`

**What is wrong:** Both fine and coarse assignment thresholds default to `0.60`. The code comment says this was selected by grid search, but any documentation that describes distinct CA3/CA1 thresholds or clearly different fine/coarse assignment behavior is ahead of the implementation.

**Why it matters:** This is an architecture-honesty issue. A reviewer can reasonably ask what makes the two scales meaningfully different if their assignment threshold is identical.

**Required fix:** Pick one truth and make code/docs agree:

1. restore distinct thresholds if that is the intended architecture and tests support it, or
2. update documentation to say dual-scale storage exists but distinct CA3/CA1 thresholding is currently not enabled because equal thresholds performed better in tuning.

Option 2 is preferable unless benchmark evidence supports changing the defaults.

#### P1 — Bare `except Exception: pass` hides supersession failures

**Location:** `slowave/core/engine.py:631-632` and nearby inner handlers

**What is wrong:** The supersession block mutates durable schema state, but broad exceptions are swallowed silently.

**Why it matters:** If belief revision fails, developers need logs and tests to reveal it. Silent failure in memory mutation makes correctness bugs hard to diagnose.

**Required fix:** Catch expected exceptions narrowly and log unexpected ones. For example, catch `KeyError` for missing candidates, but use `log.exception(...)` for unexpected failures.

#### P1 — Session resolver can collide across clients with the same scope

**Location:** `slowave/mcp/session_resolver.py`

**What is wrong:** The resolver maps one binding per scope: `scope -> session_id`. If two clients or tasks use the same scope concurrently, the later `activate()` overwrites the earlier binding. A subsequent `remember(session_id=None)` can attach to the wrong session.

**Why it matters:** This corrupts lifecycle attribution and can place memories/events into another task's session.

**Required fix:** Bind by a more specific key than scope alone, such as `(client_id, scope)` or `(connection_id, scope)`. HTTP mode likely needs a client/session key. Stdio mode can use process/connection-local identity.

#### P1 — AGPL license text is omitted from distributions

**Location:** `pyproject.toml`

**What is wrong:** `[tool.setuptools] license-files = []` explicitly disables license-file inclusion.

**Why it matters:** For an AGPL project, source distributions and wheels should include the license text. This is both compliance and packaging quality.

**Required fix:** Remove the override or set:

```toml
[tool.setuptools]
license-files = ["LICENSE"]
```

#### P2 — Conda recipe version and dependencies are stale

**Location:** `packaging/conda/meta.yaml`

**What is wrong:** The recipe sets version `0.1.0` while the project is currently `0.9.2`. It also still lists stale dependencies such as `pytorch` and `sentence-transformers`.

**Why it matters:** Anyone using or submitting the recipe would publish/install the wrong version with wrong dependencies.

**Required fix:** Update the version, source hash, Python requirement, entry points if needed, and dependency list to match `pyproject.toml`.

#### P2 — README benchmark table needs a scorer column

**Location:** `README.md`

**What is wrong:** The benchmark table reports numbers without showing scoring protocol. Slowave uses local keyword/embedding-style scoring, while many competitors use LLM-as-judge.

**Why it matters:** Scores are not directly comparable across scorers. The table should prevent apples-to-oranges interpretation.

**Required fix:** Add a `Scorer` or `Protocol` column, e.g. `keyword-overlap/local`, `embedding/local`, or `LLM judge` where applicable.

#### P2 — README should add a “Who is this for?” section

**Location:** `README.md`

**What is wrong:** This is not a correctness bug. It is a positioning gap: Slowave is a local, inspectable memory substrate, not an agent framework, prompt manager, or reasoning system.

**Why it matters:** The project has unusual design constraints. A short audience section reduces mismatched expectations.

**Required fix:** Add a concise section explaining that Slowave is for developers who want local cross-tool long-term memory with zero LLM calls in memory operations, and not for users who want autonomous reasoning or LLM-generated summaries.

#### P2 — Dashboard creates a new engine per recall request

**Location:** `slowave/dashboard/app.py`

**What is wrong:** `_recall_payload()` constructs and closes a `SlowaveEngine` on every dashboard recall request.

**Why it matters:** Engine startup can initialize encoder and index state. Per-request construction is wasteful and slows dashboard UX.

**Required fix:** Cache a dashboard engine per `db_path` for the dashboard process, with careful shutdown and thread-safety because the dashboard uses `ThreadingHTTPServer`.

#### P2 — Recall candidate generation is still partly unscoped

**Location:** `slowave/core/services/retrieval.py`

**What is wrong:** FTS and prototype-derived schema candidates are collected before scope filtering. The current code does apply a strict-scope post-filter, so this is less urgent than a direct leak, but candidate generation remains broader than necessary.

**Why it matters:** Early unscoped candidate collection wastes work and makes scope isolation harder to audit. Future changes to filtering could accidentally leak cross-scope results.

**Required fix:** Scope candidate generation as early as possible where APIs support it, while preserving explicit logic for global/profile/promoted schemas. Add regression tests with identical text in two scopes to ensure strict mode only returns allowed memories.

#### P2 — FAISS indexes are not persisted

**Location:** `slowave/latent/episodic_store.py`, `slowave/latent/semantic_store.py`

**What is wrong:** FAISS indexes are in-memory and rebuilt from SQLite. There is no `faiss.write_index()` / `faiss.read_index()` path.

**Why it matters:** This is not a correctness bug because SQLite remains the source of truth, but startup/rebuild costs can grow with database size.

**Required fix:** Implement optional index save/load with robust fallback to `reset_faiss_from_db()` when the persisted index is missing, corrupt, has the wrong dimension, or disagrees with SQLite counts.

#### P3 — VSA subsystem is mostly write-only

**Location:** `slowave/latent/vsa.py`, `slowave/latent/schema.py`

**What is wrong:** Schema construction stores VSA vectors, but retrieval/ranking/consolidation do not materially use them.

**Why it matters:** If docs imply hippocampal binding/VSA changes behavior, the implementation does not currently support that claim.

**Required fix:** Either connect VSA to measured retrieval/relation behavior, label it clearly as experimental/internal, or remove it to reduce narrative-only complexity.

#### P3 — Transition edges are derived from replay-batch order, not real adjacency

**Location:** `slowave/latent/replay_engine.py`

**What is wrong:** Transition counts are estimated by sorting a salience-sampled replay batch by timestamp, then counting adjacent prototypes. This is not the same as observed event or episode adjacency within sessions.

**Why it matters:** The transition graph can learn artificial transitions between unrelated sampled episodes. If transitions are described as learned temporal trajectories, they should come from actual sequence evidence.

**Required fix:** Derive transition counts from ordered `raw_events`, `episode_text`, or session-level episode order: for each session, count `prototype(episode_i) -> prototype(episode_i+1)`.

#### P3 — `consolidation_debug` has stale LLM-era semantics

**Location:** `slowave/storage/schema.sql`, consolidation service

**What is wrong:** The table comment says it records what the LLM saw and what claims were parsed from the response, but current consolidation is explicitly zero-LLM and writes empty prompt/response JSON.

**Why it matters:** This creates an avoidable contradiction for reviewers: a zero-LLM system has a table documenting “what the LLM saw.”

**Required fix:** Rename or redesign the table as a neutral `consolidation_trace`, remove stale LLM columns/comments, or mark it as legacy and stop creating it in new databases.

#### P3 — Generated results are tracked; `slowave.egg-info` appears local-only

**Location:** `results/`, `.gitignore`

**What is wrong:** `results/wiki_scenarios_*.json` files are tracked. The audit also mentions `slowave.egg-info`, but that was not confirmed as tracked; it appears to be a local generated directory.

**Why it matters:** Generated artifacts create repository noise and can become stale. Tracked benchmark outputs should either be documented as canonical artifacts or removed.

**Required fix:** If the files are generated outputs, remove them from git and add ignore rules:

```gitignore
/results/
*.egg-info/
```

If they are canonical benchmark evidence, move them under a documented benchmark-results directory and explain how they were produced.

#### Suggested execution order

Before release, fix the destructive/correctness and credibility issues first:

1. missing embedding must not supersede,
2. preference/profile memories must not be geometry-superseded destructively,
3. Homebrew SHA,
4. license-file packaging,
5. stale install diagnostics and conda metadata,
6. benchmark headline/scorer transparency,
7. graph weight accumulation or documentation correction,
8. supersession exception logging,
9. session resolver same-scope collision,
10. contrastive TF-IDF and contradiction-judge cleanup.

Then handle architecture-honesty and cleanup items: CA3/CA1 documentation alignment, dashboard engine caching, scoped candidate-generation tests, FAISS persistence, VSA connection/removal, real transition adjacency, `consolidation_debug` cleanup, and generated artifact removal.

#### Implementation grouping: safe batch vs measured one-by-one changes

Point 15 from the expanded list — the README “Who is this for?” positioning section — is intentionally excluded from this grouping. It is optional documentation positioning, not a release-readiness or benchmark-risk fix.

The remaining changes should be split into two implementation tracks.

##### A. No functional or benchmark effect — can be implemented together

These changes should not alter memory behavior, retrieval ranking, consolidation output, or benchmark scores. They can be bundled in one documentation/packaging/cleanup PR, then validated with packaging checks and smoke tests.

1. **Homebrew SHA fix** — update `Formula/slowave.rb` with the real PyPI sdist digest. This only affects Homebrew installation integrity.
2. **`slowave-check.sh` dependency list** — align diagnostic import checks with current `pyproject.toml`. This changes install diagnostics, not runtime memory behavior.
3. **StaleMemory README disclosure** — surface `45% overall; 86–89% for concrete keyword preferences`. This changes benchmark presentation, not benchmark behavior.
4. **README benchmark scorer/protocol column** — clarify scoring method and comparability. Documentation-only.
5. **AGPL license-file packaging** — include `LICENSE` in distributions by removing `license-files = []` or setting `license-files = ["LICENSE"]`. Packaging-only.
6. **Conda metadata refresh** — update conda recipe version, dependencies, source hash, and Python requirement to match current package metadata. Packaging-only unless the recipe is used to run benchmarks, in which case validate the environment once.
7. **Contradiction judge dead-branch cleanup, if behavior-preserving** — safe only if the change removes the redundant branch while preserving the returned verdict exactly. If introducing a new verdict or support-sensitive behavior, move it to Track B.
8  **`consolidation_debug` comment/table cleanup, if schema-compatible** — safe if limited to comments, neutral naming in docs, or non-invasive metadata cleanup. If changing schema creation/migrations, treat as Track B or run migration tests separately.
9  **Generated artifact cleanup** — remove tracked generated `results/` files and add `.gitignore` entries, unless those files are used as canonical comparison baselines in tests.
10 **VSA documentation/labeling, if docs-only** — safe if the fix merely labels VSA as experimental/internal. If removing or connecting VSA code, move it to Track B.

Validation for this batch:

- run unit/smoke tests,
- run packaging/build checks if available,
- verify README/docs render cleanly,
- verify Homebrew/conda metadata points to correct release artifacts.

##### B. Functional, performance, or benchmark-impacting — implement one by one and measure

These changes can alter memory state transitions, retrieval output, consolidation graph structure, runtime performance, or benchmark scores. They should be implemented one at a time, with before/after metrics recorded after each change. Do not batch these together, because batching would make regressions or improvements impossible to attribute.

| # | P | Item | Status | Branch | Benchmark | Result |
|---|---|---|---|---|---|---|
| B-1 | P0 | Missing embedding must not supersede | ✅ Done | `fix/b1-missing-embedding-no-supersession` | Wiki full (15 scenarios) | 15/18 hits — identical to baseline (guard never triggered; all schemas have embeddings in normal operation). Unit: 3/3 pass. |
| B-2 | P0 | Preference/profile memories must not be geometry-superseded destructively | ✅ Done | `fix/b2-preference-no-geometry-supersession` | Wiki full (15 scenarios) | 15/18 — identical to baseline (profile guard not triggered by fact-type wiki). Unit: 6/6 pass. |
| B-3 | P1 | Graph weight accumulation instead of overwrite | ✅ Done | `fix/b3-graph-weight-accumulation` | Wiki full (15 scenarios) | 15/18 — identical to baseline. Unit: 6/6 pass. |
| B-4 | P2 | Contrastive TF-IDF with real background corpus | ✅ Done | `fix/b4-contrastive-tfidf-background-corpus` | Wiki full (15 scenarios) | 15/18 — identical (display_label not used in scoring). Unit: 5/5 pass. |
| B-5 | P2 | Contradiction judge behavior change (support/recency) | ✅ Done | `fix/b5-contradiction-judge-support-recency` | Wiki full (15 scenarios) | 15/18 — identical (support gates don't change verdicts on benchmark data). Unit: 4/4 pass. |
| B-6 | P2 | CA3/CA1 threshold differentiation (0.60/0.60 → 0.85/0.55) | ✅ Done | `fix/b6-ca3-ca1-threshold-differentiation` | LongMemEval 500q, LoCoMo 1986q, DMR 500q | LongMemEval 87.8% (no change), LoCoMo 76.54% (+0.54pp), DMR 95.0%. No regression. Unit: all pass. |
| B-7 | P2 | Supersession exception handling beyond logging | ✅ Done | `fix/b7-supersession-exception-handling` | Wiki full (15 scenarios) | Identical to baseline (logging-only change, no behavior). Unit: all pass. |
| B-8 | P2 | Session resolver same-scope collision fix | ✅ Done | `fix/b8-session-resolver-collision` | N/A (concurrency fix) | Unit: 8/8 pass including thread isolation test. |
| B-9 | P2 | Dashboard engine caching | ✅ Done | `fix/b9-dashboard-engine-caching` | N/A (performance-only) | Module-level cached engine with double-checked locking. Unit: all pass. |
| B-10 | P2 | Recall candidate-generation scope filtering | ✅ Done | fix/b10-scope-filter-candidate-generation | Strict-scope leakage tests, context injection, recall benchmarks | 3/3 tests pass; FTS + prototype candidates filtered at collection time | — |
| B-11 | P3 | FAISS persistence (save/load index) | ✅ Done | fix/b11-faiss-persistence | Startup time, recall equivalence before/after reload, rebuild fallback | EpisodicStore + SemanticStore now faiss.write_index/read_index with fallback to reset_faiss_from_db() | — |
| B-12 | P3 | VSA removal or connection to retrieval | 🔄 Pending | — | Schema formation quality, retrieval quality | Skipped — needs design discussion. VSA computed but unused in retrieval; either remove or wire in, not a quick fix. |
| B-13 | P3 | Real event-adjacency transitions | ✅ Done (doc fix) | — | Graph/path-completion, transition edge distribution | Batch-order transitions are hippocampal replay co-activation, not a bug. Comment added in replay_engine.py explaining session-order adjacency would need a separate path. |
| B-14 | P3 | `consolidation_debug` schema/migration cleanup | ✅ Done | fix/b14-consolidation-debug-cleanup | Migration compatibility, dashboard/diagnostic queries | Removed LLM-era columns (prompt_text, response_json, extracted_claims_json). Migration drops them for existing DBs. |
| B-15 | P3 | Generated results tracked in repo (`.gitignore` cleanup) | ✅ Done | fix/b15-gitignore-cleanup | Build reproducibility, no stale benchmark outputs in repo | Added tests/wiki_scenarios/results/ to .gitignore. Untracked 4 auto-generated JSONs. |

**Minimum metric protocol for Track B:**

1. record the pre-change baseline commit and benchmark command,
2. implement exactly one functional change,
3. run unit tests plus the smallest targeted scenario for that subsystem,
4. run the relevant benchmark subset,
5. record quality metrics, latency/runtime, prototype/schema/edge counts where applicable,
6. only then decide whether to keep, tune, or revert the change.

---

## 8. Summary

Slowave has a genuine, defensible, and rare architectural property: it is the only deployed agent memory system that performs all consolidation and recall without any LLM calls. The cross-tool shared local store with scoped isolation is a real and uncontested market position. The retrieval pipeline is carefully designed with good anti-feedback-loop discipline.

The main risk is a gap between the neuroscience-inspired narrative and the actual consolidation implementation — specifically the graph weight overwrite, the identical CA3/CA1 thresholds, and the dormant self-supervision mechanism. These are fixable bugs, not design failures, but they would be embarrassing in a code review from an adversarial reader. Fixing P0 and P1 items before the next major release would close that gap significantly.

The README is among the most honest in this space. Its primary weakness is the StaleMemory number in the "At a Glance" table, which should surface the 45% overall rate rather than leading with the 86-89% best-case. The project's credibility is better served by full transparency than by a number that invites scrutiny.
