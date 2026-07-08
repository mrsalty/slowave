# WikiScenarios — Black-Box Capability Benchmark

Measures **slowave** across five capability families using Wikipedia-domain text and
black-box keyword-hit scoring. No DB introspection, no scope parsing — ground truth
lives in the *text of the answer*.

## Quick Start

```bash
# Full benchmark (all 4 ablations, ~8 min)
python tests/wiki_scenarios/run_wiki_scenarios.py

# Single ablation + limit
python tests/wiki_scenarios/run_wiki_scenarios.py --ablations full --limit 6

# Specific ablations, custom output
python tests/wiki_scenarios/run_wiki_scenarios.py \
  --ablations full no_salience no_graph --out-dir results/
```

Requires the Wikipedia corpus cache.  If it's missing, build it once:

```bash
python tests/wiki_scenarios/corpus.py
```

## Five Capability Families (15 Scenarios)

| Family | Tests | What It Measures |
|--------|-------|-----------------|
| **R — Retrieval** | R-1 → R-4 | Domain-specific content surfaces correctly (ML, Rome, Music, Controls) |
| **I — Isolation** | I-1 → I-3 | Unrelated domain content does NOT contaminate retrieval |
| **G — Generalization** | G-1 → G-3 | Content from separate sessions (similar pages) retrieves together after consolidation |
| **D — Decay** | D-1 → D-3 | Newer content outranks older content after simulated time decay |
| **S — Supersession** | S-1 → S-2 | New fact replaces old fact in retrieval when "now uses" pattern signals an update |

## Scoring

Each scenario has an `expected_keyword` (must appear in top-K result text) and a
`anti_keyword` (must NOT appear).  Result text = schema content + episode texts.

```
hit = expected_keyword in result_text AND anti_keyword NOT in result_text
```

No internal DB reads.  No scope string matching.  Just text.

## Ablations

To measure which component contributes what:

| Ablation | What It Removes | Expected Impact |
|----------|----------------|-----------------|
| `full` | *(nothing)* | Baseline |
| `no_salience` | Salience weighting | D-family episodic salience collapses (0.41 → 0.01) |
| `no_graph` | Spreading activation | No effect on direct-match queries; would matter for indirect-cue / completion |
| `no_consolidation` | Schema formation (forces consolidate=False) | G and S families lose all automatic schemas |

## Corpus (12 Wikipedia Pages)

```
ML Cluster:      Machine_learning, Deep_learning, Artificial_neural_network
Rome Cluster:    Ancient_Rome, Roman_Empire, Julius_Caesar
Music Cluster:   Jazz, Blues, Improvisation
Controls:        Cell_(biology), Photosynthesis, Quantum_mechanics
```

Text is pre-fetched and cached in `data/corpus_cache.json` (~741 KB, 1201 paragraphs).

## Files

```
tests/wiki_scenarios/
├── corpus.py                  # 12-page corpus + fetch/cache logic
├── harness.py                 # WikiHarness (wraps TemporalHarness)
├── scenarios.py               # 15 scenario definitions + runner logic
├── runner.py                  # Ablation loop + report + JSON output
├── run_wiki_scenarios.py      # CLI entry point
├── data/corpus_cache.json     # Pre-cached Wikipedia text
└── README.md                  # This file
```

## Design Principles

1. **Black-box** — hit/miss comes from `result.schemas[*].content_text` and
   `result.episode_texts[*]["content_text"]` only.
2. **No scope parsing** — expected/anti keywords are real words from Wikipedia text.
3. **One scenario, one harness** — fresh tempfile DB per scenario (no cross-contamination).
4. **Shared encoder** — loaded once, passed to all harness instances.
5. **Same pattern as TemporalEval** — `tests/temporal_eval/harness.py` is the reference.

## Adding New Scenarios

1. Add a `WikiScenario` entry with a unique id and one of the five family names.
2. Add the page-to-query mapping in the relevant family runner function (`_retrieval`,
   `_isolation`, etc.).
3. Verify your expected/anti keywords appear in the cached corpus.  Use:
   ```python
   from tests.wiki_scenarios.corpus import paragraphs_for
   text = " ".join(paragraphs_for("Machine_learning"))
   print("network" in text.lower())  # must be True
   print("Caesar" in text.lower())   # must be False
   ```
