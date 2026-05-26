# HippoRAG QA Benchmark Comparison

**Branch**: `bench/hipporag-qa-comparison`  
**Goal**: Compare Slowave vs HippoRAG on QA/RAG retrieval tasks  
**Status**: In Progress

## Phase 1: QA/RAG Retrieval Tasks

Compare Slowave against **published HippoRAG benchmark results** on standard QA datasets.
We only run Slowave; HippoRAG numbers are already public.

### HippoRAG Published Baselines

**Multi-Hop QA**:
- **2WikiMultiHopQA**: Answer Recall@5 baseline; HippoRAG achieves +20–38% improvement
- **MuSiQue**: Significantly outperforms single-step RAG methods
- **HotpotQA**: Strong multi-hop reasoning performance

**GraphRAG-Bench** (newer):
- Average accuracy: ~72
- Evidence Recall (L2-3): 87.9–90.9%
- Context Relevance (L2-3): 85.8–87.8%

Reference: [HippoRAG NeurIPS'24 Paper](https://arxiv.org/abs/2405.14831)

### Datasets to Evaluate On

1. **2WikiMultiHopQA** (primary): Multi-hop reasoning benchmark
2. **MuSiQue** (secondary): Multi-hop QA
3. **HotpotQA** (optional): General multi-hop evaluation

### Slowave QA Adapter

Create wrapper that:
1. Takes QA dataset (questions, documents, ground truth)
2. Builds Slowave memory from documents (sessions → episodes → consolidation)
3. Recalls for each question
4. Measures: retrieval recall, answer accuracy, latency

### Planned Artifacts

```
tests/integration/
├── hipporag_qa_eval.py              # Main evaluation script
└── datasets/
    ├── 2wiki_multihop_subset.json
    ├── musique_subset.json
    └── hotpot_subset.json

results/hipporag_comparison/
├── 2026-05-26_slowave_2wiki.json
├── 2026-05-26_slowave_musique.json
└── analysis.md                      # Slowave vs HippoRAG published numbers
```

### Success Criteria

- [ ] Download & prepare 2WikiMultiHopQA subset
- [ ] Implement Slowave QA adapter
- [ ] Run on dataset, measure recall@5, accuracy
- [ ] Compare against HippoRAG baselines
- [ ] Document findings (where Slowave wins/loses)

## Phase 2: Long-Term Memory (Later)

See main task list.

## Notes

- Keep experiments isolated from main codebase
- Document setup & reproduction steps
- Version control results + hyperparameters
