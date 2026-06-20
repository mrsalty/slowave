"""Slowave engine: top-level facade.

Wires SlowWave's latent CLS substrate (episodic+semantic+graph+transition+replay)
to Slowave's symbolic layer (raw events + episode text + typed schemas).
Public API for CLI and MCP integrations.
"""

from __future__ import annotations

import dataclasses
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from slowave.core.config import SlowaveConfig
from slowave.core.consolidation import Consolidator
from slowave.core.context import WorkingMemoryGate, WorkingMemoryState
from slowave.core.procedural import ProceduralMemoryStore
from slowave.core.scope import normalize_scope, scope_kind
from slowave.core.services.consolidation import ConsolidationService
from slowave.core.services.feedback import FeedbackService
from slowave.core.services.ingest import IngestService
from slowave.core.services.retrieval import RecallResult, RetrievalService
from slowave.core.supersession import AUTO_SUPERSEDE_THRESHOLD, SupersessionCandidate, find_superseded_candidates
from slowave.core.supersession_manifold import SupersessionManifold  # available for future use
from slowave.latent.episodic_store import EpisodicStore, EpisodicStoreConfig
from slowave.latent.graph_manager import GraphManager
from slowave.latent.replay_engine import ReplayEngine
from slowave.latent.retrieval import RetrievalPipeline
from slowave.latent.salience import SalienceEngine
from slowave.latent.semantic_store import SemanticStore, SemanticStoreConfig
from slowave.latent.temporal import TemporalProbe
from slowave.latent.transition_model import TransitionModel, TransitionModelConfig
from slowave.storage.sqlite_db import SQLiteConfig, SQLiteDB
from slowave.symbolic.encoder import TextEncoder
from slowave.symbolic.episode_text import EpisodeTextStore
from slowave.symbolic.raw_log import RawLog
from slowave.symbolic.schema_store import Schema, SchemaStore

log = logging.getLogger(__name__)


def _prefix_date(text: str, ts: int) -> str:
    """Prepend an ISO date tag to an episode's text representation.

    Format: "[YYYY-MM-DD] <text>"

    Brain analogue: episodic memories are always bound to their temporal
    context — recalling an event recalls *when* it happened as part of
    the same trace.  Surfacing the date in the text lets a downstream
    answer layer (and keyword scorers) answer "when" and "how long ago" questions
    without needing a separate lookup.

    Falls back silently on any conversion error so a bad timestamp never
    breaks recall.
    """
    from datetime import datetime, timezone
    try:
        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return f"[{date_str}] {text}" if text else f"[{date_str}]"
    except Exception:
        return text



def _default_memory_layer(schema_type: str) -> str:
    """Best-effort generic layer for explicit user memories."""
    t = str(schema_type or "").strip().lower()
    if t in {"preference", "interaction_preference", "constraint", "habit", "relationship"}:
        return "profile"
    if t in {"fact", "lesson", "warning"}:
        return "domain"
    return "workspace"


# --- Backward-compatible remember() result object ---
class RememberResult(int):
    """Backward-compatible result returned by ``SlowaveEngine.remember``.

    ``RememberResult`` is an ``int`` subclass whose integer value is the
    ``event_id``. Existing callers that compare, serialize, or store the return
    value as an integer continue to work, while Python API users can access the
    created memory/schema metadata through attributes.
    """

    event_id: int
    schema_id: int
    created_schema: "Schema | None"
    superseded_schema_ids: list[int]

    def __new__(
        cls,
        event_id: int,
        *,
        schema_id: int,
        created_schema: "Schema | None" = None,
        superseded_schema_ids: list[int] | None = None,
    ) -> "RememberResult":
        obj = int.__new__(cls, event_id)
        obj.event_id = event_id
        obj.schema_id = schema_id
        obj.created_schema = created_schema
        obj.superseded_schema_ids = list(superseded_schema_ids or [])
        return obj

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation of the remember result."""
        return {
            "event_id": self.event_id,
            "schema_id": self.schema_id,
            "superseded_schema_ids": list(self.superseded_schema_ids),
        }


class SlowaveEngine:
    def __init__(
        self,
        cfg: SlowaveConfig | None = None,
        *,
        shared_encoder: "TextEncoder | None" = None,
    ):
        self.cfg = cfg or SlowaveConfig()
        schema_path = self.cfg.schema_path or SlowaveConfig.default_schema_path()

        self.db = SQLiteDB(SQLiteConfig(path=self.cfg.db_path))
        self.db.init_schema(schema_path)

        # latent substrate (SlowWave)
        self.salience = SalienceEngine(self.cfg.salience)
        self.episodic = EpisodicStore(
            self.db, EpisodicStoreConfig(dim=self.cfg.dim, db_path=self.cfg.db_path)
        )
        self.semantic = SemanticStore(self.db, SemanticStoreConfig(dim=self.cfg.dim))
        self.graph = GraphManager(self.db, self.cfg.graph)
        # Stage 3: TransitionModel is always instantiated so predictive completion
        # fires in every benchmark run. The trained_steps == 0 guard in predict()
        # keeps it inert until at least one consolidation pass has run, so there
        # is no cost during the first session before any graph edges exist.
        # An explicit cfg.transition lets callers override dim or other params;
        # the default auto-derives dim from cfg.dim.
        _transition_cfg = self.cfg.transition if self.cfg.transition is not None else TransitionModelConfig(dim=self.cfg.dim)
        self.transition_model = TransitionModel(_transition_cfg)
        # Attach graph and semantic stores for graph-based prediction
        self.transition_model.attach_stores(self.graph, self.semantic)
        # Apply assignment_threshold shorthand if set in SlowaveConfig.
        # This overrides whatever is in cfg.replay so callers don't have to
        # construct a full ReplayConfig just to tune this one parameter.
        replay_cfg = self.cfg.replay
        if self.cfg.assignment_threshold is not None:
            replay_cfg = dataclasses.replace(
                replay_cfg,
                assignment_threshold=self.cfg.assignment_threshold,
                coarse_assignment_threshold=self.cfg.assignment_threshold,
            )
        self.replay_engine = ReplayEngine(
            db=self.db,
            episodic=self.episodic,
            semantic=self.semantic,
            graph=self.graph,
            salience=self.salience,
            transition_model=self.transition_model,
            cfg=replay_cfg,
        )
        self.retrieval = RetrievalPipeline(
            episodic=self.episodic,
            semantic=self.semantic,
            graph=self.graph,
            cfg=self.cfg.retrieval,
            # Stage 3: pass the trained transition model so retrieval can
            # use predicted next-state embeddings as a second cosine seed.
            transition_model=self.transition_model,
        )
        # Stage 5: let the replay engine rehearse retrieval against
        # prototype membership during the worker pass.
        self.replay_engine.attach_retrieval(self.retrieval)

        # symbolic layer
        self.raw_log = RawLog(self.db)
        self.episode_text = EpisodeTextStore(self.db)
        self.schemas = SchemaStore(self.db, dim=self.cfg.dim)
        self.procedures = ProceduralMemoryStore(self.db, self.cfg.procedural)
        self.working_memory_gate = WorkingMemoryGate()

        # encoder (lazy) — accept a pre-built shared encoder to avoid
        # reloading weights across multiple engines (e.g. in benchmarking).
        if shared_encoder is not None:
            self._encoder: TextEncoder | None = shared_encoder
        elif self.cfg.disable_encoder:
            self._encoder = None
        else:
            self._encoder = TextEncoder(self.cfg.encoder)

        # SupersessionManifold: lazy-computed SVD1 direction axis for P2.
        self._manifold: SupersessionManifold | None = None

        # Latent consolidator: schemas are prototype geometry + lexical signatures.
        # Zero LLM calls in ingest, consolidation, and retrieval.
        from slowave.latent.schema import (
            GeometricContradictionJudge,
            LatentSchemaBuilder,
        )

        self.consolidator: Consolidator | None = Consolidator(
            db=self.db,
            semantic=self.semantic,
            episode_text=self.episode_text,
            schemas=self.schemas,
            encoder=self.encoder,
            latent_builder=LatentSchemaBuilder(),
            geometric_judge=GeometricContradictionJudge(),
        )
        # The latent consolidator needs episode embeddings + ts.
        self.consolidator._episodic_store_ref = self.episodic

        # Stage 10 — temporal probe (embedding-space temporal compass).
        # Built once if an encoder is available; None otherwise (no-op at
        # recall time).  The probe pre-embeds 12 temporal-landmark phrases
        # so estimate_anchor() is just 12 dot products at query time.
        self._temporal_probe: TemporalProbe | None = None
        if self.encoder is not None:
            try:
                self._temporal_probe = TemporalProbe(self.encoder.encode)
            except Exception as e:
                log.warning("temporal probe init failed (will use now() fallback): %s", e)

        # services — order matters: _ingest first, then services that depend on it
        self._ingest = IngestService(
            raw_log=self.raw_log,
            episodic=self.episodic,
            episode_text=self.episode_text,
            salience=self.salience,
            transition_model=self.transition_model,
            db=self.db,
        )
        self._consolidation = ConsolidationService(
            db=self.db,
            replay_engine=self.replay_engine,
            consolidator=self.consolidator,
            schemas=self.schemas,
            ingest=self._ingest,
        )
        self._retrieval = RetrievalService(
            episodic=self.episodic,
            semantic=self.semantic,
            graph=self.graph,
            schemas=self.schemas,
            encoder=self.encoder,
            episode_text=self.episode_text,
            raw_log=self.raw_log,
            retrieval=self.retrieval,
            transition_model=self.transition_model,
            temporal_probe=self._temporal_probe,
            working_memory_gate=self.working_memory_gate,
            db=self.db,
            retrieval_cfg=self.cfg.retrieval,
        )
        self._feedback = FeedbackService(
            db=self.db,
            schemas=self.schemas,
            procedures=self.procedures,
            cfg=self.cfg.feedback,
        )

        # rebuild FAISS indices from DB
        self.episodic.reset_faiss_from_db()
        self.semantic.reset_faiss_from_db()

    @property
    def encoder(self) -> "TextEncoder | None":
        return self._encoder

    @encoder.setter
    def encoder(self, value: "TextEncoder | None") -> None:
        self._encoder = value
        if self._manifold is not None:
            self._manifold.invalidate()
        # Propagate to services that hold their own encoder reference so that
        # post-construction assignment (e.g. test monkey-patching) stays in sync.
        if hasattr(self, "_retrieval"):
            self._retrieval.encoder = value

    @classmethod
    def from_config(
        cls,
        cfg: "SlowaveConfig | None" = None,
        *,
        shared_encoder: "TextEncoder | None" = None,
    ) -> "SlowaveEngine":
        """Canonical construction entry point. Prefer this over calling the
        constructor directly — the name makes intent explicit and call sites
        become easy to grep for engine construction."""
        return cls(cfg, shared_encoder=shared_encoder)

    # ---- sessions ----------------------------------------------------------
    def session_start(
        self,
        *,
        agent: str,
        scope: str | None = None,
        ts: int | None = None,
    ) -> str:
        sid = f"sess_{uuid.uuid4().hex[:12]}"
        scope_id = normalize_scope(scope=scope)
        self.raw_log.start_session(
            session_id=sid,
            agent=agent,
            scope_id=scope_id,
            scope_kind=scope_kind(scope_id),
            ts=ts,
        )
        # Record the scope in the registry so the generalization denominator
        # (total_active_scopes) stays current without expensive table scans.
        if scope_id:
            self.schemas.scope_registry.record(
                scope_id, scope_kind(scope_id), is_recall=False
            )
        return sid

    def session_end(self, session_id: str, *, consolidate: bool = False, ts: int | None = None) -> dict[str, Any]:
        """End a session: form episodes from raw events.

        consolidate=False (default): fast path — only encodes the session into
        episodic memories. No LLM call, no replay, no blocking. The agent is
        never made to wait for consolidation.

        consolidate=True: additionally runs replay + latent schema consolidation
        synchronously. Use only for tests, scripts, or explicit one-shot
        invocations. In production, leave consolidate=False and run the
        background worker (slowave worker start) or call
        `slowave worker` or `slowave consolidate` on a schedule.
        """
        self.raw_log.end_session(session_id, ts=ts)
        episode_ids = self._ingest.form_episodes(session_id)
        stats: dict[str, Any] = {"session_id": session_id, "episodes_formed": len(episode_ids)}
        if consolidate:
            replay_stats = self.replay_engine.replay_once()
            stats["replay"] = replay_stats
            if self.consolidator is not None:
                # Consolidate the prototypes touched by this replay's mapped episodes.
                # Touched prototypes are those that have at least one of our new
                # episodes mapped to them, but we conservatively grab all current
                # prototypes that have a mapped episode in this session.
                touched = self._ingest.prototypes_for_episodes(episode_ids)
                cstats = self.consolidator.consolidate(prototype_ids=touched)
                stats["consolidation"] = {
                    "prototypes_processed": cstats.prototypes_processed,
                    "schemas_created": cstats.schemas_created,
                    "schemas_reinforced": cstats.schemas_reinforced,
                    "schemas_contradicted": cstats.schemas_contradicted,
                    "schemas_skipped": cstats.schemas_skipped,
                }
        return stats

    # ---- ingest -----------------------------------------------------------
    def event_append(
        self,
        *,
        session_id: str,
        type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        ts: int | None = None,
    ) -> int:
        # Sanitize content: strip whitespace and handle empty strings.
        # This prevents the error "messages: text content blocks must be non-empty"
        # from downstream Claude API calls. Empty content is logged with a placeholder.
        content_stripped = str(content).strip() if content else ""
        if not content_stripped:
            content_stripped = "[empty content]"
            log.warning("event_append called with empty content for session %s, using placeholder", session_id)

        # Graceful degradation: if the session_id doesn't exist in the sessions
        # table (e.g. the caller used "placeholder" or forgot to call
        # session_start), auto-register it as an ad-hoc session rather than
        # crashing with a FOREIGN KEY constraint failed error.
        # This is the most common mistake made by AI agents (including Claude Code)
        # when they skip the session_start → event → session_end lifecycle.
        if not self.raw_log.session_exists(session_id):
            log.warning(
                "event_append: session_id %r not found in sessions table — "
                "auto-registering as ad-hoc session. Call slowave_session_start "
                "first to associate events with a proper session.",
                session_id,
            )
            self.raw_log.start_session(
                session_id=str(session_id),
                agent="adhoc",
                ts=ts,
            )

        emb = None
        if self.encoder is not None:
            try:
                emb = self.encoder.encode(content_stripped)
            except Exception as e:
                log.warning("encoder failed: %s", e)
        return self.raw_log.append(
            session_id=session_id,
            type=type,
            content=content_stripped,
            metadata=metadata,
            embedding=emb,
            ts=ts,
        )

    def remember(
        self,
        *,
        content: str,
        type: str = "decision",
        session_id: str | None = None,
        agent: str = "cli",
        scope: str | None = None,
    ) -> RememberResult:
        """Explicit user-driven memory. Logged as a high-salience event.

        Two paths depending on whether a live session_id is provided:

        - No session_id: create an ad-hoc session, append the event, end
          the session immediately, form episodes, then create the schema
          backed by those episodes.  Fully self-contained; nothing leaks
          into any other session.

        - session_id provided: append the remember event to the caller's
          live session (it will be encoded into episodes when the caller
          eventually calls session_end), then create the schema immediately
          with an empty episode list.  The session is NOT ended here — that
          is the caller's responsibility.  This avoids double episode
          formation: once here and again when session_end runs.

        Returns a ``RememberResult``. It behaves like the old integer event id
        for backward compatibility, and also exposes ``event_id``, ``schema_id``,
        ``created_schema``, and ``superseded_schema_ids`` for Python API users.
        """
        caller_owns_session = session_id is not None

        if not caller_owns_session:
            session_id = self.session_start(agent=agent, scope=scope)

        event_id = self.event_append(
            session_id=session_id,
            type=f"remember:{type}",
            content=content,
            metadata={"explicit": True, "declared_type": type},
        )

        emb = self.encoder.encode(content) if self.encoder is not None else None

        if caller_owns_session:
            # The caller's session is still live — do not end or re-encode it.
            # Create the schema immediately so it is available for recall, but
            # leave supporting_episode_ids empty; the episodes will be formed
            # and linked during the caller's session_end.
            episode_ids: list[int] = []
        else:
            # Ad-hoc session: close it and form episodes right now so the
            # schema is immediately backed by episodic evidence.
            self.raw_log.end_session(session_id)
            episode_ids = self._ingest.form_episodes(session_id)

        scope_id = normalize_scope(scope=scope)
        new_schema_id = self.schemas.create(
            content_text=content,
            facets={
                "schema_class": type,
                "source": "explicit_remember",
                "source_kind": "explicit_remember",
                "memory_layer": _default_memory_layer(type),
                "injectable": True,
            },
            tags=[type, "explicit"],
            embedding=emb,
            scope_id=scope_id,
            confidence=1.0,
            salience=1.4,
            supporting_episode_ids=episode_ids,
            evidence=[(episode_ids[0] if episode_ids else None, event_id, content, 1.0)],
        )

        superseded_schema_ids: list[int] = []

        # Pattern-based deterministic supersession (before geometric check).
        # Detects explicit update signals like "now uses", "switched from X to Y", etc.
        # Only applies to explicit_remember; doesn't interfere with geometric logic below.
        pattern_candidates: list[SupersessionCandidate] = []
        try:
            pattern_candidates = find_superseded_candidates(
                new_content=content,
                scope_id=scope_id,
                schemas=self.schemas,
            )
            for cand in pattern_candidates:
                if cand.confidence >= AUTO_SUPERSEDE_THRESHOLD:
                    # Auto-supersede: high confidence pattern match
                    try:
                        self.schemas.update_status(cand.old_schema_id, status="superseded", salience=0.05)
                        self.schemas.add_relation(
                            src_schema_id=new_schema_id,
                            dst_schema_id=cand.old_schema_id,
                            relation="supersedes",
                            confidence=cand.confidence,
                        )
                        if cand.old_schema_id not in superseded_schema_ids:
                            superseded_schema_ids.append(cand.old_schema_id)
                    except (KeyError, Exception):
                        pass
                else:
                    # Below threshold: mark for review instead
                    try:
                        self.schemas.adjust_feedback_state(cand.old_schema_id, needs_review=True)
                    except (KeyError, Exception):
                        pass
        except Exception:
            # Graceful fallback: pattern supersession should never break remember()
            pass

        # P2: Cosine-based supersession fallback — fires when regex P1 finds nothing.
        # Two thresholds, both flag needs_review only (never auto-supersede):
        #   ≥0.85: near-verbatim or very similar → almost certainly a value update
        #   ≥0.50: moderately similar → plausible value update, worth human review
        # Threshold calibrated for paraphrase-multilingual-MiniLM-L12-v2 cosine
        # distribution: supersession mean ≈ 0.68, additive mean ≈ 0.36.
        if not pattern_candidates and emb is not None:
            try:
                p1_ids = {c.old_schema_id for c in pattern_candidates}
                for sid, cosine_score in self.schemas.search_embedding(
                    emb, limit=10, scope_id=scope_id
                ):
                    if sid in p1_ids:
                        continue
                    if cosine_score >= 0.50:
                        try:
                            self.schemas.adjust_feedback_state(sid, needs_review=True)
                        except (KeyError, Exception):
                            continue
            except Exception:
                pass

        # Supersession: if this explicit memory contradicts an existing
        # active schema on the same topic, mark the old one superseded.
        # Uses a high cosine threshold (0.85) so only genuinely same-topic
        # schemas are affected — "I use MySQL" is superseded by "I switched
        # to PostgreSQL", but unrelated memories are never touched.
        # This is the explicit-path counterpart to the consolidation path's
        # geometric contradiction judge, and it enables belief-revision
        # silencing (_schema_priors) to fire immediately at recall time
        # without waiting for the next consolidation pass.
        if emb is not None:
            for candidate_id, score in self.schemas.search_embedding(
                emb, limit=10, scope_id=scope_id
            ):
                if candidate_id == new_schema_id or score < 0.85:
                    continue
                try:
                    candidate = self.schemas.get(candidate_id)
                except KeyError:
                    continue
                if candidate.status not in ("active", "needs_review"):
                    continue
                if candidate.last_updated_ts < int(time.time()):
                    self.schemas.update_status(
                        candidate_id, status="superseded", salience=0.05
                    )
                    self.schemas.add_relation(
                        src_schema_id=new_schema_id,
                        dst_schema_id=candidate_id,
                        relation="supersedes",
                        confidence=1.0,
                    )
                    if candidate_id not in superseded_schema_ids:
                        superseded_schema_ids.append(candidate_id)

        try:
            created_schema = self.schemas.get(new_schema_id)
        except KeyError:
            created_schema = None

        return RememberResult(
            event_id,
            schema_id=new_schema_id,
            created_schema=created_schema,
            superseded_schema_ids=superseded_schema_ids,
        )

    # ---- consolidation ----------------------------------------------------
    def consolidate_once(self, *, triggered_by: str = "worker") -> dict[str, Any]:
        return self._consolidation.consolidate_once(triggered_by=triggered_by)
    def refresh_indices(self) -> None:
        self._retrieval.refresh_indices()

    def recall(
        self,
        query: str,
        *,
        top_k: int = 5,
        evidence: bool = False,
        scope: str | None = None,
        mode: str = "default",
    ) -> RecallResult:
        return self._retrieval.recall(query, top_k=top_k, evidence=evidence, scope=scope, mode=mode)

    def context(self, *, scope: str | None = None, limit: int = 10) -> list[Schema]:
        return self._retrieval.context(scope=scope, limit=limit)

    def context_brief(self, **kwargs: Any) -> WorkingMemoryState:
        return self._retrieval.context_brief(**kwargs)

    def retrieve_procedures(
        self,
        *,
        query: str | None = None,
        scope: str | None = None,
        goal: str | None = None,
        task_type: str | None = None,
        situation: dict[str, Any] | None = None,
        requirements: list[str] | tuple[str, ...] | None = None,
        topics: list[str] | tuple[str, ...] | None = None,
        entities: list[str] | tuple[str, ...] | None = None,
        limit: int | None = None,
        mode: str = "default",
    ):
        scope_id = normalize_scope(scope=scope)
        return self.procedures.retrieve(
            scope_id=scope_id,
            goal=goal,
            task_type=task_type,
            situation=situation or {},
            requirements=list(requirements or []),
            query=query,
            topics=topics or [],
            entities=entities or [],
            limit=limit,
            mode=mode,
        )

    def remember_procedure(
        self,
        *,
        procedure_steps: list[str],
        goal: str | None = None,
        task_type: str | None = None,
        scope: str | None = None,
        situation: dict[str, Any] | None = None,
        requirements: list[str] | None = None,
        trigger_pattern: list[str] | None = None,
        confidence: float = 0.7,
        status: str = "active",
    ) -> int:
        scope_id = normalize_scope(scope=scope)
        return self.procedures.create(
            origin_scope_id=scope_id,
            origin_scope_kind=scope_kind(scope_id),
            goal=goal,
            task_type=task_type,
            situation_signature=situation or {},
            requirements=requirements or [],
            trigger_pattern=trigger_pattern or [],
            procedure_steps=procedure_steps,
            confidence=confidence,
            status=status,
        )

    def promote_procedure_candidates_from_feedback(self) -> dict[str, Any]:
        """Deterministically promote repeated successful feedback into candidates."""
        return self.procedures.promote_candidates_from_feedback()

    # ---- inspection -------------------------------------------------------
    def get_schema(self, schema_id: int) -> Schema:
        return self.schemas.get(schema_id)

    def list_schemas(self, **kwargs: Any) -> list[Schema]:
        return self.schemas.list(**kwargs)

    def stats(self) -> dict[str, Any]:
        return {
            "episodes": self.episodic.count(),
            "prototypes": self.semantic.count(),
            "schemas": self.schemas.count(),
            "procedures": self.procedures.count(),
            "edges": self.graph.edge_count(),
        }

    def schema_health(self) -> dict[str, Any]:
        return self.schemas.health()

    def dedup_schemas_exact(self, *, dry_run: bool = True) -> dict[str, Any]:
        return self.schemas.dedup_exact(dry_run=dry_run)

    def decay_schemas(self, *, idle_days: float = 30.0, dry_run: bool = False) -> dict[str, Any]:
        """Decay salience of active schemas that have never been recalled.

        Wraps ``SchemaStore.decay_unused``. Exposed here so the CLI and MCP
        can trigger decay independently of a full consolidation pass.
        """
        return self.schemas.decay_unused(idle_days=idle_days, dry_run=dry_run)

    def close(self) -> None:
        self.db.close()

    def record_retrieval(self, **kwargs: Any) -> None:
        self._feedback.record_retrieval(**kwargs)

    def record_context_recall(self, *, context_id: str, **kwargs: Any) -> None:
        self._feedback.record_context_recall(context_id=context_id, **kwargs)

    def retrieval_feedback(self, **kwargs: Any) -> dict[str, Any]:
        return self._feedback.retrieval_feedback(**kwargs)

    def context_feedback(self, *, context_id: str, **kwargs: Any) -> dict[str, Any]:
        return self._feedback.context_feedback(context_id=context_id, **kwargs)

