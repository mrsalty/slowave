# Changelog

## [Unreleased]

### Added

- **Memory generalization**: memories that prove useful across multiple scopes are automatically promoted to broader visibility over time. Promotion is driven by recall breadth (how many distinct scopes and scope kinds a memory has been recalled in), not by LLM classification. Four stages: scoped (default), portable (same scope kind), contextual (cross-scope with reduced ranking weight), and global (unrestricted). All mechanics are LLM-free and deterministic.
- **Scope registry**: lightweight internal catalogue of known scopes, updated on every session start. Provides cheap denominator queries for the generalization stage computation.
- **Implicit selection signal** (`schemas.selection_count`): every schema selected into context or recall now increments a dedicated counter column. This separates the raw selection trace from salience, making it available for future analytics and ML model features without affecting retrieval ranking.
- **Full candidate pool tracing** (`context_recall_items.admitted`): the working-memory gate now records both admitted and filtered candidates per retrieval event. `admitted=1` means the schema was selected into context; `admitted=0` means the gate evaluated it but dropped it. Filtered items are stored with `rank=-1`. This enables queries over the full evaluation pool, not just what was returned.

### Fixed

- **Self-reinforcing recall loop**: `recall()` previously called `reinforce(amount=0.05)` unconditionally on every selected schema, bumping salience regardless of whether the memory proved useful. This created a feedback loop where selection alone caused a memory to rank higher in future recalls, independent of any quality signal. Selection now calls `mark_selected()` instead, which increments `selection_count` but does not touch salience. Salience only changes when explicit feedback arrives via `slowave_reinforce`. The `reinforce()` method is unchanged and continues to be used by the consolidation path where it is appropriate.

