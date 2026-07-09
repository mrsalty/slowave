"""Validate emergent prototype generalization from atomic constraint rules.

Replicates the Karpathy experiment's central finding (§8.1): storing atomic
constraints from distinct conceptual categories -> consolidation -> geometrically
separated prototypes emerge -- without procedural machinery.
"""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine

CATEGORY_A = [
    "Analyze requirements before implementation.",
    "Consider edge cases before writing code.",
    "Verify assumptions before proceeding.",
    "Think through the problem before coding.",
]
CATEGORY_B = [
    "Prefer simple solutions over complex ones.",
    "Remove unnecessary abstractions.",
    "Favor readability over cleverness.",
    "Choose the simplest working solution.",
]
ALL_RULES = CATEGORY_A + CATEGORY_B
_DIM = 32


class _CategoryStubEncoder:
    """Deterministic encoder: same-category -> same embedding region."""

    def __init__(self, dim: int = _DIM):
        self._dim = dim
        rng = np.random.default_rng(42)
        self._ca = rng.standard_normal(dim).astype(np.float32)
        self._ca /= np.linalg.norm(self._ca)
        self._cb = rng.standard_normal(dim).astype(np.float32)
        self._cb -= self._cb.dot(self._ca) * self._ca
        nb = np.linalg.norm(self._cb)
        self._cb = (self._cb / nb) if nb > 1e-12 else rng.standard_normal(dim).astype(np.float32)
        assert abs(self._ca.dot(self._cb)) < 1e-6

    def encode(self, text: str) -> np.ndarray:
        t = text.lower()
        ka = {"analyze", "consider", "verify", "think", "assumptions"}
        kb = {"simple", "simplest", "unnecessary", "readability", "cleverness"}
        base = (
            self._ca
            if any(k in t for k in ka)
            else (self._cb if any(k in t for k in kb) else self._ca + 0.5 * self._cb)
        )
        if base is not self._ca and base is not self._cb:
            base = base / np.linalg.norm(base)
        seed = abs(hash(text)) % (2**31)
        noise = np.random.default_rng(seed).standard_normal(self._dim).astype(np.float32) * 0.15
        v = base + noise
        return v / np.linalg.norm(v)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return 0.0 if d < 1e-12 else float(np.dot(a, b) / d)


def _tmp_engine() -> tuple[SlowaveEngine, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    cfg = SlowaveConfig(db_path=tmp.name, dim=_DIM, disable_encoder=True)
    eng = SlowaveEngine(cfg)
    eng.encoder = _CategoryStubEncoder(_DIM)
    return eng, tmp.name


def _cleanup(path: str) -> None:
    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            os.remove(p)


class TestEmergentPrototypeGeneralization:
    """Phase 1 P0: validate consolidation discovers category structure."""

    @pytest.fixture(autouse=True)
    def _engine(self):
        eng, path = _tmp_engine()
        self.eng = eng
        self._path = path
        yield
        eng.close()
        _cleanup(path)

    def _store(self) -> list[int]:
        return [self.eng.remember(content=r, type="constraint").schema_id for r in ALL_RULES]

    def test_prototypes_emerge(self) -> None:
        """8 rules from 2 categories -> >=2 prototypes after consolidation."""
        self._store()
        assert self.eng.schemas.count() == 8
        result = self.eng.consolidate_once()
        assert "error" not in result, f"consolidation failed: {result.get('error')}"
        assert self.eng.semantic.count() >= 2

    def _category_counts(self, pid: int) -> list[int]:
        """[count_from_category_A, count_from_category_B] for a prototype's members."""
        conn = self.eng.db.connect()
        members = conn.execute(
            "SELECT episode_id FROM episode_prototype_map WHERE prototype_id = ?",
            (pid,),
        ).fetchall()
        mids = [int(m["episode_id"]) for m in members]
        cc = [0, 0]
        for eid in mids:
            try:
                text = self.eng.episode_text.get(eid).content_text
            except KeyError:
                r = conn.execute(
                    "SELECT content_text FROM episode_text WHERE episode_id = ?", (eid,)
                ).fetchone()
                if r is None:
                    continue
                text = str(r["content_text"])
            for pfx in ("Remember: ", "User: ", "Assistant: "):
                if text.startswith(pfx):
                    text = text[len(pfx) :]
                    break
            text = text.strip().lower()
            for i, known in enumerate(ALL_RULES):
                if known.lower().strip() in text or text in known.lower().strip():
                    cc[0 if i < len(CATEGORY_A) else 1] += 1
                    break
        return cc

    def test_membership_purity(self) -> None:
        """Each prototype's member episodes predominantly from one category."""
        self._store()
        self.eng.consolidate_once()
        if self.eng.semantic.count() < 2:
            pytest.skip("Need >=2 prototypes")
        for pid in range(1, self.eng.semantic.count() + 1):
            try:
                self.eng.semantic.get(pid)
            except KeyError:
                continue
            cc = self._category_counts(pid)
            total = sum(cc)
            if total < 2:
                continue
            purity = max(cc) / total
            assert purity > 0.75, f"Proto {pid} purity {purity:.2f} (a={cc[0]} b={cc[1]})"

    def test_centroids_separated(self) -> None:
        """Prototypes from different categories have low cosine similarity (< 0.95).

        Same-category fine/coarse-scale prototypes are exempt: with
        differentiated CA3 (0.85) / CA1 (0.55) assignment thresholds, two
        prototypes for the *same* concept at different granularities can
        legitimately sit above 0.95 — that's not the invariant this test
        checks. Only cross-category pairs must be separated. Replay's
        salience-proportional sampling (slowave/latent/salience.py
        sample_proportional) draws from the global unseeded numpy RNG, so
        assignment order — and therefore which same-vs-cross-category pairs
        land closest — varies run to run; comparing same-category pairs here
        made this test flaky (observed max sim 0.965 on an all-same-category
        pairing) without reflecting an actual regression.
        """
        self._store()
        self.eng.consolidate_once()
        if self.eng.semantic.count() < 2:
            pytest.skip("Need >=2 prototypes")
        conn = self.eng.db.connect()
        rows = conn.execute(
            "SELECT id, centroid, dim FROM semantic_prototypes ORDER BY id"
        ).fetchall()
        from slowave.utils.vec import unpack_f32

        protos = [(int(r["id"]), unpack_f32(r["centroid"], int(r["dim"]))) for r in rows]
        # Deduplicate near-identical centroids from multi-scale duplicates,
        # keeping one (pid, centroid) representative per distinct centroid.
        distinct: list[tuple[int, np.ndarray]] = []
        for pid, c in protos:
            if not any(_cosine(c, d) > 0.999 for _, d in distinct):
                distinct.append((pid, c))
        if len(distinct) < 2:
            pytest.skip("Fewer than 2 distinct centroids")

        def _dominant_category(pid: int) -> int | None:
            cc = self._category_counts(pid)
            if sum(cc) == 0:
                return None
            return 0 if cc[0] >= cc[1] else 1

        cross_category_pairs = [
            (i, j)
            for i in range(len(distinct))
            for j in range(i + 1, len(distinct))
            if _dominant_category(distinct[i][0]) is not None
            and _dominant_category(distinct[j][0]) is not None
            and _dominant_category(distinct[i][0]) != _dominant_category(distinct[j][0])
        ]
        if not cross_category_pairs:
            pytest.skip("No cross-category prototype pairs to compare")
        mx = max(_cosine(distinct[i][1], distinct[j][1]) for i, j in cross_category_pairs)
        assert mx < 0.95, f"Max cross-category centroid sim {mx:.3f}"

    def test_consolidation_processed(self) -> None:
        self._store()
        r = self.eng.consolidate_once()
        assert "replay" in r and "consolidation" in r
        assert r["consolidation"].get("prototypes_processed", 0) >= 1

    def test_no_procedural(self) -> None:
        self._store()
        self.eng.consolidate_once()
        # Verify no procedural table — dropped in Phase 1 P1
        conn = self.eng.db.connect()
        r = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='procedural_memories'"
        ).fetchone()
        assert r is None, "procedural_memories table should be dropped"

    def test_no_prototypes_before(self) -> None:
        self._store()
        assert self.eng.semantic.count() == 0

    def test_encoder_clusters(self) -> None:
        enc = _CategoryStubEncoder(_DIM)
        ea = np.stack([enc.encode(r) for r in CATEGORY_A])
        eb = np.stack([enc.encode(r) for r in CATEGORY_B])
        ia = float(
            np.mean([_cosine(ea[i], ea[j]) for i in range(len(ea)) for j in range(i + 1, len(ea))])
        )
        ib = float(
            np.mean([_cosine(eb[i], eb[j]) for i in range(len(eb)) for j in range(i + 1, len(eb))])
        )
        cr = float(np.mean([_cosine(ea[i], eb[j]) for i in range(len(ea)) for j in range(len(eb))]))
        assert ia > cr + 0.1 and ib > cr + 0.1, f"ia={ia:.3f} ib={ib:.3f} cr={cr:.3f}"
