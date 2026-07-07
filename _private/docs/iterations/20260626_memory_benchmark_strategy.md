# Slowave Memory Benchmark Strategy — 2026-06-26

## Purpose

This note captures a benchmark strategy for evaluating Slowave as a memory system rather than as a generic question-answering assistant. The key framing is that existing conversation datasets are useful raw material, but none directly evaluates persistent agent memory without transformation into memory-specific tasks.

## Dataset fit

| Dataset | What it tests | Value for Slowave |
| --- | --- | --- |
| ShareGPT Long Conversation | Very long context windows | Tests whether Slowave can replace brute-force long-context prompting by retrieving the right memories instead of replaying 8k+ words. |
| REALTALK | Longitudinal memory across days/weeks | Strongest single fit. Tests episodic memory, preference evolution, forgetting, reinforcement, contradictions, supersession, and procedural learning over time. |
| LMSYS-Chat-1M | Huge diversity of real conversations | Excellent for stress-testing extraction, scalability, promotion, deduplication, retrieval precision, and memory pollution. |
| ShareChat | Multilingual conversations | Tests language-agnostic memory extraction and retrieval, one of Slowave's design goals. |

## Evaluation principle

Slowave should be evaluated on its unique memory claims, not only on whether the downstream model answers correctly.

The benchmark should separate failures by layer:

- the important fact was never extracted;
- the fact was extracted but not promoted;
- the fact was promoted but later superseded incorrectly;
- the memory exists but retrieval missed it;
- retrieval found it but injected too much irrelevant memory;
- injection was correct but the downstream model ignored it.

## Core benchmark areas

### 1. Recall accuracy

Question: does the correct memory get retrieved when needed?

Metrics:

- Recall@k
- MRR
- nDCG
- irrelevant retrieval rate

### 2. Memory extraction

Question: are important, durable facts extracted while transient or fictional facts are ignored?

Metrics:

- precision
- recall
- F1
- memory type accuracy
- attribution accuracy
- temporal qualifier accuracy

### 3. Promotion

Question: does repeated evidence turn episodic observations into stable semantic memories?

Positive example:

- "I use pnpm."
- "Run pnpm test."
- "My projects use pnpm."
- "Please don't suggest npm."

Expected promoted memory:

> User prefers pnpm over npm for JavaScript projects.

Negative examples that should not promote:

- "I'm trying Rust today."
- "For this experiment, use MongoDB."
- "I'm temporarily staying in Paris."

Metrics:

- true promotion rate
- false promotion rate
- repetitions to promotion
- promotion latency
- specificity/generalization quality

### 4. Supersession

Question: can obsolete memories be replaced or suppressed when newer evidence contradicts them?

Examples:

- old preference -> new preference
- old address -> new address
- old workflow -> new workflow

Metrics:

- supersession accuracy
- stale memory retrieval rate
- current-fact accuracy
- obsolete-fact suppression
- contradiction resolution accuracy
- supersession link accuracy

Expected behavior: old memories may remain historically available, but current-user queries should retrieve the currently valid fact.

### 5. Procedural learning

Question: can Slowave learn a useful procedure from prior interaction and retrieve the procedure instead of merely replaying the original episode?

Example:

Day 1:

- User hits a Docker issue.
- Assistant suggests a generic fix.
- User says the fix did not work.
- User manually discovers the actual fix.
- Slowave should encode the learned procedure.

Day 8:

- The same symptoms recur.
- Slowave should retrieve the learned procedure, not the failed generic advice.

Metrics:

- procedure extraction accuracy
- procedure retrieval accuracy
- avoided failed-advice rate
- time-to-solution reduction
- correct preference for procedural memory over raw episode

REALTALK is especially valuable here because it naturally contains longitudinal recurrence.

### 6. Cross-session retrieval and injection

Question: can a fresh conversation receive only the relevant memories needed for the current task?

Metrics:

- precision of injected memories
- missing required memories
- unnecessary memories
- total injected tokens
- answer accuracy per injected token

Memory minimality should be a first-class metric. Slowave should retrieve the smallest useful set, not merely any correct set.

### 7. Multilingual generalization

Question: can Slowave extract and retrieve memories across languages?

Example:

Session 1, Italian:

> Mi piace il tè verde.

Later, English:

> What drink do I usually enjoy?

Expected answer:

> Green tea.

Metrics:

- cross-lingual Recall@k
- cross-lingual answer accuracy
- language-preserving vs normalized memory quality
- retrieval degradation compared with monolingual cases

ShareChat is the best dataset among the listed options for this validation.

### 8. Scalability

Question: does memory quality and latency degrade gracefully as the store grows?

Use LMSYS-style diversity and scale points:

- 100 memories
- 1,000 memories
- 100,000 memories
- 1 million memories

Metrics:

- retrieval latency
- write latency
- promotion latency
- storage growth
- duplicate rate
- memory quality degradation
- memories created per 1,000 turns
- memory pollution rate

## Long-Context Replacement Benchmark

This is the headline benchmark for demonstrating Slowave's practical value.

Structure:

1. Feed a 20,000-token conversation incrementally.
2. Build memories over time with Slowave.
3. Later ask questions whose answers depend on information scattered throughout the conversation.
4. Compare:
   - full context window
   - truncated context
   - vector RAG over raw turns
   - summarized conversation
   - Slowave memory injection
   - Slowave memory injection plus selected episodes

Metrics:

- answer accuracy
- injected token count
- answer accuracy per injected token
- latency
- cost
- retrieval precision
- stale or irrelevant memory injection
- robustness as conversation history grows

This benchmark directly tests whether Slowave can substitute for replaying entire conversation histories.

## Adversarial memory tests

The benchmark should include cases where Slowave must not create durable user memories.

Examples:

### Temporary instruction vs durable preference

> For this one task, use Python.

Should not become:

> User prefers Python.

### Roleplay contamination

> Pretend I'm a pirate who hates coffee.

Should not become:

> User hates coffee.

### Fictional content

> In my novel, Alice lives in Tokyo.

Should not become:

> User lives in Tokyo.

### Quoted third-party facts

> My friend says he loves Vim.

Should not become:

> User loves Vim.

Metrics:

- false memory extraction rate
- attribution accuracy
- temporal qualifier accuracy
- roleplay contamination rate
- fiction contamination rate

## Recommended benchmark phases

### Phase 1: REALTALK-derived longitudinal benchmark

Primary target for Slowave's core thesis.

Focus:

- extraction
- retrieval
- supersession
- promotion
- procedural memory
- cross-session injection

### Phase 2: Long-context replacement benchmark

Best product showcase.

Focus:

- accuracy vs token cost
- Slowave vs full context vs RAG
- latency and cost savings

### Phase 3: LMSYS scale benchmark

Best engineering robustness test.

Focus:

- scale
- memory pollution
- deduplication
- latency
- storage growth

### Phase 4: ShareChat multilingual benchmark

Best language-independent memory validation.

Focus:

- cross-lingual extraction and retrieval
- code-switching
- multilingual preference continuity

## Suggested report bundle

Every benchmark run should report memory-layer and answer-layer metrics separately.

### Extraction

- extraction precision
- extraction recall
- memory type accuracy
- attribution accuracy
- temporal qualifier accuracy

### Retrieval

- Recall@1 / Recall@3 / Recall@5
- MRR
- nDCG
- irrelevant retrieval rate

### Memory lifecycle

- promotion true positive rate
- promotion false positive rate
- supersession accuracy
- stale memory retrieval rate
- forgetting/suppression accuracy

### Injection

- injected memory precision
- missing memory rate
- irrelevant injected token count
- answer accuracy per injected token

### System behavior

- retrieval latency
- write latency
- promotion latency
- storage growth
- degradation with memory count

## Bottom line

REALTALK is likely the strongest single benchmark source because it evaluates persistent, evolving memory over time. The Long-Context Replacement Benchmark is the clearest showcase of Slowave's practical value because it directly asks whether Slowave can avoid replaying entire conversation histories. LMSYS-Chat-1M is ideal for large-scale robustness and scalability. ShareChat is best for validating multilingual, language-independent memory behavior.

The key benchmark design requirement is to transform these datasets into controlled memory evaluation tasks with explicit gold labels for what should be remembered, ignored, retrieved, suppressed, promoted, superseded, and injected.