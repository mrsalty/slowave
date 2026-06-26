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
from slowave.symbolic.encoder import EncoderConfig
from slowave.core.paths import default_db_path
from slowave.core.feedback import FeedbackConfig


@dataclass(frozen=True)
class SlowaveConfig:
    # storage
    db_path: str = field(default_factory=default_db_path)
    schema_path: str = ""  # filled in by engine if empty

    # latent layer (text embeddings will set dim automatically)
    dim: int = 384

    # encoder
    encoder: EncoderConfig = field(default_factory=EncoderConfig)

    # slowwave core configs
    salience: SalienceConfig = field(default_factory=SalienceConfig)
    replay: ReplayConfig = field(default_factory=ReplayConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    transition: TransitionModelConfig | None = None

    # Convenience shorthand for the most-tuned parameter: prototype
    # assignment threshold. When set, overrides replay.assignment_threshold
    # and replay.coarse_assignment_threshold at engine init time.
    # 0.60 = default (broad clusters, faster consolidation)
    # 0.85 = fine-grained (distinct facts stay separate, better recall precision)
    assignment_threshold: float | None = None

    # symbolic
    disable_encoder: bool = False

    # feedback system
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)


    @staticmethod
    def default_schema_path() -> str:
        return str(Path(__file__).resolve().parent.parent / "storage" / "schema.sql")
