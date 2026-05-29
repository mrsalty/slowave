# Design: the brain-only architecture

This document records the architectural decision to remove LLM calls from the memory loop.

## The decision

An internal three-way benchmark comparison (LongMemEval, 180 questions) showed LLM-augmented schema extraction *regressing* the latent mechanisms:

```
                     cosine-only   latent (brain)   LLM-augmented
                     -----------   --------------   -------------
knowledge-update          63.3%            90.0%           63.3%
temporal-reasoning        63.3%            66.7%           56.7%
multi-session             50.0%            53.3%           53.3%
single-session-ass        73.3%            73.3%           73.3%
single-session-user       93.3%            93.3%           93.3%
single-session-pref       20.0%            20.0%           26.7%
OVERALL                   60.6%            66.1%           61.1%
```

The latent path **beats the LLM-augmented path by +5 pp aggregate**. On knowledge-update the LLM **destroys +27 pp** of the latent mechanisms' contribution (latent 90% → with LLM 63%). The only category where the LLM helps is single-session-preference (+6.7 pp), which is structurally a meta-cognition task, not a retrieval task.

Conclusion: the LLM was acting as a noise source merged into the retrieval ranker, not as a memory operator.

## The thesis

> **Memory is a latent geometric process.** Encoding, consolidation, abstraction, contradiction detection, and retrieval all happen in continuous vector space, shaped by mechanisms well characterised in neuroscience: Hebbian learning, slow-wave replay, salience decay, predictive coding, pattern completion, pattern separation.
>
> **Language is an output channel.** It translates retrieved latent state into something a downstream language model or human can consume. The translation step happens at most once per query, at the end — never during ingest, never during consolidation, never as part of the retrieval pipeline.

This separates Slowave from every system on LongMemEval and LoCoMo at the time. Mem0, Zep, Letta, HippoRAG, A-MEM, MemoryBank all use LLMs as memory operators. Slowave removes the LLM from the memory loop entirely.

## Position vs the field

| Axis | Mem0 (SOTA at evaluation time) | Slowave |
|---|---|---|
| LongMemEval accuracy | ~94.4% | **70.0%** |
| Per-ingest LLM calls | many | **zero** |
| Per-query LLM calls | 1 (frontier model) | **zero** |
| Runs on a Mac | needs API key | **fully local** |
| Privacy | data goes to cloud | **stays on device** |
| Architectural claim | engineered RAG | **brain-inspired geometry** |

The honest position: *70% of SOTA accuracy at $0 per query, fully local, ablation-clean. The ~24 pp gap is concentrated in meta-cognition tasks (preference abstraction, cross-session aggregation) that require LLM extraction by construction — not in retrieval.*

## What this gives up

- **Preference abstraction (LME 20%)**: implicit preferences are not automatically abstracted into queryable schema entries. This is structurally a meta-cognition problem, not a retrieval problem.
- **Cross-session aggregation**: summing quantities across episodes is not in scope for a pure retrieval layer.
- **Accuracy ceiling**: not competing with Mem0's accuracy numbers; competing on a different axis (compute, locality, privacy).

These limitations are documented in [limitations.md](limitations.md).

## Outcome

LLM path removed in v0.1.5. Current benchmark results with brain-only path:

| Benchmark | Score | vs cosine baseline |
|---|---:|---:|
| LongMemEval (500q, with consolidation) | **70.0%** | +10 pp |
| LoCoMo (1986q, with consolidation) | **74.6%** | +6.6 pp |
| DMR (100q) | **95.0%** | — |

Full details in [benchmarks.md](benchmarks.md). Current architecture in [architecture.md](architecture.md).
