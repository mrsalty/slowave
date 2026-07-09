#!/usr/bin/env python3
"""Phase 4 diagnostic: analyze graph edge composition on LoCoMo limit=3.

Answers the 7 diagnostic questions from plans/03-graph.md.
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
from tests.integration.locomo_eval import _parse_ts

DS_PATH = REPO_ROOT / "data" / "locomo" / "locomo10.json"
with open(DS_PATH) as f:
    dataset = json.load(f)
shared_encoder = TextEncoder(EncoderConfig())

LIMIT = 3
print(f"Running Phase 4 diagnostics on {LIMIT} LoCoMo conversations...")
print(
    f"Default GraphConfig: λ₁={GraphConfig().lambda_similarity}, λ₂={GraphConfig().lambda_transition}, λ₃={GraphConfig().lambda_coactivation}"
)
print(
    f"accumulate_decay={GraphConfig().accumulate_decay}, homeostatic_target={GraphConfig().homeostatic_target}, prune_ratio={GraphConfig().prune_ratio}"
)
print()

all_diags = []
for si, sample in enumerate(dataset[:LIMIT]):
    conv = sample["conversation"]
    conv_id = str(sample.get("sample_id", "?"))
    print(f"  conv {si+1}/{LIMIT} ({conv_id})...", end=" ", flush=True)
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
            graph=GraphConfig(),
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
                    "user_message" if speaker == conv.get("speaker_a", "A") else "assistant_message"
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
        eng.consolidate_once(triggered_by="diagnose")
        eng.replay_engine.self_supervise()
        diag = eng.replay_engine.graph.diagnose()
        diag["conv_id"] = conv_id
        all_diags.append(diag)
        print(f"{diag['edge_count']} edges, sim_dom={diag['similarity_dominance_pct']:.1f}%")
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass

# Aggregate
print()
print("=" * 60)
print("AGGREGATE DIAGNOSTICS")
print("=" * 60)

import numpy as np

edge_counts = [d["edge_count"] for d in all_diags]
sim_dom_pcts = [d["similarity_dominance_pct"] for d in all_diags]

print(f"\nTotal conversations: {len(all_diags)}")
print(
    f"Edge counts: min={min(edge_counts)}, max={max(edge_counts)}, mean={np.mean(edge_counts):.0f}"
)

# Component fractions aggregation
sim_means = [
    d["component_fractions"]["similarity"]["mean"] for d in all_diags if d["component_fractions"]
]
sim_medians = [
    d["component_fractions"]["similarity"]["median"] for d in all_diags if d["component_fractions"]
]
trans_means = [
    d["component_fractions"]["transition"]["mean"] for d in all_diags if d["component_fractions"]
]
coact_means = [
    d["component_fractions"]["coactivation"]["mean"] for d in all_diags if d["component_fractions"]
]

print("\n--- Q1: Edge weight decomposition ---")
print(f"Similarity fraction: mean={np.mean(sim_means):.3f}, median={np.mean(sim_medians):.3f}")
print(f"Transition  fraction: mean={np.mean(trans_means):.3f}")
print(f"Coactivation fraction: mean={np.mean(coact_means):.3f}")

print("\n--- Q1b: Similarity dominance ---")
print(f"% edges with >80% similarity: mean={np.mean(sim_dom_pcts):.1f}%")

# Symmetry
sym_medians = [d["symmetry"]["median"] for d in all_diags if d["symmetry"]["median"] is not None]
if sym_medians:
    print("\n--- Q6: Edge directionality ---")
    print(f"Median symmetry index: {np.mean(sym_medians):.3f}")
    print("(0=fully directional, 1=fully symmetric)")

# Degree distribution
print("\n--- Q7: Degree distribution ---")
for d in all_diags:
    dd = d["degree_distribution"]
    if dd:
        print(
            f"  {d['conv_id']}: {dd['n_sources']} sources, mean={dd['mean']:.1f}, median={dd['median']:.1f}, max={dd['max']}, p95={dd['p95']:.1f}"
        )

# GO/NO-GO decision
print()
print("=" * 60)
avg_sim_dom = np.mean(sim_dom_pcts) if sim_dom_pcts else 0
if avg_sim_dom > 80:
    print(f"GO/NO-GO: NO-GO — {avg_sim_dom:.1f}% edges are similarity-dominated (>80%)")
    print("  → Graph is mostly cosine. Architectural fix needed, not parameter tuning.")
elif avg_sim_dom > 50:
    print(f"GO/NO-GO: CAUTION — {avg_sim_dom:.1f}% edges are similarity-dominated (>80%)")
    print("  → Significant cosine influence but transition/coactivation contribute.")
    print("  → Proceed with tuning but consider reducing λ₁.")
else:
    print(f"GO/NO-GO: GO — only {avg_sim_dom:.1f}% edges are similarity-dominated")
    print("  → Transition and coactivation contribute meaningfully. Proceed to tuning.")
print("=" * 60)
