"""Top-level Slowave configuration.

Merges SlowWave's latent-side configs with new symbolic-side configs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from slowave.latent.graph_manager import GraphConfig
from slowave.latent.replay_engine import ReplayConfig
from slowave.latent.retrieval import RetrievalConfig
from slowave.latent.salience import SalienceConfig
from slowave.latent.transition_model import TransitionModelConfig
from slowave.llm.base import LLMBackendConfig
from slowave.symbolic.encoder import EncoderConfig


@dataclass(frozen=True)
class SlowaveConfig:
    # storage
    db_path: str = "slowave.db"
    schema_path: str = ""  # filled in by engine if empty

    # latent layer (text embeddings will set dim automatically)
    dim: int = 384

    # encoder
    encoder: EncoderConfig = field(default_factory=EncoderConfig)

    # llm backend (used only at replay)
    llm: LLMBackendConfig = field(default_factory=LLMBackendConfig)

    # slowwave core configs
    salience: SalienceConfig = field(default_factory=SalienceConfig)
    replay: ReplayConfig = field(default_factory=ReplayConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    transition: TransitionModelConfig | None = None

    # symbolic
    schema_min_confidence: float = 0.4
    # if True, fall back to text-only mode (no LLM, no schema extraction).
    # Useful for tests and the synthetic demo.
    disable_llm: bool = False
    disable_encoder: bool = False
    # Stage 6: how schemas are formed.
    #   "llm"    — original path, LLM extracts text claims per prototype
    #   "latent" — brain-only path, schemas are pure prototype geometry
    #              (zero LLM calls during ingest or consolidation)
    schema_mode: str = "latent"

    @staticmethod
    def default_schema_path() -> str:
        return str(Path(__file__).resolve().parent.parent / "storage" / "schema.sql")
