"""WikiScenarios benchmark runner.

Same structure as tests/temporal_eval/run_temporal_eval.py.
"""

from __future__ import annotations

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

from slowave.symbolic.encoder import EncoderConfig, TextEncoder
from tests.temporal_eval.harness import ScenarioResult
from tests.wiki_scenarios.scenarios import SCENARIOS, run_scenario

ABLATIONS = ["full", "no_salience", "no_graph", "no_consolidation"]


def run_ablation(
    ablation: str, *, shared_enc: TextEncoder, limit: int = 0, tau_days: float = 7.0
) -> list[ScenarioResult]:
    scenarios = SCENARIOS if not limit else SCENARIOS[:limit]
    results: list[ScenarioResult] = []
    for s in scenarios:
        print(f"  [{ablation}] {s.id} ({s.family})...", end=" ", flush=True)
        t0 = time.time()
        try:
            r = run_scenario(s, shared_enc=shared_enc, ablation=ablation, tau_days=tau_days)
            results.append(r)
            print(f"{'HIT' if r.hit else 'miss'}  {time.time()-t0:.1f}s")
        except Exception as e:
            print(f"ERROR: {e}")
    return results


def print_report(all_results: dict[str, list[ScenarioResult]]) -> None:
    families = ["retrieval", "isolation", "generalization", "decay", "supersession", "completion"]
    print("\n" + "=" * 90)
    print("  SLOWAVE — WikiScenarios Benchmark")
    print("=" * 90)

    all_ids = list(dict.fromkeys(r.scenario_id for rs in all_results.values() for r in rs))
    abl_list = list(all_results.keys())

    # Header
    print(f"\n  {'ID':<6} {'Family':<16} {'Expected':<18}", end="")
    for a in abl_list:
        print(f"  {a:<16}", end="")
    print()
    print(f"  {'-'*6} {'-'*16} {'-'*18}", end="")
    for _ in abl_list:
        print(f"  {'-'*16}", end="")
    print()

    # Rows
    for sid in sorted(all_ids):
        first = next((r for rs in all_results.values() for r in rs if r.scenario_id == sid), None)
        if not first:
            continue
        print(f"  {sid:<6} {first.component:<16} {first.expected_keyword:<18}", end="")
        for abl in abl_list:
            r = next((r for r in all_results[abl] if r.scenario_id == sid), None)
            mark = ("HIT " if r.hit else "miss") if r else "n/a "
            print(f"  {mark:<16}", end="")
        print()

    # Per-ablation totals + per-family breakdown
    print()
    print(f"  {'Ablation':<20}  {'Score':<10}  Per family")
    print(f"  {'-'*20}  {'-'*10}  {'-'*50}")
    for abl, results in all_results.items():
        n = len(results)
        h = sum(1 for r in results if r.hit)
        by_fam = {}
        for r in results:
            by_fam.setdefault(r.component, []).append(r.hit)
        fam_str = "  ".join(
            f"{fam[0].upper()}:{sum(hits)}/{len(hits)}"
            for fam, hits in [(f, by_fam.get(f, [])) for f in families]
            if hits
        )
        print(f"  {abl:<20}  {h}/{n} ({100*h//max(n,1)}%)  {fam_str}")
    print("=" * 90 + "\n")


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
            }
            for r in results
        ]
        path = out_dir / f"wiki_scenarios_{abl}.json"
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"  Saved {path}")
