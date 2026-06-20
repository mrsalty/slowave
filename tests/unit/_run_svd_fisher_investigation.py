"""SVD concentration + Fisher LDA investigation.

Tests the SparseCL hypothesis: does the supersession difference vector
concentrate in a low-dimensional subspace of embedding space?

If yes  → projecting onto that subspace improves discrimination cross-domain.
If no   → the signal is diffuse; no projection-based shortcut exists.

Also tests Fisher LDA as a lightweight supervised discriminant on the
difference vectors, using LOO cross-validation.

Three questions answered:
  Q1. How many SVD components are needed to explain 90% of variance for each zone?
      (low = concentrated; high = diffuse)
  Q2. Does projecting all diff vectors onto the top-K supersession SVD subspace
      improve sep(sup, add) vs full-dim direction centroid?
  Q3. What is the LOO accuracy of a regularised Fisher LDA classifier trained
      on diff vectors (binary: supersession vs all others)?

Usage:
  .venv/bin/python tests/unit/_run_svd_fisher_investigation.py
  .venv/bin/python tests/unit/_run_svd_fisher_investigation.py --model bge
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
# Model registry (same as _run_geometry_investigation.py)
# ---------------------------------------------------------------------------

@dataclass
class ModelSpec:
    label: str
    xenova_repo: str
    tokenizer_repo: str
    prefix: str = ""


ALL_MODELS: dict[str, ModelSpec] = {
    "bge": ModelSpec("bge-small-en-v1.5", "Xenova/bge-small-en-v1.5", "BAAI/bge-small-en-v1.5"),
    "e5":  ModelSpec("multilingual-e5-small", "Xenova/multilingual-e5-small", "intfloat/multilingual-e5-small"),
    "mnlm": ModelSpec("paraphrase-multilingual-MiniLM-L12-v2",
                      "Xenova/paraphrase-multilingual-MiniLM-L12-v2",
                      "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
}


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
        p = hf_hub_download(repo_id=self.spec.xenova_repo, filename="onnx/model.onnx")
        o = ort.SessionOptions()
        o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        o.intra_op_num_threads = os.cpu_count() or 4
        self._session = ort.InferenceSession(p, sess_options=o, providers=["CPUExecutionProvider"])
        self._tokenizer = AutoTokenizer.from_pretrained(self.spec.tokenizer_repo)
        print("ok")

    def encode_many(self, texts: list[str]) -> np.ndarray:
        assert self._session and self._tokenizer
        if self.spec.prefix:
            texts = [self.spec.prefix + t for t in texts]
        enc = self._tokenizer(texts, padding=True, truncation=True, max_length=512, return_tensors="np")
        required = {inp.name for inp in self._session.get_inputs()}
        inputs: dict = {
            "input_ids": enc["input_ids"].astype(np.int64),
            "attention_mask": enc["attention_mask"].astype(np.int64),
        }
        if "token_type_ids" in required:
            inputs["token_type_ids"] = (enc["token_type_ids"].astype(np.int64)
                                        if "token_type_ids" in enc
                                        else np.zeros_like(inputs["input_ids"]))
        lh = self._session.run(None, inputs)[0]
        a = enc["attention_mask"].astype(np.float32)[:, :, None]
        emb = np.sum(lh * a, axis=1) / (np.sum(a, axis=1) + 1e-8)
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        return (emb / (norms + 1e-8)).astype(np.float32)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def components_for_variance(singular_values: np.ndarray, threshold: float = 0.90) -> int:
    var = singular_values ** 2
    cumvar = np.cumsum(var) / var.sum()
    hits = np.where(cumvar >= threshold)[0]
    return int(hits[0]) + 1 if len(hits) else len(singular_values)


def sep(sup: np.ndarray, other: np.ndarray) -> float:
    if len(sup) == 0 or len(other) == 0:
        return float("nan")
    return float(sup.mean() - other.mean())


def investigate(spec: ModelSpec) -> dict:
    enc = GenericONNXEncoder(spec)
    enc.load()

    # Encode all pairs
    flat = []
    for c in CASES:
        flat.extend([c.old, c.new])
    all_embs = enc.encode_many(flat)
    embs_old = all_embs[0::2]
    embs_new = all_embs[1::2]

    # Raw diff vectors (NOT normalised — SVD needs raw magnitudes)
    diff_raw = embs_new - embs_old  # [N, 384]

    # Normalised diff vectors (for centroid/alignment)
    norms = np.linalg.norm(diff_raw, axis=1, keepdims=True)
    diff_n = diff_raw / (norms + 1e-8)

    zones = ["supersession", "additive", "unrelated", "duplicate"]
    idx: dict[str, list[int]] = {z: [] for z in zones}
    for i, c in enumerate(CASES):
        idx[c.expected_zone].append(i)

    domains = sorted({c.domain for c in CASES if c.expected_zone == "supersession"})
    dom_idx: dict[str, list[int]] = {d: [] for d in domains}
    for i, c in enumerate(CASES):
        if c.expected_zone == "supersession":
            dom_idx[c.domain].append(i)

    W = 88
    print("\n" + "=" * W)
    print(f"  {spec.label}")
    print("=" * W)

    # ------------------------------------------------------------------
    # Q1: SVD concentration per zone
    # ------------------------------------------------------------------
    print(f"\n  Q1: SVD concentration — components needed for 90% variance")
    print(f"  {'zone':13}  {'n':>4}  {'k@90%':>6}  {'k/dim':>7}  {'top-1 var%':>11}  {'top-5 var%':>11}  {'top-20 var%':>12}")
    print("  " + "-" * (W - 2))

    zone_svd: dict[str, np.ndarray] = {}
    for z in zones:
        D = diff_raw[idx[z]]
        if len(D) < 2:
            print(f"  {z:13}  {len(D):4}  (too few)")
            continue
        # SVD: D = U S Vt   shape [n, 384]
        _, s, Vt = np.linalg.svd(D, full_matrices=False)
        zone_svd[z] = Vt  # right singular vectors = principal axes
        var = s ** 2
        total = var.sum()
        k90 = components_for_variance(s)
        t1 = var[0] / total * 100
        t5 = var[:5].sum() / total * 100
        t20 = var[:20].sum() / total * 100
        print(f"  {z:13}  {len(D):4}  {k90:6}  {k90/384:7.3f}  {t1:10.1f}%  {t5:10.1f}%  {t20:11.1f}%")

    # ------------------------------------------------------------------
    # Q2: Subspace projection — does projecting onto top-K supersession
    #     SVD axes improve sep(sup, add)?
    # ------------------------------------------------------------------
    print(f"\n  Q2: Subspace projection — sep(sup, add) vs full-dim centroid")
    print(f"  {'K':>4}  {'sup@90':>7}  {'full-dim':>9}  note")
    print("  " + "-" * 50)

    sup_Vt = zone_svd.get("supersession")
    add_idx_list = idx["additive"]

    if sup_Vt is not None:
        # Full-dim LOO centroid baseline
        sup_i = idx["supersession"]
        full_alns_sup, full_alns_add = [], []
        for i in sup_i:
            pool = [j for j in sup_i if j != i]
            c = diff_n[pool].mean(axis=0)
            c /= np.linalg.norm(c) + 1e-8
            full_alns_sup.append(cosine(diff_n[i], c))
        full_centroid = diff_n[sup_i].mean(axis=0)
        full_centroid /= np.linalg.norm(full_centroid) + 1e-8
        for i in add_idx_list:
            full_alns_add.append(cosine(diff_n[i], full_centroid))
        full_sep = sep(np.array(full_alns_sup), np.array(full_alns_add))

        # Try K = 1, 2, 5, 10, 20, 50
        for K in [1, 2, 5, 10, 20, 50]:
            axes = sup_Vt[:K].T  # [384, K]
            proj = diff_n @ axes   # [N, K] — project all diff vecs onto K axes

            # Recompute centroid in projected space
            proj_sup = proj[sup_i]
            proj_add = proj[add_idx_list]

            # LOO centroid in projected space for supersession pairs
            proj_alns_sup = []
            for ii, i in enumerate(sup_i):
                pool_proj = np.delete(proj_sup, ii, axis=0)
                c_proj = pool_proj.mean(axis=0)
                n = np.linalg.norm(c_proj) + 1e-8
                c_proj = c_proj / n
                p = proj_sup[ii]
                proj_alns_sup.append(float(np.dot(p / (np.linalg.norm(p) + 1e-8), c_proj)))

            # Centroid for additive alignment
            full_centroid_proj = proj_sup.mean(axis=0)
            full_centroid_proj /= np.linalg.norm(full_centroid_proj) + 1e-8
            proj_alns_add = []
            for i_add in add_idx_list:
                p = proj[i_add]
                proj_alns_add.append(float(np.dot(p / (np.linalg.norm(p) + 1e-8), full_centroid_proj)))

            proj_sep = sep(np.array(proj_alns_sup), np.array(proj_alns_add))
            k90_sup = components_for_variance(
                np.linalg.svd(diff_raw[sup_i], full_matrices=False, compute_uv=False)
            )
            note = f"(k@90%={k90_sup})" if K == k90_sup else ""
            better = " ← better" if proj_sep > full_sep else ""
            print(f"  {K:4}  {proj_sep:+7.4f}  {full_sep:+9.4f}  {note}{better}")

    # ------------------------------------------------------------------
    # Q3: Fisher LDA LOO accuracy
    # ------------------------------------------------------------------
    print(f"\n  Q3: Fisher LDA (regularised, LOO) — diff vectors → binary sup/not-sup")

    try:
        from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
        from sklearn.preprocessing import StandardScaler

        # Build X (diff_raw), y (binary)
        X = diff_raw
        y = np.array([1 if c.expected_zone == "supersession" else 0 for c in CASES])

        # LOO cross-validation
        n_correct_sup, n_correct_not = 0, 0
        n_sup = int(y.sum())
        n_not = int((1 - y).sum())

        # Collect scores for AUC proxy
        scores_sup, scores_not = [], []

        for leave_out in range(len(CASES)):
            train_mask = np.ones(len(CASES), dtype=bool)
            train_mask[leave_out] = False
            X_train, y_train = X[train_mask], y[train_mask]
            X_test = X[leave_out:leave_out + 1]

            # Regularised LDA with shrinkage
            sc = StandardScaler()
            X_train_s = sc.fit_transform(X_train)
            X_test_s = sc.transform(X_test)

            lda = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
            lda.fit(X_train_s, y_train)
            pred = int(lda.predict(X_test_s)[0])
            score = float(lda.decision_function(X_test_s)[0])

            truth = int(y[leave_out])
            if truth == 1:
                scores_sup.append(score)
                if pred == 1:
                    n_correct_sup += 1
            else:
                scores_not.append(score)
                if pred == 0:
                    n_correct_not += 1

        acc_sup  = n_correct_sup / n_sup * 100
        acc_not  = n_correct_not / n_not * 100
        overall  = (n_correct_sup + n_correct_not) / len(CASES) * 100
        precision = n_correct_sup / max(1, n_correct_sup + (n_not - n_correct_not)) * 100

        print(f"  Overall LOO accuracy : {overall:.1f}%  ({n_correct_sup+n_correct_not}/{len(CASES)})")
        print(f"  Supersession recall  : {acc_sup:.1f}%  ({n_correct_sup}/{n_sup})")
        print(f"  Not-sup specificity  : {acc_not:.1f}%  ({n_correct_not}/{n_not})")
        print(f"  Precision (sup)      : {precision:.1f}%")
        print(f"  Mean LDA score sup   : {np.mean(scores_sup):+.4f}  std={np.std(scores_sup):.4f}")
        print(f"  Mean LDA score not   : {np.mean(scores_not):+.4f}  std={np.std(scores_not):.4f}")
        sep_lda = np.mean(scores_sup) - np.mean(scores_not)
        print(f"  Score sep (sup-not)  : {sep_lda:+.4f}")

    except ImportError:
        print("  [SKIP] sklearn not installed. pip install scikit-learn")

    # ------------------------------------------------------------------
    # Domain alignment in top-K subspace
    # ------------------------------------------------------------------
    print(f"\n  Domain alignment with top-1 supersession principal axis:")
    if sup_Vt is not None:
        axis1 = sup_Vt[0]  # [384] — most important supersession direction
        print(f"  {'domain':12}  {'n':>3}  {'mean alignment':>16}  {'range':>26}")
        print("  " + "-" * 65)
        for d in domains:
            di = dom_idx[d]
            alns = [float(np.dot(diff_n[i], axis1)) for i in di]
            lo, hi, mean = min(alns), max(alns), np.mean(alns)
            flag = "✓" if mean > 0.05 else "~" if mean > 0 else "✗"
            print(f"  {d:12}  {len(di):3}  {mean:+.4f} {flag:>10}     [{lo:+.4f}, {hi:+.4f}]")
        # Additive reference
        add_alns = [float(np.dot(diff_n[i], axis1)) for i in add_idx_list]
        print(f"  {'[additive]':12}  {len(add_alns):3}  {np.mean(add_alns):+.4f} {'ref':>10}     [{min(add_alns):+.4f}, {max(add_alns):+.4f}]")

    return {}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=list(ALL_MODELS.keys()), default="mnlm")
    args = parser.parse_args()

    spec = ALL_MODELS[args.model]
    n_sup = sum(1 for c in CASES if c.expected_zone == "supersession")
    n_add = sum(1 for c in CASES if c.expected_zone == "additive")
    domains = sorted({c.domain for c in CASES if c.expected_zone == "supersession"})

    print(f"\nSVD Concentration + Fisher LDA Investigation")
    print(f"Model: {spec.label}")
    print(f"Pairs: {len(CASES)} — {n_sup} supersession ({len(domains)} domains), {n_add} additive")
    print(f"\nHypothesis (SparseCL): supersession diff vectors concentrate in a")
    print(f"low-dim subspace. If yes, projecting onto it improves cross-domain sep.")

    investigate(spec)


if __name__ == "__main__":
    main()
