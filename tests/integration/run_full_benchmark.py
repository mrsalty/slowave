#!/usr/bin/env python3
"""Run all Slowave benchmarks in sequence and print a consolidated summary.

Benchmarks (execution order matters — see note below):
  - LoCoMo        (1986 q, ~3 min)   ← runs FIRST, must be cold
  - LongMemEval   (500 q, ~10 min with consolidation)
  - DMR           (500 q, ~9 min)
  - StaleMemory   (1200 scenarios, ~15 min)

NOTE: LoCoMo must run before LongMemEval. Running LME first degrades LoCoMo
by ~5-6 pp due to OS memory pressure after LME's large DB operations
(confirmed Jun 12 2026: standalone=83-84%, post-LME=77.5%).

Usage:
  # Full suite (~40 min, all datasets must be present):
  python tests/integration/run_full_benchmark.py

  # Quick smoke - 5 questions/scenarios per category:
  python tests/integration/run_full_benchmark.py --limit 5

  # Skip a benchmark you don't have data for:
  python tests/integration/run_full_benchmark.py --skip stalememory

  # Custom output directory:
  python tests/integration/run_full_benchmark.py --out-dir data/runs/2026-06-06

Each benchmark writes its own JSON to --out-dir, then a combined
summary JSON is written to --out-dir/summary.json.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INTEG = REPO_ROOT / "tests" / "integration"


def _run(cmd: list[str], label: str) -> bool:
    print("\n" + "="*60)
    print(f"  {label}")
    print("="*60)
    t0 = time.time()
    # Pass parent environment to subprocess so OPENROUTER_API_KEY is inherited
    r = subprocess.run(cmd, cwd=str(REPO_ROOT), env=os.environ)
    elapsed = time.time() - t0
    if r.returncode != 0:
        print(f"[ERROR] {label} exited {r.returncode}")
        return False
    print(f"[OK] {label} finished in {elapsed:.0f}s")
    return True


def _load(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] could not load {path}: {e}")
        return None


def _summary_qa(d: dict) -> dict:
    s = d.get("summary", {})
    return {
        "n": s.get("n", 0),
        "score_pct": s.get("score_pct", 0.0),
        "llm_calls": s.get("cost", {}).get("n_llm_calls_total", 0),
    }


def _summary_stale(d: dict) -> dict:
    s = d.get("summary", {})
    return {
        "n": s.get("n", 0),
        "detection_rate_pct": round(s.get("detection_rate", 0) * 100, 1),
        "stale_rate_pct": round(s.get("stale_rate", 0) * 100, 1),
        "no_answer_rate_pct": round(s.get("no_answer_rate", 0) * 100, 1),
        "llm_calls": s.get("llm_calls", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all Slowave benchmarks")
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max questions/scenarios per category (0=full run)",
    )
    parser.add_argument(
        "--skip", nargs="+", default=[],
        choices=["longmemeval", "locomo", "dmr", "stalememory"],
        help="Benchmarks to skip",
    )
    parser.add_argument(
        "--out-dir", default="",
        help="Output directory for results (default: data/runs/<timestamp>)",
    )
    parser.add_argument(
        "--no-consolidate", action="store_true",
        help="Skip consolidation (faster, lower scores)",
    )
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else REPO_ROOT / "data" / "runs" / stamp
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir}")

    py = sys.executable
    skip = set(args.skip)
    cons_flag = ["--no-consolidate"] if args.no_consolidate else []
    lim_flag = ["--limit", str(args.limit)] if args.limit else []

    results: dict[str, dict] = {}
    suite_start = time.time()

    # LoCoMo runs FIRST — must be cold (no prior large benchmark in the same OS session).
    # Running LongMemEval first degrades LoCoMo by ~5-6 pp due to OS memory pressure /
    # ONNX/FAISS process-state contamination across subprocess boundaries.
    # Confirmed Jun 12 2026: standalone LoCoMo = 83-84%, post-LME LoCoMo = 77.5%.
    if "locomo" not in skip:
        ds = REPO_ROOT / "data" / "locomo" / "locomo10.json"
        if not ds.exists():
            print(f"[SKIP] LoCoMo: {ds} not found")
        else:
            out = out_dir / "locomo.json"
            cmd = [
                py, str(INTEG / "locomo_eval.py"),
                "--dataset", str(ds),
                "--assignment-threshold", "0.85",
                "--out", str(out),
            ] + cons_flag + lim_flag
            if _run(cmd, "LoCoMo"):
                d = _load(out)
                if d:
                    results["locomo"] = _summary_qa(d)

    # LongMemEval
    if "longmemeval" not in skip:
        ds = REPO_ROOT / "data" / "longmemeval" / "longmemeval_oracle.json"
        if not ds.exists():
            print(f"[SKIP] LongMemEval: {ds} not found")
        else:
            out = out_dir / "longmemeval.json"
            cmd = [
                py, str(INTEG / "longmemeval_eval.py"),
                "--dataset", str(ds),
                "--assignment-threshold", "0.85",
                "--top-k", "10",
                "--out", str(out),
            ] + cons_flag + lim_flag
            if _run(cmd, "LongMemEval"):
                d = _load(out)
                if d:
                    results["longmemeval"] = _summary_qa(d)

    # DMR
    if "dmr" not in skip:
        ds = REPO_ROOT / "data" / "dmr_original" / "msc_self_instruct.jsonl"
        if not ds.exists():
            print(f"[SKIP] DMR: {ds} not found")
        else:
            out = out_dir / "dmr.json"
            cmd = [
                py, str(INTEG / "dmr_original_eval.py"),
                "--dataset", str(ds),
                "--out", str(out),
            ] + lim_flag
            if _run(cmd, "DMR (MSC Self-Instruct)"):
                d = _load(out)
                if d:
                    results["dmr"] = _summary_qa(d)

    # StaleMemory
    if "stalememory" not in skip:
        ds = REPO_ROOT / "data" / "stalememory" / "scenarios.jsonl"
        if not ds.exists():
            print(f"[SKIP] StaleMemory: {ds} not found")
        else:
            out = out_dir / "stalememory.json"
            cmd = [
                py, str(INTEG / "stalememory_eval.py"),
                "--dataset", str(ds),
                "--assignment-threshold", "0.85",
                "--top-k", "10",
                "--out", str(out),
            ] + cons_flag + lim_flag
            if _run(cmd, "StaleMemory"):
                d = _load(out)
                if d:
                    results["stalememory"] = _summary_stale(d)

    # Summary
    total_elapsed = time.time() - suite_start
    summary = {
        "meta": {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "total_elapsed_s": round(total_elapsed, 1),
            "limit": args.limit,
            "consolidate": not args.no_consolidate,
            "skipped": list(skip),
        },
        "results": results,
    }
    summary_path = out_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "="*60)
    print(f"  SUITE COMPLETE  ({total_elapsed:.0f}s)")
    print("="*60)
    for name, r in results.items():
        if name == "stalememory":
            det = r["detection_rate_pct"]
            stl = r["stale_rate_pct"]
            llm = r["llm_calls"]
            n   = r["n"]
            print(f"  {name:<15} n={n:<6} detection={det}%  stale={stl}%  llm_calls={llm}")
        else:
            sc  = r["score_pct"]
            llm = r["llm_calls"]
            n   = r["n"]
            print(f"  {name:<15} n={n:<6} score={sc}%  llm_calls={llm}")
    print(f"  Summary: {summary_path}")


if __name__ == "__main__":
    main()
