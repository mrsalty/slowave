# HippoRAG QA Benchmark Comparison

**Branch**: `bench/hipporag-qa-comparison`  
**Goal**: Compare Slowave vs HippoRAG on QA/RAG retrieval tasks  
**Status**: In Progress

## Phase 1: QA/RAG Retrieval Tasks

Compare Slowave and HippoRAG on standard QA benchmarks.

### Benchmarks to Use

- **GraphRAG-Bench**: Multi-hop reasoning, knowledge graphs
- **CRAG**: Comprehensive RAG benchmark
- **Domain-specific QA**: (TBD - select a few focused datasets)

### Metrics

- Retrieval precision/recall
- Multi-hop reasoning accuracy
- End-to-end QA accuracy
- Latency
- Memory footprint

### HippoRAG Setup

Repository: [OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG)

```bash
# Clone and install
git clone https://github.com/OSU-NLP-Group/HippoRAG.git
pip install -e .
```

### Slowave QA Adapter

Need to create a wrapper that:
1. Takes QA dataset (questions, documents, ground truth answers)
2. Builds Slowave memory from documents
3. Recalls for each question
4. Measures retrieval/QA metrics

### Planned Artifacts

```
tests/integration/
├── hipporag_qa_eval.py          # Main evaluation script
└── datasets/
    ├── graphrag_bench_subset.json
    └── crag_subset.json

results/
└── hipporag_comparison/
    ├── 2026-05-26_baseline.json
    └── analysis.md
```

## Phase 2: Long-Term Memory (Later)

See main task list.

## Notes

- Keep experiments isolated from main codebase
- Document setup & reproduction steps
- Version control results + hyperparameters
