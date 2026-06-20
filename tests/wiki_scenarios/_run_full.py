#!/usr/bin/env python3
"""Run full WikiScenarios benchmark, one ablation at a time."""
import sys, os, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import logging
for n in ("sentence_transformers","transformers","httpx","httpcore","huggingface_hub","filelock","tqdm","onnxruntime"):
    logging.getLogger(n).setLevel(logging.ERROR)

from slowave.symbolic.encoder import EncoderConfig, TextEncoder
from tests.wiki_scenarios.runner import run_ablation, print_report, save_results

out_dir = Path(__file__).parent / "results"
ABLATIONS = ["full", "no_salience", "no_graph", "no_consolidation"]

print("Loading encoder...")
enc = TextEncoder(EncoderConfig())

all_results = {}
t_total = time.time()
for abl in ABLATIONS:
    print(f"\n── Ablation: {abl} ──")
    t0 = time.time()
    all_results[abl] = run_ablation(abl, shared_enc=enc, limit=0, tau_days=7.0)
    print(f"  Done in {time.time()-t0:.1f}s")

print_report(all_results)
save_results(all_results, out_dir)
print(f"Total time: {time.time()-t_total:.1f}s")
