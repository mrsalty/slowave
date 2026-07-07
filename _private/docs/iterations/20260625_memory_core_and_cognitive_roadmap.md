# Slowave Memory Core and Cognitive Roadmap — 2026-06-25

## Purpose

This note captures the product/architecture direction discussed after the global project review: first make Slowave's current memory-centered functions rock solid and draw a clear v1 line, then choose the next cognitive-function trajectory that can make Slowave the brain-inspired memory system people actually adopt.

## Strategic position

Slowave should not try to become a complete cognitive architecture. Its strongest position is narrower and more defensible:

> Slowave is a local adaptive memory substrate for AI agents. It remembers, prioritizes, consolidates, reinforces, supersedes, and explains. The agent reasons and acts.

This boundary keeps Slowave distinct from agent planners, reasoning engines, language models, and tool execution frameworks.

## Current cognitive-function core

Slowave already covers the memory-centered subset of cognition:

| Cognitive function | Slowave equivalent |
| --- | --- |
| Episodic memory | raw events, sessions, episodes |
| Semantic memory | schemas, prototypes |
| Working memory | `activate()` / gated context brief |
| Attention | salience, scope, gating, activation thresholds |
| Associative memory | graph links, spreading activation, coactivation |
| Learning | feedback, reinforcement, recurrence, generalization |
| Consolidation | worker/replay/schema formation |
| Prediction | TransitionModel / trajectory edges |
| Supersession | newer memories replacing older ones |
| Metacognition | confidence, `needs_review`, feedback health, diagnostics |

This is enough for a strong v1. The risk is widening into more cognitive domains before the existing memory loop is fully reliable.

## Phase 1: make the current memory core rock solid

The first priority is not more cognitive breadth. It is reliability, invariants, and trust.

### 1. Lifecycle reliability

The 5-verb cycle must be boringly dependable:

```text
activate → remember → recall → reinforce → commit
```

Success criteria:

- `activate()` opens or resolves sessions predictably.
- `remember()` stores durable typed memories with correct scope.
- `recall()` does not leak across scopes unless explicitly allowed.
- `reinforce()` applies feedback to the exact retrieval snapshot.
- `commit()` closes the correct session and forms episodes when appropriate.
- skipped commits are handled safely by the session reaper.

### 2. Scope safety

Scope safety is adoption-critical. Users will not trust a memory system that leaks irrelevant or private project context.

Required invariants:

- `strict_scope` means strict.
- CLI, MCP, and Python API semantics match.
- cross-scope recall is explicit, bounded, and explainable.
- global memories require strong promotion rules.
- diagnostics explain why any memory crossed scope boundaries.

Positioning:

> Memory follows context, not chaos.

### 3. Retrieval quality and explainability

Every surfaced memory should be explainable in debug/inspection paths.

Useful explanation components:

- similarity score
- salience
- scope match
- recency / temporal bias
- feedback history
- graph or spreading-activation contribution
- generalization stage
- confidence
- status
- provenance / source evidence

Normal output can stay compact, but the system must be inspectable when users ask, “Why did this memory appear now?”

### 4. Consolidation correctness

Consolidation is Slowave's most important brain-inspired differentiator. It must improve memory over time rather than create clutter.

Harden:

- duplicate prevention
- schema formation quality
- old-memory supersession
- contradiction handling
- stale-memory decay
- episode-to-schema evidence links
- replay behavior
- migration safety
- deterministic-enough tests

Key question:

> If a user runs Slowave for six months, does memory get better or messier?

Rock solid means: better.

### 5. Feedback learning

Feedback makes Slowave adaptive rather than static RAG.

Expected behavior:

- useful memories strengthen
- wrong or stale memories weaken or move to review
- missing feedback is tracked
- `too_much_context` reduces future over-injection
- feedback attaches to exact retrieval snapshots
- feedback effects are visible in diagnostics

### 6. Operational reliability

Adoption depends on boring local operations:

- install works
- setup works
- doctor explains issues
- backup/restore works
- dashboard is useful
- daemon/worker are stable
- DB migrations are safe
- local privacy story is clear
- first model download is explicit; later runs are offline

## The v1 line

### Slowave v1 owns

- memory encoding
- episodic storage
- semantic consolidation
- associative retrieval
- working-memory activation
- salience / attention
- feedback reinforcement
- scope governance
- supersession and decay
- provenance and explanation
- memory health diagnostics

### Slowave v1 does not own

- general reasoning
- autonomous planning
- tool execution
- agent policy
- language generation
- social reasoning
- consciousness / global workspace claims
- full cognitive architecture

Guiding sentence:

> Slowave remembers, prioritizes, consolidates, and explains. The agent reasons and acts.

## Phase 2: next cognitive trajectory — memory governance

After the current memory core is solid, the most valuable next cognitive-function trajectory is **memory governance**, not reasoning or planning.

Memory governance means Slowave becomes excellent at knowing the quality, uncertainty, reliability, conflict state, provenance, and lifecycle of its own memories.

This is the right next trajectory because most memory tools stop at store/search. Slowave can own the fuller loop:

```text
experience → consolidate → retrieve → evaluate → reinforce → supersede → forget → explain → self-maintain
```

Product promise:

> Slowave is not just a vector memory. It is a self-maintaining memory system.

### Memory governance capabilities

#### 1. Interpretable confidence

Each important memory should expose confidence as a composite, not a mysterious number.

Example components:

- evidence count
- supporting sessions
- last confirmed time
- contradiction count
- scope stability
- feedback score
- recurrence
- source kind

#### 2. Coherent memory lifecycle states

Useful states include:

- active
- tentative
- needs_review
- contradicted
- stale
- superseded
- archived

Some of this already exists. The goal is to make the lifecycle coherent, visible, and reliable.

#### 3. Contradiction and review queues

Users should be able to inspect and resolve memory conflicts:

> These memories disagree; please resolve or mark one as superseded.

This is especially important for long-lived local memory.

#### 4. First-class provenance

Important memories should answer:

- where did this come from?
- when was it formed?
- which sessions support it?
- has it been reinforced?
- has it been contradicted?
- when was it last useful?

Provenance is a trust feature.

#### 5. Forgetting as a feature

Brain-inspired memory should not mean infinite accumulation. Forgetting should be adaptive retention.

Policy examples:

- preserve constraints unless explicitly removed
- preserve lessons longer than raw events
- decay one-off low-salience facts
- archive stale project details
- protect durable user preferences
- forget contradicted transient facts

## Phase 3: predictive context, not executive control

After memory governance, improve prediction carefully.

The goal is not:

> Slowave decides what the agent should do.

The goal is:

> Slowave predicts which memories are likely useful for what the agent is about to do.

### Capabilities

- task-phase memory priors: debugging, planning, implementation, review, release, documentation, incident response
- predictive prefetch during `activate()`
- “likely useful next” memory hints
- trajectory explanations

Important constraint:

> Trajectory edges are explanatory only. They describe what tends to happen; they never prescribe what must happen.

## Phase 4: personalized memory policy

Different scopes need different retention and recall policies.

Examples:

- `project:*` — preserve architecture decisions, constraints, test commands, bug lessons; decay temporary implementation details.
- `user:*` — preserve durable preferences and stable personal facts; protect sensitive data.
- `domain:*` — preserve concepts, references, reusable knowledge, uncertainty.
- `relationship:*` — preserve interaction preferences and stable social context only if explicitly intended.

This keeps Slowave adaptive without needing LLM-based memory operators.

## Phase 5: adoption layer

Brain-inspired architecture wins attention, but adoption depends on integration and reliability.

To become the default memory substrate, Slowave needs:

- stable MCP surface
- stable Python API
- stable CLI
- import/export
- memory portability
- simple local DB story
- integration docs for common agent frameworks
- dashboard polish
- multi-agent/multi-client clarity
- one-command setup that does not surprise users

## Trajectories to avoid for now

Avoid expanding into:

- full reasoning engine
- autonomous planner
- hidden procedural execution engine
- consciousness / global-workspace framing
- broad social cognition
- LLM-heavy consolidation

These either duplicate the host LLM/agent runtime, create unsafe hidden policy, or weaken Slowave's core differentiator: local memory consolidation without LLM calls.

## Recommended milestone sequence

### Milestone A: Memory Core Freeze

Define the official v1 contract:

- lifecycle API
- scope rules
- schema lifecycle
- feedback semantics
- consolidation behavior
- retrieval explanation format
- storage/migration guarantees

Potential artifacts:

- `docs/architecture_v1.md`
- `docs/memory_contract.md`

### Milestone B: Trust and Explainability

- retrieval explanation
- memory provenance view
- confidence components
- scope-crossing explanations
- feedback audit log
- dashboard memory health

### Milestone C: Memory Hygiene

- stale-memory review
- contradiction queue
- duplicate cleanup
- controlled forgetting policies
- archive/decay dashboard

### Milestone D: Predictive Context

- task-phase priors
- predictive prefetch
- trajectory explanations
- “likely useful next” hints

### Milestone E: Adoption Layer

- integration guides
- API stability
- MCP hardening
- import/export
- dashboard polish
- reliable one-command install

## Adoption thesis

People adopt infrastructure when it is:

1. useful immediately
2. reliable after months
3. inspectable
4. correctable
5. private/local
6. easy to integrate
7. hard to misuse
8. clearly better than vector search

Winning product statement:

> Slowave is the local memory layer agents can trust: it remembers what matters, forgets what does not, explains why memories appear, learns from feedback, protects scope boundaries, and improves through consolidation — without sending memory to an LLM.

## Final recommendation

1. Consolidate and freeze the current memory core.
2. Build memory governance: confidence, uncertainty, provenance, contradiction, forgetting, review.
3. Add predictive context without turning prediction into executive control.
4. Add personalized memory policy by scope type.
5. Harden the adoption layer so Slowave becomes the default local memory substrate rather than just an interesting architecture.