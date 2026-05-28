# Slowave Evaluation Strategy

Date: 2026-05-28

## Summary

Slowave should be evaluated as a long-term learning substrate, not only as a retrieval or RAG system. Existing datasets such as LongMemEval and LoCoMo remain useful, but they should not be the north star. They mostly test whether a system can recover facts from past context. Slowave also needs to be measured on whether it accumulates, distills, scopes, updates, forgets, and applies durable knowledge over time.

The recommended approach is to use a portfolio of evaluations:

1. Keep LongMemEval and LoCoMo as external compatibility and regression benchmarks.
2. Build a Slowave-native longitudinal synthetic benchmark.
3. Create a dogfooding gold set from real daily usage across Cline, Claude Code, and Claude Desktop.
4. Run ablations to prove which parts of the architecture actually help.
5. Track system-health metrics to detect long-term memory rot.

The north-star evaluation question should be:

> Does Slowave reliably improve future agent behavior using compact, current, correctly scoped knowledge accumulated from past interactions?

## Why LongMemEval and LoCoMo Are Not Enough

LongMemEval and LoCoMo are valuable because they provide familiar external reference points and allow comparison against retrieval-oriented memory systems. They are useful for answering questions like:

- Can the system recover a past fact?
- Can it answer a question using long-context conversation history?
- Does a retrieval layer surface relevant prior utterances?

However, Slowave is intended to do more than pure retrieval. It accumulates knowledge and distills it over time. Therefore, Slowave also needs evaluation for:

- knowledge accumulation across repeated sessions;
- semantic abstraction from multiple events;
- schema quality;
- temporal adaptation when preferences or facts change;
- contradiction handling;
- scoped memory boundaries;
- context gating;
- decay and forgetting;
- long-term robustness as memory grows;
- downstream behavioral improvement.

LongMemEval and LoCoMo should therefore remain part of the evaluation suite, but they should be clearly labeled as retrieval-oriented benchmarks rather than complete measures of Slowave's intended capability.

## Evaluation Portfolio

### Layer A: Existing Benchmark Compatibility

Use datasets such as:

- LongMemEval;
- LoCoMo;
- Mem0-style memory evaluations, where relevant;
- RAG-style QA datasets, where relevant.

Purpose:

- compare against known baselines;
- catch obvious retrieval regressions;
- make Slowave legible to external audiences;
- measure basic memory lookup performance.

Recommended framing:

> Retrieval-oriented benchmark performance, not full Slowave capability.

These benchmarks should be treated as regression and credibility instruments, not as the primary optimization target.

### Layer B: Slowave-Native Synthetic Longitudinal Benchmark

This should become the main controlled benchmark.

Create simulated users and projects across many sessions. Each synthetic world should include:

- repeated preferences;
- changing preferences;
- contradictions;
- stale facts;
- project-specific facts;
- cross-project interference risks;
- procedural knowledge;
- personal style;
- recurring tasks;
- rare but important constraints;
- accidental or demo noise;
- long gaps between relevant events.

The benchmark should evaluate whether Slowave:

1. stores the right events;
2. distills the right schemas;
3. retrieves the right memory at the right time;
4. suppresses irrelevant or stale memory;
5. updates or decays outdated beliefs;
6. supports better downstream answers and actions.

Example synthetic scenario:

```text
Session 1:
User says they prefer pytest and small focused tests.

Session 3:
User says that in project A they prefer integration tests first.

Session 8:
User says they no longer want broad integration tests in project A because they became slow.

Session 14:
User asks: "Add tests for this bug."

Expected memory behavior:
- Recall the project A-specific current preference.
- Avoid applying the old integration-test-first preference.
- Avoid overusing the generic pytest preference if it is not useful.
- Suggest focused tests unless integration coverage is necessary.
```

The probe should often require behavioral use of memory, not just answering a direct question like "what does the user prefer?".

### Layer C: Dogfooding / Real Longitudinal Evaluation

Slowave's real advantage is daily use, so real usage should become a core evaluation source.

Since Slowave is already used through Cline, Claude Code, and Claude Desktop, add a lightweight labeling pipeline for real memory activations.

For each agent response where Slowave context was injected, log:

- user query;
- retrieved schemas and events;
- activation scores and reasons;
- final assistant behavior;
- whether the assistant used memory;
- whether memory was helpful, irrelevant, stale, missing, or harmful.

Suggested label schema:

```text
memory_helpfulness:
  3 = essential / clearly improved answer
  2 = useful
  1 = harmless but marginal
  0 = irrelevant
 -1 = distracting
 -2 = stale, wrong, or harmful

memory_need:
  required
  useful
  optional
  unnecessary

failure_type:
  missed_memory
  stale_memory
  over_recall
  wrong_scope
  contradiction_not_resolved
  privacy_or_boundary_issue
  bad_distillation
  bad_decay
```

This produces a product-relevant metric:

> In real use, how often does Slowave improve the assistant instead of distracting it?

### Layer D: Ablation and Baseline Tests

To understand whether Slowave's architecture is helping, compare multiple configurations:

1. no memory;
2. raw event retrieval only;
3. schema/distilled memory only;
4. raw plus schema memory;
5. Slowave with decay disabled;
6. Slowave with consolidation disabled;
7. Slowave with project scoping disabled;
8. full current Slowave.

Important comparisons:

```text
raw retrieval vs distilled schemas
distilled schemas vs full context gating
full Slowave vs no memory
full Slowave vs naive vector memory
```

Without ablations, it will be hard to know whether distillation, consolidation, temporal weighting, and context gating are actually adding value.

### Layer E: System Health Metrics

Slowave also needs internal operational metrics because long-term memory systems can slowly degrade.

Track:

- number of events;
- number of episodes;
- number of schemas;
- schema support count distribution;
- contradiction count;
- decay rate;
- activation distribution;
- average context payload size;
- duplicate schema rate;
- stale schema survival rate;
- cross-project contamination rate;
- consolidation latency;
- recall latency;
- token overhead;
- memory write/read ratio.

Examples of pathologies these metrics should reveal:

- If schema count grows linearly forever, distillation is failing.
- If activation always returns high-salience generic preferences, context gating is failing.
- If stale schemas remain active after repeated contradiction, update or decay is failing.
- If many schemas have support count 1 forever, consolidation may be too eager.

## Capability Taxonomy

Slowave's intended capabilities should be evaluated separately.

### 1. Episodic Recall

Can Slowave recover a specific past event?

Example:

> What command did we run to fix the migration issue last week?

Metrics:

- recall@k;
- answer exactness;
- source correctness.

This overlaps most with LongMemEval and LoCoMo.

### 2. Semantic Accumulation

Can Slowave infer stable knowledge from multiple events?

Example:

> User repeatedly dislikes style-only code review comments.

Expected schema:

> User prefers blunt architectural feedback over style-only nitpicks.

Metrics:

- schema precision;
- schema recall;
- support count correctness;
- duplicate rate;
- overgeneralization rate.

### 3. Temporal Adaptation

Can Slowave handle changed beliefs or preferences?

Example:

```text
Earlier: user prefers Jest.
Later: user moved project to Vitest.
Now: user asks to add a test.
```

Expected behavior:

- use Vitest for the relevant project;
- do not blindly apply the old Jest memory;
- preserve old memory as historically true but inactive or stale if needed.

Metrics:

- current-fact accuracy;
- stale-memory suppression;
- contradiction resolution accuracy.

### 4. Scope Control

Can Slowave apply memories only within the correct boundary?

Example:

```text
Project A uses Python and pytest.
Project B uses TypeScript and Vitest.
```

When operating in project B, Slowave should not inject project A testing conventions.

Metrics:

- cross-scope false positive rate;
- project-specific recall accuracy;
- global-vs-local classification accuracy.

### 5. Context Gating

Can Slowave choose not to inject memory?

A good memory system should often stay silent.

Example:

> What is 2+2?

Expected behavior:

- no irrelevant memory payload;
- no personality or project-context contamination.

Metrics:

- unnecessary recall rate;
- context payload usefulness;
- precision of memory injection.

### 6. Compression and Distillation

Can Slowave convert many raw events into compact reusable claims?

Example:

> Fifty turns about code-review style become one durable preference.

Metrics:

- compression ratio;
- retained utility;
- factual faithfulness;
- schema granularity;
- duplicate or fragmentation rate.

### 7. Long-Term Robustness

Does Slowave still work after weeks or months of mixed usage?

Metrics:

- performance as memory corpus grows;
- recall latency;
- precision over time;
- stale schema rate;
- memory pollution rate.

## Slowave Longitudinal Eval Dataset

Slowave should have its own benchmark, initially private if necessary.

Possible names:

- Slowave Longitudinal Eval;
- Slowave Memory Gym;
- SlowBench;
- Personal Memory Eval;
- Agent Memory Lifecycle Eval.

Each test case should include sessions plus one or more probes.

Example structure:

```json
{
  "scenario_id": "project_testing_preference_change",
  "sessions": [
    {
      "time": "2026-01-01T10:00:00Z",
      "project": "alpha",
      "messages": [
        {
          "role": "user",
          "content": "I prefer integration tests before unit tests."
        },
        {
          "role": "assistant",
          "content": "..."
        }
      ]
    },
    {
      "time": "2026-02-01T10:00:00Z",
      "project": "alpha",
      "messages": [
        {
          "role": "user",
          "content": "Actually, integration tests are too slow here. Prefer focused unit tests unless necessary."
        }
      ]
    }
  ],
  "probe": {
    "time": "2026-03-01T10:00:00Z",
    "project": "alpha",
    "user_message": "Add tests for this parser bug."
  },
  "expected": {
    "should_recall": [
      "Prefer focused unit tests unless integration is necessary."
    ],
    "should_not_recall": [
      "Prefer integration tests before unit tests."
    ],
    "expected_behavior": [
      "Suggest focused unit tests.",
      "Avoid old integration-first preference."
    ]
  }
}
```

## Scoring Modes

Each probe should be scored at two levels: memory behavior and final assistant behavior.

### Memory-Level Scoring

Questions:

- Did Slowave retrieve the necessary memory?
- Did it retrieve stale or irrelevant memory?
- Was the memory correctly scoped?
- Was activation justified?
- Did the rendered context stay compact?

Metrics:

```text
memory_precision
memory_recall
stale_recall_rate
wrong_scope_rate
context_tokens
activation_rank_of_gold_memory
```

### Behavior-Level Scoring

Questions:

- Did the assistant act better because of memory?
- Did it follow the current preference or constraint?
- Did it avoid stale or irrelevant memories?
- Was the final answer useful?

Metrics:

```text
task_success
personalization_success
constraint_adherence
stale_behavior_rate
harmful_memory_rate
```

Behavior-level scoring should matter more than retrieval-only scoring. A memory can be retrieved but not used; alternatively, the assistant may succeed without memory. Both layers are needed for diagnosis.

## Dogfood Gold Set

Create a small gold set from real usage.

Every week, sample 20 to 50 real interactions from Cline, Claude Code, and Claude Desktop where memory could matter. Label:

1. what memory should have been used;
2. what memory should not have been used;
3. whether the response improved;
4. whether anything stale or wrong was present;
5. whether anything important was missing.

Suggested categories:

- coding style;
- project conventions;
- architecture preferences;
- recurring commands;
- personal preferences;
- past decisions;
- open questions;
- warnings or lessons;
- environment facts;
- tooling constraints.

This gold set will likely be the highest-signal benchmark because it reflects actual product use.

## Adversarial Cases

Memory systems fail in predictable ways. The Slowave-native benchmark should explicitly test them.

### Contradiction

```text
Earlier: "I prefer concise answers."
Later: "For architecture discussions, be detailed."
Probe: user asks an architecture question.
Expected: detailed answer, not generic concision.
```

### Scope Leakage

```text
A project-specific preference from project A is available while working in project B.
Expected: no leakage unless the preference is globally marked.
```

### Overgeneralization

```text
One-off statement becomes durable preference.
Expected: no high-confidence schema yet.
```

### Under-Consolidation

```text
Repeated pattern never becomes a schema.
Expected: stable schema after enough support.
```

### Memory Pollution

```text
Temporary demo or test data enters memory.
Expected: low salience or natural decay.
```

### Retrieval Distraction

```text
Simple factual query unrelated to memory.
Expected: no memory context.
```

### Long Gap

```text
Important old constraint is not mentioned for months.
Expected: still retrievable if stable and relevant.
```

### Preference Evolution

```text
User changes their mind gradually over five sessions.
Expected: nuanced current schema, not abrupt contradiction chaos.
```

## Public and Private Scorecards

Maintain two scorecards.

### Public / Standard Scorecard

Use:

- LongMemEval;
- LoCoMo;
- Mem0-style comparisons;
- latency and cost metrics.

This answers:

> How does Slowave compare to other memory or RAG systems on known tasks?

### Private / Slowave-Native Scorecard

Use:

- synthetic longitudinal evaluation;
- dogfood gold set;
- ablations;
- system-health metrics.

This answers:

> Is Slowave becoming a better long-term agent memory system?

Both scorecards are necessary. Public benchmarks support external communication; private Slowave-native benchmarks prevent optimizing toward a retrieval wrapper.

## Recommended North-Star Metrics

### 1. Memory Helpfulness Rate

From dogfooding labels:

```text
% of memory-injected responses where memory was useful or essential
```

Possible target:

```text
>70% useful or essential
<5% harmful or stale
```

### 2. Missing Important Memory Rate

```text
% of interactions where a known relevant memory existed but was not surfaced
```

Goal: trend downward over time.

### 3. Stale / Wrong Memory Rate

```text
% of retrieved memories that are outdated, contradicted, or wrongly scoped
```

Possible target:

```text
<3-5%
```

### 4. Longitudinal Task Success

On the Slowave-native synthetic benchmark:

```text
% of probes where final assistant behavior correctly uses accumulated memory
```

This should be one of the most important benchmark metrics.

### 5. Context Efficiency

Possible formulations:

```text
useful memory per token injected
average memory context tokens for successful tasks
```

A good memory system is not only accurate; it is compact.

## Suggested Evaluation Architecture

```text
evals/
  datasets/
    longmemeval/
    locomo/
    slowave_longitudinal/
    dogfood_gold/
  runners/
    run_longmemeval.py
    run_locomo.py
    run_longitudinal.py
    run_dogfood_replay.py
  scorers/
    memory_retrieval.py
    behavior_judge.py
    stale_memory.py
    scope_control.py
    schema_quality.py
  baselines/
    no_memory.py
    raw_vector.py
    raw_event_only.py
    schema_only.py
    full_slowave.py
  reports/
    scorecard.md
    trend_dashboard.json
```

Core evaluation flow:

```text
1. Reset isolated Slowave database.
2. Replay historical or synthetic sessions.
3. Trigger consolidation as configured.
4. Run probe.
5. Capture:
   - slowave_context output;
   - slowave_recall output;
   - final assistant response, if applicable.
6. Score retrieval.
7. Score behavior.
8. Compare against baselines and ablations.
```

Evaluations should use deterministic snapshots and isolated stores. They should not depend on the live personal memory store unless explicitly running dogfood replay.

## Use of LLM Judges

Some scoring will require semantic judgment. LLM judges can be used, but their output should be structured and constrained.

Example judge output:

```json
{
  "uses_current_preference": true,
  "uses_stale_preference": false,
  "mentions_irrelevant_memory": false,
  "task_success": 4,
  "explanation": "The answer follows the newer project-specific testing preference and avoids the stale integration-first rule."
}
```

Use deterministic checks where possible:

- whether expected schema IDs appeared;
- whether stale schema IDs appeared;
- activation rank;
- project scope;
- token count;
- latency;
- number of retrieved memories.

Use LLM judges for behavior quality, and deterministic metrics for memory mechanics.

## 30 / 60 / 90 Day Plan

### First 30 Days: Measurement Spine

Build:

1. LongMemEval and LoCoMo runners as regression baselines;
2. 20 to 30 Slowave-native synthetic scenarios;
3. basic ablations:
   - no memory;
   - raw only;
   - schema only;
   - full Slowave;
4. a simple scorecard:
   - memory precision and recall;
   - stale recall;
   - wrong-scope recall;
   - context token count;
   - task success judged by rubric.

Outcome:

> One command can show whether a change improved or harmed memory behavior.

### Days 30-60: Dogfood Gold Set

Build:

1. export/replay pipeline from real Cline, Claude Code, and Claude Desktop usage;
2. manual labeling UI or JSON-based labeling files;
3. weekly sampling of real interactions;
4. dogfood scorecard.

Outcome:

> Slowave can be measured against real daily work.

### Days 60-90: Longitudinal Stress Testing

Build:

1. larger synthetic worlds with 100+ sessions each;
2. time-gap simulation;
3. memory pollution tests;
4. contradiction and evolution tests;
5. dashboards over memory growth and health.

Outcome:

> Slowave can be measured for health and utility as memory accumulates.

## Final Recommendation

Adopt this evaluation strategy:

1. keep LongMemEval and LoCoMo as external and regression benchmarks;
2. create a Slowave-native longitudinal synthetic benchmark focused on accumulation, distillation, temporal adaptation, scope, and context gating;
3. build a dogfooding gold set from real daily use;
4. run ablations aggressively to prove distillation and context gating add value;
5. track system-health metrics to detect long-term memory rot;
6. use behavior-level success as the main target, not retrieval-only accuracy.

LongMemEval and LoCoMo test memory as a database. Slowave should be evaluated as a learning substrate.
