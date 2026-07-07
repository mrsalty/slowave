#!/usr/bin/env python3
"""CLI entry point for WikiScenarios benchmark.

Usage:
  python tests/wiki_scenarios/run_wiki_scenarios.py
  python tests/wiki_scenarios/run_wiki_scenarios.py --ablation full --limit 4
  python tests/wiki_scenarios/run_wiki_scenarios.py --ablations full no_salience no_graph
  python tests/wiki_scenarios/run_wiki_scenarios.py --out-dir data/wiki_scenarios/
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

import logging
for _n in ("sentence_transformers","transformers","httpx","httpcore",
           "huggingface_hub","filelock","tqdm","onnxruntime"):
    logging.getLogger(_n).setLevel(logging.ERROR)

from slowave.symbolic.encoder import EncoderConfig, TextEncoder
from tests.wiki_scenarios.runner import run_ablation, print_report, save_results, ABLATIONS

REPO_ROOT = Path(__file__).parent.parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="WikiScenarios Benchmark")
    parser.add_argument("--ablations", nargs="+", default=["full"],
                        choices=ABLATIONS,
                        help="Ablations to run (default: full)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max scenarios to run (0 = all 15)")
    parser.add_argument("--tau-days", type=float, default=7.0,
                        help="Salience decay half-life in days")
    parser.add_argument("--out-dir", default="data/wiki_scenarios",
                        help="Output directory for JSON files")
    args = parser.parse_args()

    out_dir = REPO_ROOT / args.out_dir

    print("Loading encoder (shared across all scenarios)...")
    enc = TextEncoder(EncoderConfig())

    all_results = {}
    t_total = time.time()
    for abl in args.ablations:
        print(f"\n── Ablation: {abl} ──────────────────────────────────────────")
        t0 = time.time()
        all_results[abl] = run_ablation(abl, shared_enc=enc,
                                        limit=args.limit, tau_days=args.tau_days)
        print(f"  Done in {time.time()-t0:.1f}s")

    print_report(all_results)
    save_results(all_results, out_dir)
    print(f"Total time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
