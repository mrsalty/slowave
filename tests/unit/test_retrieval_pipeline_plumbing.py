"""Plumbing tests for retrieval pipeline components.

Uses a ControlledEncoder — pre-registered embeddings for specific strings,
deterministic random for everything else — to guarantee precise cosine
relationships. Each test verifies that exactly one retrieval component
produces a measurable behavioral change when enabled vs disabled, with all
other components neutralized.

These are regression tests: they catch broken code paths, not degraded
quality. They verify the wires are connected, not that the wires carry
the right current.

SP-1: spreading — proves graph_harvest_n goes from 0 to >0 when spreading
  is enabled, confirming the ML→ZAN graph edge is traversed.

SP-2: temporal — proves temporal boost changes episode sort order (Gondola
  before LRU) when anchor matches simulated time, with pure cosine ordering
  reversed without temporal.
"""

from __future__ import annotations

import dataclasses
import math
import os
import tempfile

import numpy as np

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.latent.replay_engine import ReplayConfig
from slowave.latent.retrieval import RetrievalConfig, RetrievalPipeline
from slowave.latent.salience import SalienceConfig
from slowave.symbolic.encoder import EncoderConfig

_DIM = 32
_SIM_EPOCH = 1735689600  # 2025-01-01 UTC
_DAY = 86400


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------


def _axis(i: int) -> np.ndarray:
    v = np.zeros(_DIM, dtype=np.float32)
    v[i] = 1.0
    return v


class _ControlledEncoder:
    """Returns registered embeddings for known strings; deterministic random otherwise."""

    def __init__(self) -> None:
        self._registry: dict[str, np.ndarray] = {}

    def register(self, text: str, emb: np.ndarray) -> "_ControlledEncoder":
        v = np.asarray(emb, dtype=np.float32).reshape(-1)
        self._registry[text] = v / (float(np.linalg.norm(v)) + 1e-12)
        return self

    def encode(self, text: str) -> np.ndarray:
        if text in self._registry:
            return self._registry[text].copy()
        seed = int(abs(hash(text)) % (2**31))
        v = np.random.default_rng(seed).standard_normal(_DIM).astype(np.float32)
        return v / (float(np.linalg.norm(v)) + 1e-12)

    @property
    def dim(self) -> int:
        return _DIM


class _Harness:
    """Thin harness: SlowaveEngine with ControlledEncoder and simulated time."""

    def __init__(self, encoder: _ControlledEncoder, cfg: RetrievalConfig) -> None:
        self._enc = encoder
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._db_path = self._tmp.name
        self.sim_now = _SIM_EPOCH
        self._tau_s = 7.0 * _DAY
        engine_cfg = SlowaveConfig(
            db_path=self._db_path,
            dim=_DIM,
            encoder=EncoderConfig(),
            salience=SalienceConfig(tau_seconds=self._tau_s, consolidation_penalty=0.5),
            replay=ReplayConfig(
                assignment_threshold=0.85, sample_size=2048, max_prototypes_per_replay=128
            ),
            retrieval=cfg,
            disable_encoder=False,
        )
        self.eng = SlowaveEngine(engine_cfg, shared_encoder=encoder)  # type: ignore[arg-type]

    def session(self, turns: list[tuple[str, str]], *, consolidate: bool = False) -> None:
        sid = self.eng.session_start(agent="test", scope="test")
        conn = self.eng.db.connect()
        conn.execute("UPDATE sessions SET started_ts=? WHERE id=?", (self.sim_now, sid))
        conn.commit()
        for role, content in turns:
            etype = "user_message" if role == "user" else "assistant_message"
            emb = self._enc.encode(content)
            self.eng.raw_log.append(
                session_id=sid, ts=self.sim_now, type=etype, content=content, embedding=emb
            )
        self.eng.session_end(sid, consolidate=consolidate)
        conn.execute(
            "UPDATE episodic_memories SET ts=?, last_salience_ts=? "
            "WHERE event_id LIKE ? OR event_id LIKE ?",
            (self.sim_now, self.sim_now, f"micro_{sid}_%", f"macro_{sid}"),
        )
        conn.commit()

    def ingest(self, text: str, *, consolidate: bool = False) -> None:
        self.session([("user", text)], consolidate=consolidate)

    def ingest_many(self, texts: list[str], *, consolidate: bool = False) -> None:
        for text in texts:
            self.session([("user", text)], consolidate=consolidate)

    def advance(self, days: float, *, replay: bool = True) -> None:
        self.sim_now += int(days * _DAY)
        conn = self.eng.db.connect()
        for r in conn.execute(
            "SELECT id, salience, last_salience_ts FROM episodic_memories"
        ).fetchall():
            dt = max(0, self.sim_now - int(r["last_salience_ts"]))
            d = max(0.01, float(r["salience"]) * math.exp(-dt / self._tau_s))
            conn.execute(
                "UPDATE episodic_memories SET salience=?, last_salience_ts=? WHERE id=?",
                (d, self.sim_now, int(r["id"])),
            )
        conn.commit()
        self.eng.refresh_indices()
        if replay:
            self.eng.replay_engine.replay_once()

    def recall_diagnose(self, text: str, top_k: int = 10):
        self.eng.refresh_indices()
        return self.eng.recall(text, top_k=top_k, diagnose=True)

    def recall_pipeline_direct(self, text: str, cfg: RetrievalConfig, top_k: int = 10) -> str:
        """Bypass RetrievalService to avoid TemporalProbe overriding anchor_ts."""
        self.eng.refresh_indices()
        q = self.eng.encoder.encode(text)
        pipeline = RetrievalPipeline(
            episodic=self.eng.episodic,
            semantic=self.eng.semantic,
            graph=self.eng.graph,
            cfg=cfg,
        )
        mem = pipeline.retrieve(q)
        ep_texts = self.eng.episode_text.get_many([m.id for m in mem.episodic[:top_k]])
        return " ".join(et.content_text for et in ep_texts if et and et.content_text)

    def close(self) -> None:
        self.eng.close()
        for ext in ("", "-wal", "-shm"):
            p = self._db_path + ext
            if os.path.exists(p):
                os.remove(p)


# ---------------------------------------------------------------------------
# SP-1: spreading finds a cross-domain episode via graph edge
# ---------------------------------------------------------------------------

# SP-1 config: only use_spreading varies.
# - temporal=False: ZAN ingested at t+1d; recency would rescue it without spreading
# - transition=False: ML→ZAN ingestion order is learned by transition model
# - salience=0, salience_gate=False: ML proto has 150× support; gate amplifies dominance
# - spread_episodic_top_k=50: ZAN sits at cosine≈0.33 with q_spread, needs large top_k
_SP1_BASE = RetrievalConfig(
    salience_weight=0.0,
    use_temporal=False,
    use_transition=False,
    use_multi_scale=False,
    salience_gate=False,
    spread_episodic_top_k=50,
)

_Q1 = "What Python libraries does our team use for machine learning model training?"
_ML_FILLERS = [
    "PyTorch provides automatic differentiation for neural network training.",
    "TensorFlow offers high-level APIs for training deep learning models at scale.",
    "JAX enables accelerated numerical computing with composable transforms.",
    "Scikit-learn implements classical machine learning algorithms in Python.",
    "Keras provides a high-level API for building and training neural networks.",
    "HuggingFace Transformers distributes pre-trained language model weights.",
    "LightGBM trains gradient-boosted trees for tabular data classification.",
    "XGBoost implements an optimized gradient boosting framework.",
    "CatBoost handles categorical features natively in gradient boosting.",
    "FastAI simplifies training deep learning models on common datasets.",
]
_ZAN_TEXT = "Zanbouli manages ARP table synchronization across VLAN segments."


def _sp1_encoder() -> _ControlledEncoder:
    enc = _ControlledEncoder()
    enc.register(_Q1, _axis(0))
    # ML filler at cosine=0.6 with query (not 1.0, leaving room for spreading to compete)
    ml_emb = np.zeros(_DIM, dtype=np.float32)
    ml_emb[0] = 0.6
    ml_emb[1] = 0.8
    ml_emb /= float(np.linalg.norm(ml_emb))
    for text in _ML_FILLERS:
        enc.register(text, ml_emb)
    # ZAN at axis_1: cosine=0 with query.
    # cos(axis_1, ML_centroid≈[0.6,0.8,...]) = 0.8 < assignment_threshold(0.85)
    # → ZAN forms its own prototype, separate from ML.
    enc.register(_ZAN_TEXT, _axis(1))
    return enc


def test_spreading_finds_cross_domain_episode():
    """Spreading retrieves ZAN (cosine=0 with query) via ML→ZAN graph edge.

    ZAN forms its own prototype (cos=0.8 to ML centroid < threshold=0.85).
    Coactivation edges form during replay. q_spread then has an axis_1
    component that FAISS resolves to the ZAN episode.

    graph_harvest_n counts episodes found via spread-projection that
    cosine-direct missed — must be >0 with spreading, 0 without.
    """
    h_on = _Harness(_sp1_encoder(), _SP1_BASE)
    h_on.ingest_many(_ML_FILLERS, consolidate=True)
    h_on.advance(1, replay=True)
    h_on.ingest(_ZAN_TEXT, consolidate=False)
    h_on.advance(1, replay=True)
    qd_on = h_on.recall_diagnose(_Q1).query_diagnostics
    h_on.close()

    h_off = _Harness(_sp1_encoder(), dataclasses.replace(_SP1_BASE, use_spreading=False))
    h_off.ingest_many(_ML_FILLERS, consolidate=True)
    h_off.advance(1, replay=True)
    h_off.ingest(_ZAN_TEXT, consolidate=False)
    h_off.advance(1, replay=True)
    qd_off = h_off.recall_diagnose(_Q1).query_diagnostics
    h_off.close()

    assert qd_on is not None and qd_off is not None
    assert qd_on.graph_harvest_n > 0, (
        f"spreading=True: expected graph_harvest_n>0, got {qd_on.graph_harvest_n}; "
        f"activated={qd_on.activated_after_spread_n}, depth={qd_on.activation_depth}"
    )
    assert (
        qd_off.graph_harvest_n == 0
    ), f"spreading=False: expected graph_harvest_n==0, got {qd_off.graph_harvest_n}"


# ---------------------------------------------------------------------------
# SP-2: temporal boost changes episode sort order
# ---------------------------------------------------------------------------

# SP-2 temporal anchor = simulated "now" after setup (SIM_EPOCH + 14 days).
# Without this the default anchor is wall-clock time (July 2026), making both
# Jan-2025 episode groups equally "old" with negligible temporal difference.
_SP2_ANCHOR = _SIM_EPOCH + 14 * _DAY

# SP-2 config: only use_temporal varies.
# - salience=0: 14-day decay would rescue NEW regardless of temporal boost
# - spreading/transition/multi_scale=False: clean isolation
# - episodic_top_k=40: 5 OLD × 2ep + 5 NEW × 2ep = 20 total; 40 captures all
_SP2_BASE = RetrievalConfig(
    salience_weight=0.0,
    use_spreading=False,
    use_multi_scale=False,
    use_transition=False,
    episodic_top_k=40,
)

_Q2 = "What eviction strategy does the cache manager use for heap memory reclamation?"
_OLD_TEXT = "The cache manager uses LRU-eviction for heap memory reclamation."
_NEW_TEXT = "The cache manager uses Gondola-eviction for heap memory reclamation."


def _sp2_encoder() -> _ControlledEncoder:
    enc = _ControlledEncoder()
    enc.register(_Q2, _axis(0))
    # OLD: cosine=0.990 — wins on pure cosine without temporal
    old_emb = np.zeros(_DIM, dtype=np.float32)
    old_emb[0] = 0.990
    old_emb[1] = 0.141
    enc.register(_OLD_TEXT, old_emb / float(np.linalg.norm(old_emb)))
    # NEW: cosine=0.980 — loses on cosine, wins with temporal boost
    # temporal_bonus_new ≈ 0.250, temporal_bonus_old ≈ 0.178 → Δ=0.072 > deficit 0.010
    new_emb = np.zeros(_DIM, dtype=np.float32)
    new_emb[0] = 0.980
    new_emb[1] = 0.141
    enc.register(_NEW_TEXT, new_emb / float(np.linalg.norm(new_emb)))
    return enc


def test_temporal_boost_changes_episode_ranking():
    """Temporal boost (anchor=sim_now=t+14d) ranks NEW Gondola before OLD LRU.

    OLD cosine=0.990 > NEW=0.980, so without temporal OLD leads. With anchor
    at simulated "now" (t+14d): NEW bonus≈0.250, OLD bonus≈0.178. NEW final
    score 1.230 > OLD 1.168 → Gondola appears first.

    Uses recall_pipeline_direct() to bypass RetrievalService.TemporalProbe,
    which otherwise overrides temporal_anchor_ts using real wall-clock time.
    """
    cfg_on = dataclasses.replace(_SP2_BASE, temporal_anchor_ts=_SP2_ANCHOR)
    cfg_off = dataclasses.replace(_SP2_BASE, use_temporal=False)

    h_on = _Harness(_sp2_encoder(), cfg_on)
    for _ in range(5):
        h_on.ingest(_OLD_TEXT, consolidate=False)
    h_on.advance(14, replay=True)
    for _ in range(5):
        h_on.ingest(_NEW_TEXT, consolidate=False)
    h_on.advance(0, replay=True)
    hyp_on = h_on.recall_pipeline_direct(_Q2, cfg_on, top_k=3)
    h_on.close()

    h_off = _Harness(_sp2_encoder(), cfg_off)
    for _ in range(5):
        h_off.ingest(_OLD_TEXT, consolidate=False)
    h_off.advance(14, replay=True)
    for _ in range(5):
        h_off.ingest(_NEW_TEXT, consolidate=False)
    h_off.advance(0, replay=True)
    hyp_off = h_off.recall_pipeline_direct(_Q2, cfg_off, top_k=3)
    h_off.close()

    def gondola_before_lru(h: str) -> bool:
        hl = h.lower()
        if "gondola" not in hl:
            return False
        if "lru" not in hl:
            return True
        return hl.index("gondola") < hl.index("lru")

    assert gondola_before_lru(
        hyp_on
    ), f"temporal=True: expected Gondola first, got: {hyp_on[:100]!r}"
    assert not gondola_before_lru(
        hyp_off
    ), f"temporal=False: expected LRU first, got: {hyp_off[:100]!r}"
