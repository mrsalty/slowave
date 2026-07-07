"""Temporal evaluation harness with simulated time."""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any

from slowave.core.config import SlowaveConfig
from slowave.core.engine import RecallResult, SlowaveEngine
from slowave.latent.replay_engine import ReplayConfig
from slowave.latent.retrieval import RetrievalConfig
from slowave.latent.salience import SalienceConfig
from slowave.symbolic.encoder import EncoderConfig, TextEncoder

SIM_EPOCH = 1735689600  # 2025-01-01
DAY = 86400


@dataclass
class ScenarioResult:
    scenario_id: str
    description: str
    component: str
    expected_keyword: str
    hypothesis: str
    hit: bool
    detail: dict[str, Any] = field(default_factory=dict)


def keyword_hit(hypothesis: str, keyword: str) -> bool:
    return keyword.lower() in hypothesis.lower()


class TemporalHarness:
    """Persistent single-DB harness with injectable simulated time."""

    def __init__(
        self,
        *,
        shared_encoder: TextEncoder,
        consolidate: bool = True,
        tau_days: float = 7.0,
        ablation: str = "full",
    ):
        self.shared_encoder = shared_encoder
        self.consolidate = consolidate
        self.tau_seconds = tau_days * DAY
        self.ablation = ablation
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_path = self._tmp.name
        self.sim_now = SIM_EPOCH
        self._eng: SlowaveEngine | None = None
        self._build_engine()

    def _build_engine(self):
        no_sal = self.ablation == "no_salience"
        no_gr = self.ablation == "no_graph"
        cfg = SlowaveConfig(
            db_path=self.db_path,
            dim=self.shared_encoder.dim,
            encoder=EncoderConfig(),
            salience=SalienceConfig(
                tau_seconds=self.tau_seconds, recall_reinforcement=0.3, consolidation_penalty=0.5
            ),
            replay=ReplayConfig(
                assignment_threshold=0.85, sample_size=2048, max_prototypes_per_replay=128
            ),
            retrieval=RetrievalConfig(
                salience_weight=0.0 if no_sal else 0.4,
                neighbor_top_k=0 if no_gr else 6,
                use_spreading=not no_gr,
            ),
            disable_encoder=False,
        )
        self._eng = SlowaveEngine(cfg, shared_encoder=self.shared_encoder)

    @property
    def eng(self):
        return self._eng

    def session(self, turns: list[tuple[str, str]], *, consolidate: bool | None = None):
        cons = self.consolidate if consolidate is None else consolidate
        sid = self.eng.session_start(agent="temporal_eval", scope="eval:temporal")
        conn = self.eng.db.connect()
        conn.execute("UPDATE sessions SET started_ts=? WHERE id=?", (self.sim_now, sid))
        conn.commit()
        for role, content in turns:
            etype = "user_message" if role == "user" else "assistant_message"
            emb = self.shared_encoder.encode(content)
            self.eng.raw_log.append(
                session_id=sid, ts=self.sim_now, type=etype, content=content, embedding=emb
            )
        self.eng.session_end(sid, consolidate=cons)
        conn.execute(
            "UPDATE episodic_memories SET ts=?, last_salience_ts=? WHERE event_id LIKE ? OR event_id LIKE ?",
            (self.sim_now, self.sim_now, f"micro_{sid}_%", f"macro_{sid}"),
        )
        conn.commit()

    def advance(self, days: float, *, replay: bool = True):
        self.sim_now += int(days * DAY)
        conn = self.eng.db.connect()
        for r in conn.execute(
            "SELECT id, salience, last_salience_ts FROM episodic_memories"
        ).fetchall():
            dt = max(0, self.sim_now - int(r["last_salience_ts"]))
            d = max(0.01, float(r["salience"]) * math.exp(-dt / self.tau_seconds))
            conn.execute(
                "UPDATE episodic_memories SET salience=?, last_salience_ts=? WHERE id=?",
                (d, self.sim_now, int(r["id"])),
            )
        conn.commit()
        self.eng.refresh_indices()
        if replay:
            self.eng.replay_engine.replay_once()

    def reinforce(self, text: str, *, n: int = 3, top_k: int = 5):
        for _ in range(n):
            self.eng.refresh_indices()
            self.eng.recall(text, top_k=top_k)

    def query(self, text: str, *, top_k: int = 5) -> RecallResult:
        self.eng.refresh_indices()
        return self.eng.recall(text, top_k=top_k)

    def salience_of(self, keyword: str) -> float:
        conn = self.eng.db.connect()
        rows = conn.execute(
            "SELECT em.salience FROM episodic_memories em JOIN episode_text et ON et.episode_id=em.id WHERE et.content_text LIKE ?",
            (f"%{keyword}%",),
        ).fetchall()
        return max((float(r["salience"]) for r in rows), default=0.0)

    def n_schemas(self):
        return self.eng.schemas.count()

    def close(self):
        self.eng.close()
        for ext in ("", "-wal", "-shm"):
            p = self.db_path + ext
            if os.path.exists(p):
                os.remove(p)
