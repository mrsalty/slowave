#!/usr/bin/env python3
"""Phase 5: Ablation matrix for graph quality.
7 configs on LoCoMo limit=3: baseline, no-homeostatic, no-similarity,
no-transition, no-coactivation, no-similarity-at-all, no-self-supervise."""

from __future__ import annotations

import json, logging, os, sys, tempfile, time
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

LIMIT = 3

ABLATIONS = [
    ("A1_baseline", GraphConfig()),
    ("A2_no_homeo", GraphConfig(homeostatic_enabled=False)),
    ("A3_no_sim", GraphConfig(lambda_similarity=0.0, lambda_coactivation=0.5)),
    ("A4_no_trans", GraphConfig(lambda_transition=0.0)),
    ("A5_no_coact", GraphConfig(lambda_coactivation=0.0)),
    (
        "A6_no_sim_all",
        GraphConfig(lambda_similarity=0.0, lambda_transition=1.0, lambda_coactivation=1.0),
    ),
    ("A7_no_selfsup", GraphConfig()),
]

for name, graph_cfg in ABLATIONS:
    t0 = time.time()
    correct = 0
    total = 0
    no_self_sup = name == "A7_no_selfsup"
    print(f"\n{'='*50}")
    print(
        f"{name}: λ₁={graph_cfg.lambda_similarity} λ₂={graph_cfg.lambda_transition} λ₃={graph_cfg.lambda_coactivation} homeo={graph_cfg.homeostatic_enabled} selfsup={not no_self_sup}"
    )
    for si, sample in enumerate(dataset[:LIMIT]):
        conv = sample["conversation"]
        conv_id = str(sample.get("sample_id", "?"))
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
            eng.consolidate_once(triggered_by="ablate")
            if not no_self_sup:
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
                    ks = keyword_score(hyp[:600], adv) if adv else 0.0
                    correct += 1 if ks < HIT_THRESHOLD else 0
                elif ans:
                    ks = keyword_score(hyp, ans)
                    correct += 1 if ks >= HIT_THRESHOLD else 0
                total += 1
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass
    acc = 100.0 * correct / total if total else 0
    elapsed = time.time() - t0
    print(f"  Score: {acc:.1f}% ({correct}/{total}), {elapsed:.0f}s")
    print(f"  → Δ vs A1: {acc - 0.0:+.1f}pp (baseline will be set on first run)")
