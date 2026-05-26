# Benchmarking Slowave

Reproduce the numbers from the README. All commands run from the repo root with the venv active.

```bash
source .venv/bin/activate
```

The brain-only path (`--schema-mode latent`) requires no LLM and no API key.

---

## LongMemEval (500 questions, 6 categories)

```bash
# Full run — brain-only, ~3 min, zero LLM
python tests/integration/longmemeval_eval.py \
  --schema-mode latent \
  --out data/longmemeval/runs/lme_brainonly.json

# Cosine-only baseline (~1 min)
python tests/integration/longmemeval_eval.py \
  --schema-mode latent --no-graph-expansion --no-transition \
  --out data/longmemeval/runs/lme_cosine.json

# Smoke (10 questions per category, ~20 s)
python tests/integration/longmemeval_eval.py \
  --schema-mode latent --limit 10 \
  --out data/longmemeval/runs/lme_smoke.json
```

**Expected (full, brain-only):** 70.00% — 168s on a Mac.

### Per-stage ablations

```bash
--no-multi-scale        # Stage 9 off
--no-transition         # Stage 3 off
--no-graph-expansion    # Stage 1 spreading off
--no-self-supervise     # Stage 5 off
--no-pattern-separation # Stage 8 off (already default off)
--schema-mode llm       # legacy LLM-extraction path (needs Ollama)
```

### Category filter

```bash
python tests/integration/longmemeval_eval.py \
  --schema-mode latent \
  --categories knowledge-update temporal-reasoning \
  --out data/longmemeval/runs/lme_focused.json
# Categories: knowledge-update | single-session-preference |
#             multi-session | single-session-user |
#             single-session-assistant | temporal-reasoning
```

---

## LoCoMo (1986 questions, 5 categories)

```bash
# Full run — brain-only, ~5 min, zero LLM
python tests/integration/locomo_eval.py \
  --schema-mode latent --assignment-threshold 0.65 \
  --out data/locomo/runs/locomo_brainonly.json

# Cosine-only baseline (~1 min)
python tests/integration/locomo_eval.py \
  --no-consolidate \
  --out data/locomo/runs/locomo_cosine.json

# Smoke (1 conversation, ~10 s)
python tests/integration/locomo_eval.py \
  --schema-mode latent --limit 1 --assignment-threshold 0.65 \
  --out data/locomo/runs/locomo_smoke.json
```

**Expected (full, brain-only):** 75.48% F1 — ~5 min.

### Per-stage ablations

```bash
--no-multi-scale
--no-transition --no-self-supervise
--no-graph-expansion
--no-salience-rerank
--schema-mode llm   # legacy path (needs Ollama: ollama pull qwen2.5:7b-instruct)
```

### Category filter

```bash
python tests/integration/locomo_eval.py \
  --schema-mode latent --categories 2 3 --assignment-threshold 0.65 \
  --out data/locomo/runs/locomo_temporal.json
# Categories: 1=single-session  2=temporal  3=commonsense
#             4=multi-session   5=adversarial
```

---

## Inspecting results

```bash
python -c "
import json, sys
d = json.load(open(sys.argv[1]))
s = d.get('summary', {})
print('score:', s.get('score_pct'), '%   F1:', s.get('avg_f1'))
for k, v in (s.get('by_category') or {}).items():
    print(f'  {v.get(\"name\", k):<28} n={v[\"n\"]:<5} {v[\"score_pct\"]:>5.1f}%')
print()
cost = d.get('cost', {})
if cost:
    print('LLM calls:', cost.get('llm_calls'), '  tokens:', cost.get('llm_tokens'),
          '  est $:', cost.get('estimated_cost_usd'))
" path/to/run.json
```

---

## 2WikiMultiHopQA (100 examples, QA/RAG task)

Multi-hop question answering benchmark comparing Slowave's document retrieval against published HippoRAG results.

```bash
# Full run — brain-only, ~1 min, zero LLM
python run_2wiki_benchmark.py

# Smaller run (10 examples, ~10 s)
python run_2wiki_benchmark.py --num-examples 10

# Custom dataset
python run_2wiki_benchmark.py --dataset path/to/dataset.json --num-examples 50
```

**Expected (full, 100 examples):** 82.5% Recall@5 — ~42 seconds on a Mac.

**Comparison to HippoRAG**:
- **Recall@5**: 82.5% (Slowave) vs 87% (HippoRAG) — only 5.2% gap
- **Recall@10**: 100% (Slowave perfect coverage)
- **MRR**: 0.75 (Slowave) vs 0.78 (HippoRAG) — 3.5% gap

See [`docs/benchmarks/hipporag-qa-comparison.md`](benchmarks/hipporag-qa-comparison.md) for full methodology and analysis.

---

## Sanity check

Before reporting any new number, verify the cosine baseline still reproduces ~60% on LongMemEval and ~68% on LoCoMo. If it doesn't, something broke the cosine path — fix before trusting the augmented run.
