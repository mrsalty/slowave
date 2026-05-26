#!/usr/bin/env python3
"""Sweep replay assignment_threshold on a single LoCoMo conversation.

Reports episodes / prototypes / edges for each threshold so we can see at
what point the online k-means stops collapsing into a single super-cluster.
This is the upstream gate on Stage 1 spreading activation: if the
replay engine produces ~1 prototype, the prototype graph is empty, and
spreading has nothing to traverse.
"""
from __future__ import annotations
import json, os, sys, tempfile, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault('KMP_DUPLICATE_LIB_OK', 'TRUE')
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

import logging
logging.basicConfig(level=logging.WARNING)
for _n in ('sentence_transformers','transformers','httpx','httpcore',
           'huggingface_hub','filelock','tqdm'):
    logging.getLogger(_n).setLevel(logging.ERROR)

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.latent.replay_engine import ReplayConfig
from slowave.latent.retrieval import RetrievalConfig
from slowave.latent.salience import SalienceConfig
from slowave.llm.base import LLMBackendConfig
from slowave.symbolic.encoder import EncoderConfig, TextEncoder
from tests.integration.locomo_eval import _parse_ts


def run_threshold(sample, enc, threshold: float, *, sample_size: int = 2048,
                  max_protos: int = 128):
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    cfg = SlowaveConfig(
        db_path=db_path, dim=enc.dim, llm=LLMBackendConfig(),
        salience=SalienceConfig(tau_seconds=86400 * 30),
        replay=ReplayConfig(
            assignment_threshold=threshold,
            sample_size=sample_size,
            max_prototypes_per_replay=max_protos,
        ),
        retrieval=RetrievalConfig(),
        disable_llm=True, disable_encoder=False,
    )
    eng = SlowaveEngine(cfg, shared_encoder=enc)
    conv = sample['conversation']
    speaker_a = conv.get('speaker_a', 'A')
    nsess = len([k for k in conv if k.startswith('session_') and 'date' not in k])
    for i in range(1, nsess + 1):
        turns = conv.get('session_%d' % i, [])
        date_str = conv.get('session_%d_date_time' % i, '')
        if not turns:
            continue
        sid = eng.session_start(agent='locomo', project=sample['sample_id'])
        session_ts = _parse_ts(date_str) if date_str else int(time.time())
        for turn in turns:
            text = str(turn.get('text', '')).strip()
            if not text:
                continue
            role = 'user_message' if str(turn.get('speaker', '')) == speaker_a else 'assistant_message'
            eng.raw_log.append(
                session_id=sid, ts=session_ts,
                type=role, content=text, embedding=enc.encode(text),
            )
        eng.session_end(sid, consolidate=False)
    eng.replay_engine.replay_once()
    eps = eng.episodic.count()
    pro = eng.semantic.count()
    ed = eng.graph.edge_count()
    # Distribution: episodes per prototype.
    conn = eng.db.connect()
    rows = conn.execute(
        'SELECT prototype_id, COUNT(*) AS n FROM episode_prototype_map '
        'GROUP BY prototype_id ORDER BY n DESC'
    ).fetchall()
    sizes = [int(r['n']) for r in rows]
    eng.close()
    for ext in ('', '-wal', '-shm'):
        p = db_path + ext
        if os.path.exists(p):
            os.remove(p)
    return eps, pro, ed, sizes


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--dataset', default='data/locomo/locomo10.json')
    p.add_argument('--conv', type=int, default=0,
                   help='Index of conversation to sweep (0..9)')
    p.add_argument('--thresholds', nargs='+', type=float,
                   default=[0.65, 0.75, 0.82, 0.85, 0.88, 0.90, 0.92, 0.95, 0.97])
    args = p.parse_args()

    dataset_path = args.dataset
    if not os.path.isabs(dataset_path):
        dataset_path = str(REPO_ROOT / dataset_path)
    samples = json.load(open(dataset_path))
    sample = samples[args.conv]
    print(f"Conversation: {sample.get('sample_id', args.conv)}")

    print('Loading encoder...', end=' ', flush=True)
    enc = TextEncoder(EncoderConfig()); _ = enc.dim
    print(f'OK (dim={enc.dim})')

    print()
    print(f'{"threshold":>10}  {"episodes":>8}  {"prototypes":>10}  {"edges":>6}  size_dist (top 8)')
    print('-' * 80)
    for t in args.thresholds:
        eps, pro, ed, sizes = run_threshold(sample, enc, t)
        head = sizes[:8]
        print(f'{t:>10.2f}  {eps:>8d}  {pro:>10d}  {ed:>6d}  {head}')


if __name__ == '__main__':
    main()
