#!/usr/bin/env python3
"""Debug Stage 3: inspect predictive seed on PR-1 scenario."""
from __future__ import annotations
import os, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault('KMP_DUPLICATE_LIB_OK', 'TRUE')
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

import logging
logging.basicConfig(level=logging.WARNING)
for n in ('sentence_transformers','transformers','httpx','httpcore','huggingface_hub','filelock','tqdm'):
    logging.getLogger(n).setLevel(logging.ERROR)

import numpy as np
from slowave.symbolic.encoder import EncoderConfig, TextEncoder
from tests.temporal_eval.harness import TemporalHarness
from tests.temporal_eval.scenarios import completion, decay

enc = TextEncoder(EncoderConfig()); _ = enc.dim
h = TemporalHarness(shared_encoder=enc, consolidate=False, tau_days=7.0, ablation='no_llm')
decay.run_all(h)
m = h.eng.transition_model
print('trained_steps:', m.trained_steps)
print('episodes:', h.eng.episodic.count(),
      'protos:', h.eng.semantic.count(),
      'edges:', h.eng.graph.edge_count())

q = enc.encode('Where does the user work?')
h.eng.refresh_indices()
pred = m.predict(q.reshape(1, -1)).reshape(-1)
pn = float(np.linalg.norm(pred))
print('pred norm:', pn)
pred = pred / (pn + 1e-9)
print('q . pred cosine:', float(q.dot(pred)))

ep_sc, ep_id = h.eng.episodic.search(q, top_k=8)
pr_sc, pr_id = h.eng.episodic.search(pred, top_k=8)
for label, sc, idx in [('q', ep_sc, ep_id), ('pred', pr_sc, pr_id)]:
    print(f'--- via {label}')
    for s, eid in zip(sc.tolist(), idx.tolist()):
        if eid == -1:
            continue
        et = h.eng.episode_text.get(eid)
        text = (et.content_text if et else '').replace('\n', ' / ')
        print(f'  cos={s:.3f}  text={text[:80]!r}')
h.close()
