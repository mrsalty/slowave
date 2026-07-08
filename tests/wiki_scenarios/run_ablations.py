#!/usr/bin/env python3
"""Retrieval ablation matrix for WikiScenarios.

Runs all 18 scenarios once per ablation config, varying one boolean
retrieval flag at a time. Prints a hit/miss matrix and per-family
score table, then saves JSON results to data/wiki_scenarios/ablations/.

Usage:
  python tests/wiki_scenarios/run_ablations.py
  python tests/wiki_scenarios/run_ablations.py --limit 6
"""

from __future__ import annotations

import argparse
import dataclasses
import json
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

for _n in (
    "sentence_transformers",
    "transformers",
    "httpx",
    "httpcore",
    "huggingface_hub",
    "filelock",
    "tqdm",
    "onnxruntime",
):
    logging.getLogger(_n).setLevel(logging.ERROR)

from slowave.latent.retrieval import RetrievalConfig
from slowave.symbolic.encoder import EncoderConfig, TextEncoder
from tests.temporal_eval.harness import ScenarioResult
from tests.wiki_scenarios.scenarios import SCENARIOS, run_scenario

REPO_ROOT = Path(__file__).parent.parent.parent
FAMILIES = ["retrieval", "isolation", "generalization", "decay", "supersession", "completion"]

# Baseline matches the harness full config: salience_weight=0.4, all components on.
_BASE = RetrievalConfig(salience_weight=0.4)

ABLATIONS: dict[str, RetrievalConfig] = {
    "full": _BASE,
    "no_spreading": dataclasses.replace(_BASE, use_spreading=False),
    "no_temporal": dataclasses.replace(_BASE, use_temporal=False),
    "no_salience_gate": dataclasses.replace(_BASE, salience_gate=False),
    "no_transition": dataclasses.replace(_BASE, use_transition=False),
    "no_multiscale": dataclasses.replace(_BASE, use_multi_scale=False),
    "cosine_only": dataclasses.replace(
        _BASE,
        use_spreading=False,
        use_temporal=False,
        salience_gate=False,
        use_transition=False,
        use_multi_scale=False,
    ),
}


def run_ablation(
    name: str,
    cfg: RetrievalConfig,
    *,
    enc: TextEncoder,
    limit: int,
    tau_days: float,
) -> list[ScenarioResult]:
    scenarios = SCENARIOS if not limit else SCENARIOS[:limit]
    results: list[ScenarioResult] = []
    for s in scenarios:
        print(f"  [{name:16s}] {s.id} ({s.family})...", end=" ", flush=True)
        t0 = time.time()
        try:
            r = run_scenario(
                s,
                shared_enc=enc,
                ablation="full",  # harness ablation string unused (overridden by cfg)
                tau_days=tau_days,
                retrieval_cfg_override=cfg,
            )
            results.append(r)
            saves = ""
            if r.detail.get("query_diagnostics"):
                n = r.detail["query_diagnostics"].get("graph_only_saves", 0)
                saves = f" saves={n}" if n else ""
            print(f"{'HIT' if r.hit else 'miss'}  {time.time() - t0:.1f}s{saves}")
        except Exception as e:
            print(f"ERROR: {e}")
    return results


def print_matrix(all_results: dict[str, list[ScenarioResult]]) -> None:
    abl_list = list(all_results.keys())
    all_ids = list(dict.fromkeys(r.scenario_id for rs in all_results.values() for r in rs))

    col_w = 14
    header_w = 22

    print("\n" + "=" * (header_w + col_w * len(abl_list)))
    print("  RETRIEVAL ABLATION MATRIX — WikiScenarios")
    print("=" * (header_w + col_w * len(abl_list)))

    # Header
    print(f"\n  {'Scenario':<{header_w}}", end="")
    for a in abl_list:
        print(f"  {a:<{col_w - 2}}", end="")
    print()
    print(f"  {'-' * header_w}", end="")
    for _ in abl_list:
        print(f"  {'-' * (col_w - 2)}", end="")
    print()

    # Rows
    for sid in sorted(all_ids):
        first = next((r for rs in all_results.values() for r in rs if r.scenario_id == sid), None)
        if not first:
            continue
        label = f"{sid} ({first.component[:6]})"
        print(f"  {label:<{header_w}}", end="")
        for abl in abl_list:
            r = next((r for r in all_results[abl] if r.scenario_id == sid), None)
            mark = ("HIT " if r.hit else "miss") if r else "n/a "
            print(f"  {mark:<{col_w - 2}}", end="")
        print()

    # Score row
    print(f"\n  {'TOTAL':<{header_w}}", end="")
    scores: dict[str, int] = {}
    for abl, results in all_results.items():
        n = len(results)
        h = sum(1 for r in results if r.hit)
        scores[abl] = h
        print(f"  {h}/{n} ({100 * h // max(n, 1)}%){'':<{col_w - 10}}", end="")
    print()

    # Delta row
    full_score = scores.get("full", 0)
    print(f"  {'Δ vs full':<{header_w}}", end="")
    for abl in abl_list:
        d = scores.get(abl, 0) - full_score
        mark = "--" if abl == "full" else (f"+{d}" if d > 0 else str(d))
        print(f"  {mark:<{col_w - 2}}", end="")
    print()

    # Per-family breakdown
    print(f"\n  {'Family':<{header_w}}", end="")
    for a in abl_list:
        print(f"  {a:<{col_w - 2}}", end="")
    print()
    print(f"  {'-' * header_w}", end="")
    for _ in abl_list:
        print(f"  {'-' * (col_w - 2)}", end="")
    print()
    for fam in FAMILIES:
        print(f"  {fam:<{header_w}}", end="")
        for abl, results in all_results.items():
            hits = [r.hit for r in results if r.component == fam]
            if hits:
                print(f"  {sum(hits)}/{len(hits)}{'':<{col_w - 5}}", end="")
            else:
                print(f"  {'n/a':<{col_w - 2}}", end="")
        print()

    print("=" * (header_w + col_w * len(abl_list)) + "\n")


def save_results(all_results: dict[str, list[ScenarioResult]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for abl, results in all_results.items():
        payload = [
            {
                "scenario_id": r.scenario_id,
                "family": r.component,
                "expected_keyword": r.expected_keyword,
                "hit": r.hit,
                "hypothesis": r.hypothesis,
                "detail": r.detail,
                "query_diagnostics": r.detail.get("query_diagnostics"),
            }
            for r in results
        ]
        path = out_dir / f"ablation_{abl}.json"
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
    print(f"  Saved {len(all_results)} ablation files to {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval Ablation Matrix")
    parser.add_argument("--limit", type=int, default=0, help="Max scenarios (0 = all 18)")
    parser.add_argument("--tau-days", type=float, default=7.0)
    parser.add_argument(
        "--out-dir", default="data/wiki_scenarios/ablations", help="Output directory"
    )
    parser.add_argument(
        "--ablations",
        nargs="+",
        default=list(ABLATIONS.keys()),
        choices=list(ABLATIONS.keys()),
    )
    args = parser.parse_args()

    out_dir = REPO_ROOT / args.out_dir

    print("Loading encoder (shared across all ablations)...")
    enc = TextEncoder(EncoderConfig())

    all_results: dict[str, list[ScenarioResult]] = {}
    t_total = time.time()

    for name in args.ablations:
        cfg = ABLATIONS[name]
        print(f"\n── {name} ──────────────────────────────────────────")
        t0 = time.time()
        all_results[name] = run_ablation(
            name, cfg, enc=enc, limit=args.limit, tau_days=args.tau_days
        )
        print(f"  Done in {time.time() - t0:.1f}s")

    print_matrix(all_results)
    save_results(all_results, out_dir)
    print(f"Total time: {time.time() - t_total:.1f}s")


if __name__ == "__main__":
    main()
