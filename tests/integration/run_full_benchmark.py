#!/usr/bin/env python3
"""Run all Slowave benchmarks in sequence and print a consolidated summary.

Benchmarks (execution order matters — see note below):
  - WikiScenarios  (15 scenarios, ~2 min)  ← no dataset needed
  - Temporal       (18 scenarios, ~1 min)  ← no dataset needed
  - LoCoMo         (1986 q, ~3 min)
  - LongMemEval    (500 q, ~10 min with consolidation)
  - DMR            (500 q, ~9 min)
  - StaleMemory    (1200 scenarios, ~15 min)

NOTE: LoCoMo must run before LongMemEval. Running LME first degrades LoCoMo
by ~5-6 pp due to OS memory pressure after LME's large DB operations
(confirmed Jun 12 2026: standalone=83-84%, post-LME=77.5%).

Usage:
  # Full suite (~40 min, external datasets must be present):
  python tests/integration/run_full_benchmark.py

  # Quick smoke - 5 questions/scenarios per category:
  python tests/integration/run_full_benchmark.py --limit 5

  # Skip benchmarks you don't have data for:
  python tests/integration/run_full_benchmark.py --skip stalememory locomo

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
WIKI = REPO_ROOT / "tests" / "wiki_scenarios"
TEMPORAL = REPO_ROOT / "tests" / "temporal_eval"


def _run(cmd: list[str], label: str) -> bool:
    print("\n" + "="*60)
    print(f"  {label}")
    print("="*60)
    t0 = time.time()
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
    }


def _summary_stale(d: dict) -> dict:
    s = d.get("summary", {})
    return {
        "n": s.get("n", 0),
        "detection_rate_pct": round(s.get("detection_rate", 0) * 100, 1),
        "stale_rate_pct": round(s.get("stale_rate", 0) * 100, 1),
        "no_answer_rate_pct": round(s.get("no_answer_rate", 0) * 100, 1),
    }


def _load_prev_summaries(runs_dir: Path, current_dir: Path, limit: int, n: int = 5) -> list[dict]:
    """Return up to n previous summary.json dicts, oldest-first, matching limit setting."""
    if not runs_dir.exists():
        return []
    candidates = []
    for d in sorted(runs_dir.iterdir()):
        if d == current_dir or not d.is_dir():
            continue
        summary_path = d / "summary.json"
        if not summary_path.exists():
            continue
        try:
            with open(summary_path) as f:
                data = json.load(f)
            if data.get("meta", {}).get("limit", 0) != limit:
                continue
            candidates.append(data)
        except Exception:
            continue
    return candidates[-n:]


def _print_trend(current: dict[str, dict], prev_summaries: list[dict]) -> None:
    """Print a trend table comparing current results against previous runs."""
    if not prev_summaries:
        return

    def _primary(name: str, r: dict) -> float | None:
        if r is None:
            return None
        return r.get("detection_rate_pct" if name == "stalememory" else "score_pct")

    def _short_date(summary: dict) -> str:
        ts = summary.get("meta", {}).get("created_at", "")
        try:
            dt = datetime.fromisoformat(ts)
            return dt.strftime("%b %d")
        except Exception:
            return "?"

    W = 9  # column width for score values
    print()
    label_count = len(prev_summaries)
    print(f"  TREND  (vs {label_count} previous comparable run{'s' if label_count > 1 else ''})")
    sep = "  " + "─" * (17 + (W + 2) * label_count + W + 2 + 7)
    print(sep)
    header = f"  {'benchmark':<15}"
    for s in prev_summaries:
        header += f"  {_short_date(s):>{W}}"
    header += f"  {'now':>{W}}  {'Δ':>5}"
    print(header)
    print(sep)

    for name, r in current.items():
        cur_val = _primary(name, r)
        if cur_val is None:
            continue
        prev_vals = [_primary(name, s.get("results", {}).get(name)) for s in prev_summaries]
        row = f"  {name:<15}"
        for v in prev_vals:
            row += f"  {(f'{v:.1f}%') if v is not None else 'n/a':>{W}}"
        row += f"  {cur_val:.1f}%"
        last = next((v for v in reversed(prev_vals) if v is not None), None)
        if last is not None:
            delta = cur_val - last
            if abs(delta) < 0.5:
                marker = f"  ~{abs(delta):.1f}"
            elif delta > 0:
                marker = f"  ↑{delta:.1f}"
            else:
                marker = f"  ↓{abs(delta):.1f}"
            row += marker
        print(row)

    print(sep)


def _summary_wiki(scenarios: list) -> dict:
    n = len(scenarios)
    h = sum(1 for s in scenarios if s.get("hit"))
    return {"n": n, "score_pct": round(100 * h / max(n, 1), 1)}


def _summary_temporal(d: dict) -> dict:
    scenarios = [s for rs in d.get("results", {}).values() for s in rs]
    n = len(scenarios)
    h = sum(1 for s in scenarios if s.get("hit"))
    return {"n": n, "score_pct": round(100 * h / max(n, 1), 1)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all Slowave benchmarks")
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max questions/scenarios per category (0=full run)",
    )
    parser.add_argument(
        "--skip", nargs="+", default=[],
        choices=["wiki", "temporal", "longmemeval", "locomo", "dmr", "stalememory"],
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

    # WikiScenarios — self-contained, no external dataset needed
    if "wiki" not in skip:
        wiki_out = out_dir / "wiki_scenarios_full.json"
        cmd = [
            py, str(WIKI / "run_wiki_scenarios.py"),
            "--ablations", "full",
            "--out-dir", str(out_dir),
        ] + lim_flag
        if _run(cmd, "WikiScenarios"):
            d = _load(wiki_out)
            if d:
                results["wiki"] = _summary_wiki(d)

    # Temporal — self-contained, no external dataset needed
    if "temporal" not in skip:
        temporal_out = out_dir / "temporal.json"
        cmd = [
            py, str(TEMPORAL / "run_temporal_eval.py"),
            "--ablation", "full",
            "--out", str(temporal_out),
        ]
        if _run(cmd, "Temporal"):
            d = _load(temporal_out)
            if d:
                results["temporal"] = _summary_temporal(d)

    # LoCoMo runs before LME to keep the run order consistent across benchmarks.
    # NOTE: empirical data (Jun 2026, 14 runs) shows LoCoMo scores HIGHER when LME ran
    # just before it in the same OS session (~81-83%) than when it runs cold (~76-81%,
    # mean 78.8%, stdev 2.3%). The earlier comment claiming post-LME hurts LoCoMo was
    # incorrect — the effect is the opposite, likely ONNX/encoder warmup benefits.
    # Cold-run variance of ~5 pp is normal; don't treat it as a regression signal.
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
            n   = r["n"]
            print(f"  {name:<15} n={n:<6} detection={det}%  stale={stl}%")
        else:
            sc = r["score_pct"]
            n  = r["n"]
            print(f"  {name:<15} n={n:<6} score={sc}%")
    print(f"  Summary: {summary_path}")

    prev = _load_prev_summaries(
        runs_dir=REPO_ROOT / "data" / "runs",
        current_dir=out_dir,
        limit=args.limit,
    )
    _print_trend(results, prev)


if __name__ == "__main__":
    main()
