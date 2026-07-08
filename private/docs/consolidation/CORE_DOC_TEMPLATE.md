# Core Algorithm Documentation Template & Generation Prompt

This document serves two purposes:
1. **A template** — the section structure every core doc should follow
2. **A generation prompt** — feed the «TEMPLATE» block to an LLM with access to the implementation to produce a high-quality module doc

---

## Why This Structure

Each core doc must support three downstream activities:

- **Measurement**: What knobs exist? What invariants must hold? What can be instrumented?
- **Benchmarking**: What parameter sweeps matter? What ablations test this component?
- **Improvement**: What are the known failure modes? What's the relationship to other modules?

The structure below ensures every document answers these questions.

---

## «TEMPLATE»

```
# NN — Module Name

## Overview

[2-4 sentences: what this module does, what mechanisms it combines, where it sits in the pipeline]

## Data Flow

[Input: what comes in. Output: what goes out. Optional: a simple ASCII diagram]

## Mathematical Formulation

### Phase 1: [Name]

[Formula in LaTeX \\( \\] notation]

Where:
- variable = config_param (default: `value`) — what it means

**Logical concept**: [1-2 sentences: WHY this formula exists, what problem it solves, what happens if you change the key parameter]

### Phase 2: [Name]
...

[Continue for all phases — one section per distinct step in the algorithm]

## Configuration

### `ConfigClassName`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `param_name` \\( symbol \\) | `type` | `default` | Description |

[Complete — every parameter in the dataclass must appear]

## Key Invariants

1. [Behavior that must always be true — e.g. "X always outranks Y"]
2. [Behavior that defines the mechanism — e.g. "only Z episodes receive reinforcement"]
3. ...

[Each invariant should be testable: you can write a unit test for it]

## Implementation Files

| File | What It Implements |
|------|-------------------|
| `slowave/latent/module.py` | Main class + algorithm |
| `slowave/latent/module.py` | Config dataclass |
| `slowave/core/services/module.py` | Higher-level wrapper (if applicable) |
| `slowave/latent/dependency.py` | Supporting class used by this module |
...

## Diagnostic Hooks

| Metric | What It Measures | How to Instrument |
|--------|-----------------|-------------------|
| `metric_name` | What this tells you about the module's behavior | Where in the code to add instrumentation |

[Every "does this component actually work?" question should map to at least one diagnostic hook]

## Parameter Sensitivity

| Parameter | Direction | Effect | Sweep Range |
|-----------|-----------|--------|-------------|
| `param` | ↑ / ↓ / non-linear | What happens when you increase it | Suggested values to try |

## Known Failure Modes

| Symptom | Likely Cause | Diagnostic Signal |
|---------|-------------|-------------------|
| Observable bad behavior | Root cause | Which metric would catch this |

## Relationship to Other Modules

| Module | Relationship |
|--------|-------------|
| `NN-other.md` | How this module depends on or feeds into the other |

[Cross-reference every module this one reads from or writes to]
```

---

## Generation Prompt

Copy-paste the block below into an LLM that has read-access to the Slowave implementation:

```
You are generating a core algorithm documentation file for the Slowave memory system.
The output format must follow the «TEMPLATE» above exactly.

Rules:
1. Read the implementation file(s) listed under "Implementation Files" thoroughly.
   Do NOT summarize from memory or from other docs — read the actual code.
2. Every formula must match the code exactly. If the code has a salience multiplier
   of (0.5 + 0.5 * sal), the formula must show that. No simplifications.
3. Every config parameter in the dataclass must appear in the Configuration table.
   Count them against the dataclass fields to verify completeness.
4. Every boolean config flag gets one row in Parameter Sensitivity.
5. Max-merge semantics (the code does `if discounted > prev: overwrite`) must be
   explicit in the formula text — don't say "merged" when the code does max-merge.
6. For each phase, explain the logical concept — WHY the formula is shaped that way.
   What problem does it solve? What would break if the parameter were 0?
7. Invariants must be testable. "X works well" is not an invariant. "X always
   outranks Y because ceiling < 1.0" is.
8. Diagnostic hooks should answer: "is this component actually doing anything?"
   The central hook is "what fraction of this component's contributions survive
   into the final output?"
9. If the implementation has a reserved-slot, diversity-cap, or promotion mechanism
   that rearranges the head AFTER ranking, document it in detail — these are the
   parts most likely to silently mask component contributions.
10. Include stub values for Parameter Sensitivity and Known Failure Modes.
    These will be filled in during measurement, but the structure must exist.

Module: [NAME]
Implementation entry point: [FILE:CLASS]
Goal: produce private/docs/consolidation/core/NN-name.md
```

---

## Quality Checklist

Before considering a doc complete, verify:

- [ ] All config parameters listed (count vs dataclass fields)
- [ ] Every formula matches the code (spot-check 3 random lines)
- [ ] Max-merge / min-merge / weighted-add semantics are explicit
- [ ] Every boolean flag has a sensitivity row
- [ ] At least one diagnostic hook answers "is this component dead weight or alive?"
- [ ] Invariants are falsifiable
- [ ] Implementation file table is complete
- [ ] Cross-references to other modules are present