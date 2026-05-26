#!/usr/bin/env python3
"""Ablation summary: compare ablation conditions from JSON result files.

Usage:
    .venv/bin/python scripts/ablation_summary.py data/longmemeval/runs/ablation_*.json

Prints a comparison table across conditions and categories, and highlights
which components contribute to the overall score.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

CONDITION_LABELS = {
    "A_full":          "A  full system (LLM + salience + graph)",
    "B_no_llm":        "B  no LLM       (episodes only)",
    "C_no_salience":   "C  no salience  (LLM + graph, no rerank)",
    "D_no_graph":      "D  no graph     (LLM + salience, no expand)",
    "E_no_replay":     "E  no replay    (threshold=1.1, no LLM)",
    "F_no_llm_no_sal": "F  no LLM + no salience",
    "G_pure_embed":    "G  pure embed   (FAISS only, no LLM/sal/graph)",
}

ALL_CATS = [
    "knowledge-update",
    "single-session-preference",
    "multi-session",
    "single-session-user",
    "single-session-assistant",
    "temporal-reasoning",
]


def load_result(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def condition_name(path: str) -> str:
    stem = Path(path).stem  # e.g. ablation_A_full_20260525_120000
    # strip leading "ablation_" and trailing timestamp
    parts = stem.split("_")
    # find condition: everything between "ablation" and the timestamp
    # timestamp pattern: 8 digits _ 6 digits
    import re
    ts_pattern = re.compile(r"^\d{8}$")
    cond_parts = []
    for p in parts[1:]:
        if ts_pattern.match(p):
            break
        cond_parts.append(p)
    return "_".join(cond_parts)


def main() -> None:
    paths = sys.argv[1:]
    if not paths:
        print("Usage: ablation_summary.py <result.json> [...]")
        sys.exit(1)

    rows: list[tuple[str, dict]] = []
    for p in sorted(paths, key=os.path.getmtime):
        try:
            d = load_result(p)
        except Exception as e:
            print(f"skip {p}: {e}")
            continue
        cname = condition_name(p)
        rows.append((cname, d))

    if not rows:
        print("No valid files loaded.")
        sys.exit(1)

    # Build per-condition summary
    print()
    print("=" * 100)
    print(" ABLATION STUDY — Slowave LongMemEval")
    print("=" * 100)

    # Overall comparison
    print()
    print(f" {'Condition':<45} {'N':>4}  {'Hits':>5}  {'Overall%':>9}  {'AvgKS':>6}  {'Elapsed':>9}  {'Model'}")
    print(f" {'-'*45} {'-'*4}  {'-'*5}  {'-'*9}  {'-'*6}  {'-'*9}  {'-'*25}")

    baseline_pct: float | None = None
    for cname, d in rows:
        s = d.get("summary", {}); m = d.get("meta", {})
        label = CONDITION_LABELS.get(cname, cname)
        n = s.get("n", 0); hits = s.get("hits", 0); pct = s.get("score_pct", 0.0)
        elapsed = m.get("total_elapsed_s", 0.0)
        model = m.get("model", "?")
        by_cat = s.get("by_category", {})
        avg_ks = (
            sum(v.get("avg_keyword_score", 0) for v in by_cat.values()) / max(1, len(by_cat))
            if by_cat else 0.0
        )
        if cname == "A_full" and baseline_pct is None:
            baseline_pct = pct
        delta = f"{pct - baseline_pct:+.1f}" if baseline_pct is not None and cname != "A_full" else "baseline"
        print(f" {label:<45} {n:>4}  {hits:>5}  {pct:>8.1f}%  {avg_ks:>6.3f}  {elapsed:>7.0f}s  {model:<25}  {delta}")

    # Per-category breakdown
    print()
    print(" Per-category breakdown")
    print()

    # header
    cat_cols = [c[:18] for c in ALL_CATS]
    header = f" {'Condition':<20}  " + "  ".join(f"{c:>18}" for c in cat_cols)
    print(header)
    print(" " + "-" * (len(header) - 1))

    for cname, d in rows:
        s = d.get("summary", {}); by_cat = s.get("by_category", {})
        label = CONDITION_LABELS.get(cname, cname)[:20]
        cells = []
        for cat in ALL_CATS:
            cv = by_cat.get(cat)
            if cv:
                cells.append(f"{cv['hits']:>3}/{cv['n']:<3} {cv['score_pct']:>5.1f}%")
            else:
                cells.append(f"{'n/a':>18}")
        print(f" {label:<20}  " + "  ".join(cells))

    # Component contribution analysis
    print()
    print(" Component contribution analysis")
    print(" (delta from pure embedding baseline G, positive = helpful)")
    print()

    g_data = dict(rows).get("G_pure_embed")
    a_data = dict(rows).get("A_full")
    if g_data and a_data:
        g_pct = g_data["summary"].get("score_pct", 0)
        a_pct = a_data["summary"].get("score_pct", 0)
        print(f"  Pure embed baseline (G):  {g_pct:.1f}%")
        print(f"  Full system (A):          {a_pct:.1f}%  (delta = {a_pct - g_pct:+.1f}%)")
        print()
        for cname, d in rows:
            if cname in ("G_pure_embed", "A_full"):
                continue
            pct = d["summary"].get("score_pct", 0)
            label = CONDITION_LABELS.get(cname, cname)
            print(f"  {label:<45} {pct:>6.1f}%  delta_from_G={pct - g_pct:+.1f}%")

    print()
    print("=" * 100)
    print()


if __name__ == "__main__":
    main()
