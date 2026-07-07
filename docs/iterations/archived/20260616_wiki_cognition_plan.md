# WikiCognition Benchmark: Plan & Progress

**Date**: 2026-06-16  
**Branch**: `feature/wiki-cognition-benchmark`  
**Objective**: Measure ALL slowave capabilities (retrieval, schema formation, generalization, temporal, supersession)

## Summary

WikiCognition = comprehensive benchmark using Wikipedia domain clusters (similar + dissimilar topics) to test:
- ✅ Schema formation from episodic streams
- ✅ Cross-episode generalization (coarse prototypes)
- ✅ Temporal dynamics (decay, reinforcement)
- ✅ Supersession (fact replacement)
- ✅ Spreading activation (graph-based retrieval)
- ✅ Scope isolation vs. cross-scope generalization

## 8 Stages

| Stage | Goal | Metrics |
|-------|------|---------|
| 1 | Episodic Ingestion | Speed, memory, paragraph count |
| 2 | Schema Formation | Count, confidence, consolidation rate |
| 3 | Within-Domain Retrieval | Precision@K, Recall@K |
| 4 | Cross-Domain Generalization | Promotion rate, shared schemas |
| 5 | Isolation | False positive rate across domains |
| 6 | Temporal Dynamics | Decay rate, reinforcement effect |
| 7 | Supersession | Detection rate, stale marking |
| 8 | Ablations | Component contribution (no_salience, no_graph, no_consolidation) |

## Corpus (12 Wikipedia pages)

```
ML Cluster:       Machine_learning, Deep_learning, Artificial_neural_network
Rome Cluster:     Ancient_Rome, Roman_Empire, Julius_Caesar  
Music Cluster:    Jazz, Blues, Improvisation
Controls:         Cell_(biology), Photosynthesis, Quantum_mechanics
```

## File Structure

```
tests/wiki_cognition/
├─ corpus.py              # WIKICOG_CORPUS
├─ queries.py             # 50 labeled queries
├─ harness.py             # WikiCognitionHarness
├─ stages/
│  ├─ stage1_ingest.py
│  ├─ stage2_consolidation.py
│  ├─ stage3_retrieval.py
│  ├─ stage4_generalization.py
│  ├─ stage5_isolation.py
│  ├─ stage6_temporal.py
│  ├─ stage7_supersession.py
│  └─ stage8_ablation.py
├─ run_wiki_cognition.py  # Orchestrator
└─ README.md
```

## Progress

### Phase 1: Foundation (Days 1-2)
- [ ] Directory structure + corpus.py
- [ ] queries.py (50 queries)
- [ ] harness.py (WikiCognitionHarness)
- [ ] Download Wikipedia pages
- **Validation**: Imports work, corpus loads

### Phase 2: Stages 1-3 (Days 2-4)
- [ ] stage1_ingest.py
- [ ] stage2_consolidation.py  
- [ ] stage3_retrieval.py
- **Validation**: Run stages, check metrics

### Phase 3: Stages 4-5 (Days 4-5)
- [ ] stage4_generalization.py
- [ ] stage5_isolation.py
- **Validation**: Similar domains generalize, dissimilar isolated

### Phase 4: Stages 6-7 (Days 5-6)
- [ ] stage6_temporal.py
- [ ] stage7_supersession.py
- **Validation**: Decay curves, supersession detected

### Phase 5: Stage 8 + Integration (Days 6-7)
- [ ] stage8_ablation.py
- [ ] run_wiki_cognition.py
- [ ] Output + docs
- **Validation**: Full end-to-end run
