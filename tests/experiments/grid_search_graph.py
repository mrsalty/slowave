#!/usr/bin/env python3
"""Grid search over GraphConfig — LoCoMo only.

Run: .venv/bin/python tests/integration/grid_search_graph.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
logging.basicConfig(level=logging.WARNING)
for _n in (
    "sentence_transformers",
    "transformers",
    "httpx",
    "httpcore",
    "huggingface_hub",
    "filelock",
    "tqdm",
):
    logging.getLogger(_n).setLevel(logging.ERROR)
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.latent.graph_manager import GraphConfig
from slowave.latent.replay_engine import ReplayConfig
from slowave.latent.retrieval import RetrievalConfig
from slowave.latent.salience import SalienceConfig
from slowave.symbolic.encoder import EncoderConfig, TextEncoder
from tests.integration.locomo_eval import _parse_ts, keyword_score

HIT_THRESHOLD = 0.5
DS_PATH = REPO_ROOT / "data" / "locomo" / "locomo10.json"
with open(DS_PATH) as f:
    dataset = json.load(f)
shared_encoder = TextEncoder(EncoderConfig())

CONFIGS = [
    ("overwrite", GraphConfig(homeostatic_enabled=False, accumulate_decay=0.0)),
    # current defaults
    (
        "d=0.3_t=0.5_r=0.2",
        GraphConfig(accumulate_decay=0.3, homeostatic_target=0.5, prune_ratio=0.2),
    ),
    # relaxed budget for sparser 128-proto graph
    (
        "d=0.3_t=1.0_r=0.1",
        GraphConfig(accumulate_decay=0.3, homeostatic_target=1.0, prune_ratio=0.1),
    ),
    (
        "d=0.5_t=1.0_r=0.1",
        GraphConfig(accumulate_decay=0.5, homeostatic_target=1.0, prune_ratio=0.1),
    ),
    (
        "d=0.5_t=0.8_r=0.1",
        GraphConfig(accumulate_decay=0.5, homeostatic_target=0.8, prune_ratio=0.1),
    ),
    (
        "d=0.3_t=0.8_r=0.1",
        GraphConfig(accumulate_decay=0.3, homeostatic_target=0.8, prune_ratio=0.1),
    ),
]


def run_one(name, graph_cfg):
    t0 = time.time()
    correct = 0
    total = 0
    for si, sample in enumerate(dataset):
        conv = sample["conversation"]
        conv_id = str(sample.get("sample_id", "?"))
        print(f"  conv {si+1}/10...", end=" ", flush=True)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            cfg = SlowaveConfig(
                db_path=db_path,
                dim=shared_encoder.dim,
                encoder=EncoderConfig(),
                salience=SalienceConfig(tau_seconds=86400 * 30),
                replay=ReplayConfig(
                    assignment_threshold=0.85,
                    sample_size=2048,
                    max_prototypes_per_replay=128,
                    use_multi_scale=True,
                ),
                retrieval=RetrievalConfig(
                    salience_weight=0.5, neighbor_top_k=6, use_multi_scale=True, use_transition=True
                ),
                graph=graph_cfg,
                disable_encoder=False,
            )
            eng = SlowaveEngine(cfg, shared_encoder=shared_encoder)
            nsess = len([k for k in conv if k.startswith("session_") and "date" not in k])
            for i in range(1, nsess + 1):
                turns = conv.get(f"session_{i}", [])
                date_str = conv.get(f"session_{i}_date_time", "")
                sts = _parse_ts(date_str) if date_str else None
                if not turns:
                    continue
                sid = eng.session_start(agent="locomo", scope=f"eval:{conv_id}")
                if sts:
                    c = eng.db.connect()
                    c.execute("UPDATE sessions SET started_ts=? WHERE id=?", (sts, sid))
                    c.commit()
                for turn in turns:
                    txt = str(turn.get("text", "")).strip()
                    if not txt:
                        continue
                    cap = str(turn.get("blip_caption", "")).strip()
                    if cap:
                        txt = txt + " [image: " + cap + "]"
                    speaker = str(turn.get("speaker", ""))
                    role = (
                        "user_message"
                        if speaker == conv.get("speaker_a", "A")
                        else "assistant_message"
                    )
                    eng.raw_log.append(
                        session_id=sid,
                        ts=sts or int(time.time()),
                        type=role,
                        content=txt,
                        embedding=shared_encoder.encode(txt),
                    )
                eng.session_end(sid, consolidate=False)
                if sts:
                    c = eng.db.connect()
                    c.execute(
                        "UPDATE episodic_memories SET ts=?,last_salience_ts=? WHERE event_id LIKE ? OR event_id LIKE ?",
                        (sts, sts, f"micro_{sid}_%", f"macro_{sid}"),
                    )
                    c.commit()
            eng.consolidate_once(triggered_by="grid_search")
            eng.replay_engine.self_supervise()
            for qa in sample["qa"]:
                q = str(qa.get("question", "")).strip()
                ans = str(qa.get("answer", "")) if qa.get("answer") is not None else ""
                adv = str(qa.get("adversarial_answer", ""))
                cat = int(qa.get("category", 1))
                r = eng.recall(q, top_k=12)
                hyp = " ".join(
                    [s.content_text for s in r.schemas]
                    + [ep["content_text"] for ep in r.episode_texts]
                )
                if cat == 5 and not ans:
                    # adversarial: NOT fooled = answer NOT found
                    ks = keyword_score(hyp[:600], adv) if adv else 0.0
                    correct += 1 if ks < HIT_THRESHOLD else 0
                elif ans:
                    # standard + adversarial-with-answer: keyword_score >= threshold
                    ks = keyword_score(hyp, ans)
                    correct += 1 if ks >= HIT_THRESHOLD else 0
                total += 1
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass
    elapsed = time.time() - t0
    score = 100.0 * correct / total if total else 0.0
    return {
        "config": name,
        "n": total,
        "score_pct": round(score, 2),
        "elapsed_s": round(elapsed, 1),
    }


if __name__ == "__main__":
    results = []
    for name, gcfg in CONFIGS:
        print(f"\n=== {name} ===", flush=True)
        r = run_one(name, gcfg)
        results.append(r)
        print(f"  Score: {r['score_pct']:.2f}% ({r['elapsed_s']:.0f}s)", flush=True)
    print("\n\n=== GRID RESULTS ===")
    print(f"{'Config':<30} {'Score':>8} {'Time':>6}")
    print("-" * 47)
    for r in results:
        print(f"{r['config']:<30} {r['score_pct']:>7.2f}% {r['elapsed_s']:>5.0f}s")
