#!/usr/bin/env python3
"""Feedback module (08) micro-benchmark.

Unlike locomo_eval.py/longmemeval_eval.py/stalememory_eval.py, this module has
no external dataset or accuracy ground truth to benchmark against — none of
the project's 6 benchmarks ever call retrieval_feedback()/record_retrieval()
(see plans/08-feedback.md's Priority Finding). This script substitutes a
deterministic, *scored* internal-consistency benchmark: inject schemas with a
synthetic "true quality" label, run repeated noisy recall->feedback rounds
against a real SlowaveEngine, and score how well the resulting salience /
context_noise_score / status separate good schemas from bad ones.

Metric: AUC-style separation — P(good schema's score > bad schema's score)
over every (good, bad) pair, ties counting as 0.5. 1.0 = perfect separation,
0.5 = no better than chance.

Three configs are run and compared:
  - baseline:            apply_learning=True,  scope_id set
  - apply_learning=False: the master gate disabled — should collapse ALL separation
  - scope_id=None:        scope omitted — should collapse noise-score separation
                           only (core doc Invariant 10), salience separation
                           should be unaffected (salience updates don't need scope)

Usage:
    uv run python private/docs/consolidation/scripts/feedback_ablation.py
    uv run python private/docs/consolidation/scripts/feedback_ablation.py --rounds 40 --out results.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from typing import Sequence

import numpy as np

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.core.feedback import FeedbackConfig

# The scope_id=None scenario deliberately triggers FeedbackService's
# no-scope-id warning on every negative-feedback call — that's the point of
# the scenario, not noise. Silence it here so the benchmark's own output
# stays readable; the AUC collapse in that scenario is the actual evidence.
logging.getLogger("slowave.core.services.feedback").setLevel(logging.ERROR)

# Fraction of feedback rounds that are "mislabeled" relative to a schema's
# true synthetic quality — models realistic, noisy human feedback rather than
# a hand-holding oracle.
NOISE_P = 0.2


def make_engine(**feedback_overrides) -> tuple[SlowaveEngine, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    fb_cfg = FeedbackConfig(**feedback_overrides)
    cfg = SlowaveConfig(db_path=tmp.name, dim=8, disable_encoder=True, feedback=fb_cfg)
    return SlowaveEngine(cfg), tmp.name


def cleanup(path: str) -> None:
    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            os.remove(p)


def make_schema(eng: SlowaveEngine, text: str, seed: int) -> int:
    rng = np.random.default_rng(seed)
    emb = rng.normal(size=(8,)).astype(np.float32)
    emb /= np.linalg.norm(emb) + 1e-12
    return eng.schemas.create(
        content_text=text, facets={}, tags=[], embedding=emb, confidence=1.0, salience=1.0
    )


def apply_feedback(
    eng, sid: int, label: str, *, outcome: str, scope_id: str | None, seq: int
) -> None:
    ctx = f"ctx_{sid}_{seq}"
    eng.record_retrieval(retrieval_id=ctx, retrieval_type="recall", scope_id=scope_id)
    kwargs: dict[str, list[str]] = {}
    if label in ("useful", "partially_useful"):
        kwargs["used_memory_ids"] = [f"sch_{sid}"]
    elif label == "irrelevant":
        kwargs["irrelevant_memory_ids"] = [f"sch_{sid}"]
    elif label == "stale":
        kwargs["stale_memory_ids"] = [f"sch_{sid}"]
    elif label == "wrong":
        kwargs["wrong_memory_ids"] = [f"sch_{sid}"]
    eng.retrieval_feedback(
        retrieval_id=ctx,
        retrieval_type="recall",
        feedback=label,
        outcome=outcome,
        scope_id=scope_id,
        **kwargs,
    )


def auc(higher_group: Sequence[float], lower_group: Sequence[float]) -> float:
    """P(a value from higher_group > a value from lower_group), ties = 0.5.

    Standard Mann-Whitney-style rank-separation score. 1.0 = the two groups
    are perfectly separated in the expected direction; 0.5 = indistinguishable.
    """
    if not higher_group or not lower_group:
        return float("nan")
    wins = 0.0
    for h in higher_group:
        for lo in lower_group:
            if h > lo:
                wins += 1.0
            elif h == lo:
                wins += 0.5
    return wins / (len(higher_group) * len(lower_group))


def run_scenario(
    *,
    n_good: int,
    n_bad: int,
    rounds: int,
    seed: int,
    apply_learning: bool = True,
    use_scope: bool = True,
) -> dict:
    eng, path = make_engine(apply_learning=apply_learning)
    try:
        rng = np.random.default_rng(seed)
        good_ids = [make_schema(eng, f"good schema {i}", seed=1000 + i) for i in range(n_good)]
        bad_ids = [make_schema(eng, f"bad schema {i}", seed=2000 + i) for i in range(n_bad)]
        scope = "bench:feedback" if use_scope else None
        seq = 0

        for _ in range(rounds):
            for sid in good_ids:
                seq += 1
                if rng.random() > NOISE_P:
                    label = "useful" if rng.random() < 0.7 else "partially_useful"
                else:
                    label = "irrelevant"  # noisy mislabel
                apply_feedback(eng, sid, label, outcome="success", scope_id=scope, seq=seq)

            for sid in bad_ids:
                seq += 1
                if rng.random() > NOISE_P:
                    r = rng.random()
                    if r < 0.7:
                        label, outcome = "irrelevant", "success"
                    elif r < 0.9:
                        label, outcome = "stale", "success"
                    else:
                        label, outcome = "wrong", "failure"
                else:
                    label, outcome = "useful", "success"  # noisy mislabel
                apply_feedback(eng, sid, label, outcome=outcome, scope_id=scope, seq=seq)

        good = [eng.schemas.get(i) for i in good_ids]
        bad = [eng.schemas.get(i) for i in bad_ids]
        good_sal = [s.salience for s in good]
        bad_sal = [s.salience for s in bad]
        good_noise = [s.facets.get("context_noise_score", 0.0) for s in good]
        bad_noise = [s.facets.get("context_noise_score", 0.0) for s in bad]

        return {
            "salience_auc": round(auc(good_sal, bad_sal), 4),
            "noise_score_auc": round(auc(bad_noise, good_noise), 4),
            "mean_good_salience": round(float(np.mean(good_sal)), 4),
            "mean_bad_salience": round(float(np.mean(bad_sal)), 4),
            "mean_good_noise": round(float(np.mean(good_noise)), 4),
            "mean_bad_noise": round(float(np.mean(bad_noise)), 4),
            "bad_excluded_fraction": round(sum(s.status != "active" for s in bad) / n_bad, 4),
            "good_excluded_fraction": round(sum(s.status != "active" for s in good) / n_good, 4),
            "good_ceiling_saturation_fraction": round(
                sum(s.salience >= 20.0 for s in good) / n_good, 4
            ),
        }
    finally:
        eng.close()
        cleanup(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-good", type=int, default=12)
    parser.add_argument("--n-bad", type=int, default=12)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    configs = {
        "baseline": dict(apply_learning=True, use_scope=True),
        "apply_learning=False": dict(apply_learning=False, use_scope=True),
        "scope_id=None": dict(apply_learning=True, use_scope=False),
    }

    results = {}
    for name, kwargs in configs.items():
        results[name] = run_scenario(
            n_good=args.n_good, n_bad=args.n_bad, rounds=args.rounds, seed=args.seed, **kwargs
        )

    print(
        f"\n{'config':<22} {'salience_auc':>13} {'noise_auc':>10} "
        f"{'bad_excl%':>10} {'good_ceil%':>11}"
    )
    for name, r in results.items():
        print(
            f"{name:<22} {r['salience_auc']:>13} {r['noise_score_auc']:>10} "
            f"{r['bad_excluded_fraction'] * 100:>9.1f}% "
            f"{r['good_ceiling_saturation_fraction'] * 100:>10.1f}%"
        )

    print("\nFull metrics:")
    print(json.dumps(results, indent=2))

    baseline = results["baseline"]
    no_learning = results["apply_learning=False"]
    no_scope = results["scope_id=None"]

    checks = [
        ("baseline separates good/bad by salience (auc > 0.85)", baseline["salience_auc"] > 0.85),
        (
            "apply_learning=False collapses salience separation (auc < 0.6)",
            no_learning["salience_auc"] < 0.6,
        ),
        (
            "baseline separates good/bad by noise score (auc > 0.85)",
            baseline["noise_score_auc"] > 0.85,
        ),
        (
            "scope_id=None collapses noise-score separation (auc < 0.6)",
            no_scope["noise_score_auc"] < 0.6,
        ),
        (
            "scope_id=None does NOT collapse salience separation (auc > 0.85)",
            no_scope["salience_auc"] > 0.85,
        ),
    ]
    print("\nSanity checks:")
    all_ok = True
    for desc, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {desc}")
        all_ok = all_ok and ok

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nWrote {args.out}")

    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
