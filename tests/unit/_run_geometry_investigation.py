"""Difference-vector geometry investigation — domain-general edition.

Two centroid strategies are tested per encoder:

  centroid_all (LOO)
    Built from all supersession pairs. For each supersession pair, centroid
    excludes self (leave-one-out). Measures overall direction quality.

  centroid_tech → all domains
    Built from TECH domain pairs only. Evaluated against ALL supersession
    pairs, including medical, business, hr, legal, financial, science.
    This is the KEY test: does the direction generalise cross-domain?
    If yes → a small built-in seed set from any domain works everywhere.
    If no  → per-domain centroids are needed, which is impractical.

Key metric: sep(sup, add) = mean_sup_alignment - mean_add_alignment
  Higher = better separation between supersession and additive.

Usage:
  .venv/bin/python tests/unit/_run_geometry_investigation.py
  .venv/bin/python tests/unit/_run_geometry_investigation.py --model mnlm
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

os.environ["TQDM_DISABLE"] = "1"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("filelock").setLevel(logging.ERROR)

from tests.unit.test_supersession_geometry import CASES


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

@dataclass
class ModelSpec:
    label: str
    xenova_repo: str
    tokenizer_repo: str
    prefix: str = ""


ALL_MODELS: dict[str, ModelSpec] = {
    "bge": ModelSpec(
        label="bge-small-en-v1.5",
        xenova_repo="Xenova/bge-small-en-v1.5",
        tokenizer_repo="BAAI/bge-small-en-v1.5",
    ),
    "e5": ModelSpec(
        label="multilingual-e5-small (no prefix)",
        xenova_repo="Xenova/multilingual-e5-small",
        tokenizer_repo="intfloat/multilingual-e5-small",
    ),
    "mnlm": ModelSpec(
        label="paraphrase-multilingual-MiniLM-L12-v2",
        xenova_repo="Xenova/paraphrase-multilingual-MiniLM-L12-v2",
        tokenizer_repo="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    ),
}


# ---------------------------------------------------------------------------
# Generic ONNX encoder
# ---------------------------------------------------------------------------

class GenericONNXEncoder:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        self._session = None
        self._tokenizer = None

    def load(self) -> None:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from transformers import AutoTokenizer

        print(f"  loading {self.spec.label}...", end=" ", flush=True)
        model_path = hf_hub_download(repo_id=self.spec.xenova_repo, filename="onnx/model.onnx")
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = os.cpu_count() or 4
        self._session = ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])
        self._tokenizer = AutoTokenizer.from_pretrained(self.spec.tokenizer_repo)
        print("ok")

    def encode_many(self, texts: list[str]) -> np.ndarray:
        assert self._session and self._tokenizer
        if self.spec.prefix:
            texts = [self.spec.prefix + t for t in texts]
        enc = self._tokenizer(texts, padding=True, truncation=True, max_length=512, return_tensors="np")
        required = {inp.name for inp in self._session.get_inputs()}
        inputs: dict[str, np.ndarray] = {
            "input_ids": enc["input_ids"].astype(np.int64),
            "attention_mask": enc["attention_mask"].astype(np.int64),
        }
        if "token_type_ids" in required:
            inputs["token_type_ids"] = (enc["token_type_ids"].astype(np.int64)
                                        if "token_type_ids" in enc
                                        else np.zeros_like(inputs["input_ids"]))
        last_hidden = self._session.run(None, inputs)[0]
        attn = enc["attention_mask"].astype(np.float32)[:, :, None]
        emb = np.sum(last_hidden * attn, axis=1) / (np.sum(attn, axis=1) + 1e-8)
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        return (emb / (norms + 1e-8)).astype(np.float32)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def _centroid(vecs: np.ndarray) -> np.ndarray:
    c = vecs.mean(axis=0)
    return c / (np.linalg.norm(c) + 1e-8)


def _sep(sup: list[float], add: list[float]) -> float:
    if not sup or not add:
        return float("nan")
    return sum(sup) / len(sup) - sum(add) / len(add)


def _zone_str(vals: list[float]) -> str:
    if not vals:
        return "n/a"
    return f"[{min(vals):+.3f}, {max(vals):+.3f}] mean={sum(vals)/len(vals):+.3f}"


# ---------------------------------------------------------------------------
# Core investigation
# ---------------------------------------------------------------------------

def investigate(spec: ModelSpec) -> dict:
    enc = GenericONNXEncoder(spec)
    enc.load()

    # Encode all pairs in one pass
    flat = []
    for c in CASES:
        flat.extend([c.old, c.new])
    all_embs = enc.encode_many(flat)
    embs_old = all_embs[0::2]
    embs_new = all_embs[1::2]

    # Normalised difference vectors
    diff = embs_new - embs_old
    norms = np.linalg.norm(diff, axis=1, keepdims=True)
    diff_n = (diff / (norms + 1e-8)).astype(np.float32)

    sup_idx  = [i for i, c in enumerate(CASES) if c.expected_zone == "supersession"]
    add_idx  = [i for i, c in enumerate(CASES) if c.expected_zone == "additive"]
    tech_idx = [i for i, c in enumerate(CASES) if c.expected_zone == "supersession" and c.domain == "tech"]
    domains  = sorted({c.domain for c in CASES if c.expected_zone == "supersession"})

    # --- Metric 1: cosine(old, new) ---
    cos_vals = [cosine(embs_old[i], embs_new[i]) for i in range(len(CASES))]

    # --- Metric 2: alignment with centroid_all (LOO) ---
    aln_all: list[float] = []
    for i in range(len(CASES)):
        pool = [j for j in sup_idx if j != i] if i in sup_idx else sup_idx
        c_vec = _centroid(diff_n[pool]) if pool else None
        aln_all.append(cosine(diff_n[i], c_vec) if c_vec is not None else float("nan"))

    # --- Metric 3: alignment with centroid_tech (cross-domain test) ---
    # For tech pairs, fall back to LOO within tech; for all others, use full tech centroid
    c_tech_full = _centroid(diff_n[tech_idx]) if tech_idx else None
    aln_tech: list[float] = []
    for i in range(len(CASES)):
        if i in tech_idx:
            # LOO within tech for fairness
            pool = [j for j in tech_idx if j != i]
            c_vec = _centroid(diff_n[pool]) if pool else None
        else:
            c_vec = c_tech_full
        aln_tech.append(cosine(diff_n[i], c_vec) if c_vec is not None else float("nan"))

    # Collect by zone for each metric
    def _by_zone(vals: list[float]) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {"supersession": [], "additive": [], "unrelated": [], "duplicate": []}
        for i, c in enumerate(CASES):
            out[c.expected_zone].append(vals[i])
        return out

    bz_cos  = _by_zone(cos_vals)
    bz_all  = _by_zone(aln_all)
    bz_tech = _by_zone(aln_tech)

    # Domain breakdown for supersession (alignment_all)
    dom_aln: dict[str, list[float]] = {d: [] for d in domains}
    for i, c in enumerate(CASES):
        if c.expected_zone == "supersession":
            dom_aln[c.domain].append(aln_all[i])

    dom_aln_tech: dict[str, list[float]] = {d: [] for d in domains}
    for i, c in enumerate(CASES):
        if c.expected_zone == "supersession":
            dom_aln_tech[c.domain].append(aln_tech[i])

    W = 88
    print("\n" + "=" * W)
    print(f"  {spec.label}")
    print("=" * W)

    # Zone summary table
    print(f"\n  {'Zone':13}  {'Metric':34}  {'Range + Mean':38}  Sep(sup-add)")
    print("  " + "-" * (W - 2))
    for metric_name, bz in [("cosine(old,new)", bz_cos), ("align centroid_all(LOO)", bz_all), ("align centroid_tech→all", bz_tech)]:
        sup_v = bz["supersession"]
        add_v = bz["additive"]
        sep = _sep(sup_v, add_v)
        for z in ["supersession", "additive", "unrelated", "duplicate"]:
            vals = bz[z]
            m_label = metric_name if z == "supersession" else ""
            sep_str = f"  Δ={sep:+.3f}" if z == "supersession" else ""
            print(f"  {z:13}  {m_label:34}  {_zone_str(vals):38}{sep_str}")
        print()

    # Domain breakdown — centroid_all (LOO)
    print(f"  Supersession alignment by domain — centroid_all (LOO):")
    print(f"  {'domain':12}  {'n':>3}  {'range + mean':38}  cross-domain?")
    print("  " + "-" * 65)
    for d in domains:
        vals = dom_aln[d]
        is_seed = "(seed)" if d == "tech" else ""
        print(f"  {d:12}  {len(vals):3}  {_zone_str(vals):38}  {is_seed}")

    # Domain breakdown — centroid_tech (cross-domain generalisation test)
    print(f"\n  Supersession alignment by domain — centroid_TECH only (cross-domain test):")
    print(f"  {'domain':12}  {'n':>3}  {'range + mean':38}  note")
    print("  " + "-" * 65)
    for d in domains:
        vals = dom_aln_tech[d]
        note = "(LOO within tech)" if d == "tech" else "← generalises?" if sum(vals)/len(vals) > 0.15 else "← FAILS"
        print(f"  {d:12}  {len(vals):3}  {_zone_str(vals):38}  {note}")

    return {
        "label": spec.label,
        "n_sup": len(bz_cos["supersession"]),
        "n_add": len(bz_cos["additive"]),
        "cos_sep":    _sep(bz_cos["supersession"],  bz_cos["additive"]),
        "aln_sep":    _sep(bz_all["supersession"],  bz_all["additive"]),
        "tech_sep":   _sep(bz_tech["supersession"], bz_tech["additive"]),
        "dom_aln":    {d: (sum(v)/len(v) if v else 0) for d, v in dom_aln.items()},
        "dom_tech":   {d: (sum(v)/len(v) if v else 0) for d, v in dom_aln_tech.items()},
    }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(results: list[dict]) -> None:
    W = 88
    domains = sorted(results[0]["dom_tech"].keys()) if results else []

    print("\n" + "=" * W)
    print("  SUMMARY — separation: mean(sup) - mean(add)   higher = better")
    print("=" * W)
    print(f"  {'Model':45}  {'cos':>7}  {'aln(all)':>9}  {'aln(tech)':>10}  winner")
    print("  " + "-" * (W - 2))
    for r in results:
        best = max([("cos", r["cos_sep"]), ("aln_all", r["aln_sep"]), ("aln_tech", r["tech_sep"])],
                   key=lambda x: x[1])[0]
        print(f"  {r['label']:45}  {r['cos_sep']:+.3f}   {r['aln_sep']:+.4f}   {r['tech_sep']:+.4f}   {best}")

    print(f"\n  Cross-domain mean alignment (centroid_tech → each domain):")
    print(f"  {'domain':12}", end="")
    for r in results:
        short = r["label"].split("/")[0][:16]
        print(f"  {short:>17}", end="")
    print()
    print("  " + "-" * (W - 2))
    for d in domains:
        print(f"  {d:12}", end="")
        for r in results:
            val = r["dom_tech"].get(d, float("nan"))
            flag = " ✓" if val > 0.15 else " ✗"
            print(f"  {val:+.3f}{flag:>12}", end="")
        print()

    print("\n" + "=" * W)
    print("  Interpretation:")
    print("  aln(all) sep >> cos sep  → direction discriminates better than cosine")
    print("  aln(tech) generalises    → centroid from one domain works cross-domain")
    print("  aln(tech) col = ✓ for non-tech domains → latent approach is viable globally")
    print("  aln(tech) col = ✗ for non-tech domains → per-domain centroids needed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=list(ALL_MODELS.keys()) + ["all"], default="all",
                        help="Which model(s) to run (default: all)")
    args = parser.parse_args()

    models = list(ALL_MODELS.values()) if args.model == "all" else [ALL_MODELS[args.model]]

    n_sup = sum(1 for c in CASES if c.expected_zone == "supersession")
    n_add = sum(1 for c in CASES if c.expected_zone == "additive")
    n_unr = sum(1 for c in CASES if c.expected_zone == "unrelated")
    n_dup = sum(1 for c in CASES if c.expected_zone == "duplicate")
    domains = sorted({c.domain for c in CASES if c.expected_zone == "supersession"})
    n_tech = sum(1 for c in CASES if c.expected_zone == "supersession" and c.domain == "tech")

    print(f"\nDifference-Vector Geometry Investigation — domain-general edition")
    print(f"Pairs: {len(CASES)} total — {n_sup} supersession across {len(domains)} domains "
          f"({n_add} additive, {n_unr} unrelated, {n_dup} duplicate)")
    print(f"Domains: {', '.join(domains)}")
    print(f"Tech seed size for cross-domain test: {n_tech} pairs")
    print(f"\nKey question: does centroid_tech (built from {n_tech} tech pairs) "
          f"generalise to medical, business, hr, legal, financial, science?")

    results = []
    for spec in models:
        try:
            results.append(investigate(spec))
        except Exception as e:
            print(f"\n  [SKIP] {spec.label}: {e}")

    if results:
        print_summary(results)


if __name__ == "__main__":
    main()
