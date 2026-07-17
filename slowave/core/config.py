"""Top-level Slowave configuration.

Merges SlowWave's latent-side configs with new symbolic-side configs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from slowave.core.feedback import FeedbackConfig
from slowave.core.paths import default_db_path
from slowave.latent.graph_manager import GraphConfig
from slowave.latent.replay_engine import ReplayConfig
from slowave.latent.retrieval import RetrievalConfig
from slowave.latent.salience import SalienceConfig
from slowave.latent.schema import GeometricJudgeConfig
from slowave.latent.transition_model import TransitionModelConfig
from slowave.symbolic.encoder import EncoderConfig

# Default for the `top_k` parameter of `recall()` — how many schemas/episodes
# a call returns to its caller. Distinct from RetrievalConfig's internal
# candidate-pool fields (episodic_top_k, semantic_top_k, etc.), which control
# pipeline internals, not this output size. Backed by Recall@K benchmark
# sweeps (LoCoMo/LongMemEval/DMR/StaleMemory, 2026-07-13): raising from 5 to
# 20 improved every benchmark (+1.8pp to +23.7pp), none regressed.
DEFAULT_RECALL_TOP_K = 20


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
    judge: GeometricJudgeConfig = field(default_factory=GeometricJudgeConfig)

    # Convenience shorthand for the most-tuned parameter: prototype
    # assignment threshold. When set, overrides replay.assignment_threshold
    # and replay.coarse_assignment_threshold at engine init time.
    # 0.60 = default (broad clusters, faster consolidation)
    # 0.85 = fine-grained (distinct facts stay separate, better recall precision)
    assignment_threshold: float | None = None

    # symbolic
    disable_encoder: bool = False

    # Event-store replay (2026-07-16): stamped onto every raw event, schema,
    # and prototype created while this config is active. RebuildService
    # (slowave/core/services/rebuild.py) compares this against each
    # customer DB's replay_checkpoints on every SlowaveEngine startup, and
    # transparently rebuilds all derived memory state from raw_events if
    # they don't match — no manual action from the customer.
    #
    # Bump this ONLY when a change alters episode formation (ingest.py),
    # prototype assignment/clustering (replay_engine.py), or schema-writing
    # logic (consolidation.py) such that it would produce *different output*
    # for already-ingested raw_events. Do NOT bump for refactors or bug
    # fixes that don't change output (e.g. the replay_all()/consolidate_all()
    # additions themselves were behavior-preserving for existing code paths
    # and did not bump this), or for unrelated features — most releases
    # should leave this untouched, which is what keeps the auto-rebuild a
    # no-op for most upgrades. When you do bump it, also set
    # current_logic_version_description below so the change is
    # self-documenting. See private/docs/iterations/20260716_event-store-replay.md.
    current_logic_version: str = "0"
    # Human-readable note on *why* current_logic_version was last bumped.
    # Written into the logic_versions.description column by
    # RebuildService.try_claim() at rebuild time.
    current_logic_version_description: str = ""

    # feedback system
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)

    @staticmethod
    def default_schema_path() -> str:
        return str(Path(__file__).resolve().parent.parent / "storage" / "schema.sql")
