"""Slowave engine: top-level facade.

Wires SlowWave's latent CLS substrate (episodic+semantic+graph+transition+replay)
to Slowave's symbolic layer (raw events + episode text + typed schemas).
Public API for CLI and MCP integrations.
"""

from __future__ import annotations

import dataclasses
import logging
import sys
import time as _time
import uuid
from typing import Any

import numpy as np

from slowave.core.config import DEFAULT_RECALL_TOP_K, SlowaveConfig
from slowave.core.consolidation import Consolidator
from slowave.core.context import WorkingMemoryGate, WorkingMemoryState
from slowave.core.scope import normalize_scope, scope_kind
from slowave.core.services.consolidation import ConsolidationService
from slowave.core.services.feedback import FeedbackService
from slowave.core.services.ingest import IngestService
from slowave.core.services.retrieval import RecallResult, RetrievalService
from slowave.core.supersession_manifold import (
    CROSS_SCOPE_COS_THRESHOLD,
    DIR_REVIEW_BAND,
    DIRECTION_THRESHOLD,
    EXTENDED_SAME_SCOPE_COS_THRESHOLD,
    SAME_SCOPE_COS_THRESHOLD,
    SupersessionManifold,
)
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

        # encoder (lazy) — accept a pre-built shared encoder to avoid
        # reloading weights across multiple engines (e.g. in benchmarking).
        # Constructed here, before the latent substrate below, so a
        # logic_version rebuild (which needs a real encoder for schema
        # embeddings) can reuse it instead of loading a second copy.
        if shared_encoder is not None:
            self._encoder: TextEncoder | None = shared_encoder
        elif self.cfg.disable_encoder:
            self._encoder = None
        else:
            self._encoder = TextEncoder(self.cfg.encoder)

        # Auto-migration: if a release bumped current_logic_version, rebuild
        # all derived memory state from raw_events before anything below
        # reads it. Must run before EpisodicStore/SemanticStore/etc so their
        # reset_faiss_from_db() calls near the end of __init__ see
        # post-migration state. See slowave/core/services/rebuild.py and
        # private/docs/iterations/20260716_event-store-replay.md.
        from slowave.core.services.rebuild import RebuildService

        if RebuildService.needs_rebuild(self.db, self.cfg):
            try:
                if RebuildService.try_claim(self.db, self.cfg):
                    RebuildService.run(
                        self.db,
                        self.cfg,
                        encoder=self._encoder,
                        on_start=lambda: print(
                            f"Slowave: rebuilding memory for logic v{self.cfg.current_logic_version}"
                            " — one-time, may take a moment",
                            file=sys.stderr,
                        ),
                    )
                else:
                    # Another process is migrating (or just did). Wait
                    # briefly for its checkpoint rather than building our
                    # own stores against a mid-rebuild derived-table state;
                    # give up and proceed on current state if it's taking a
                    # while — self-heals on a later restart via the
                    # claim/reclaim logic in try_claim().
                    RebuildService.wait_for_completion(self.db, self.cfg)
            except Exception:
                log.exception("logic_version rebuild failed; continuing on current derived state")

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
        _transition_cfg = (
            self.cfg.transition
            if self.cfg.transition is not None
            else TransitionModelConfig(dim=self.cfg.dim)
        )
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
        replay_cfg = dataclasses.replace(
            replay_cfg, current_logic_version=self.cfg.current_logic_version
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
        self.working_memory_gate = WorkingMemoryGate()

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
            # Share the engine's own lazily-computed manifold (same instance
            # remember()'s direction_score check below uses) so the judge's
            # supersedes verdict and remember()'s inline supersession logic
            # never diverge from evaluating two independently-computed SVD1
            # axes -- constructing SupersessionManifold is cheap (it doesn't
            # compute anything until .axis is first accessed), so calling
            # _get_manifold() here doesn't defeat that laziness.
            geometric_judge=GeometricContradictionJudge(
                self.cfg.judge, manifold=self._get_manifold()
            ),
            logic_version=self.cfg.current_logic_version,
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
            encoder=self.encoder,
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

    def _get_manifold(self) -> "SupersessionManifold | None":
        if self.encoder is None:
            return None
        if self._manifold is None:
            self._manifold = SupersessionManifold(self.encoder)
        return self._manifold

    def _fetch_schema_embedding(self, schema_id: int) -> "np.ndarray | None":
        from slowave.utils.vec import unpack_f32

        conn = self.db.connect()
        row = conn.execute(
            "SELECT embedding, dim FROM schemas WHERE id = ?", (int(schema_id),)
        ).fetchone()
        if row is None or row["embedding"] is None:
            return None
        try:
            return unpack_f32(row["embedding"], int(row["dim"]))
        except Exception:
            return None

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
        goal: str | None = None,
    ) -> str:
        sid = f"sess_{uuid.uuid4().hex[:12]}"
        scope_id = normalize_scope(scope=scope)
        self.raw_log.start_session(
            session_id=sid,
            agent=agent,
            scope_id=scope_id,
            scope_kind=scope_kind(scope_id),
            ts=ts,
            goal=goal,
        )
        # Record the scope in the registry so the generalization denominator
        # (total_active_scopes) stays current without expensive table scans.
        if scope_id:
            self.schemas.scope_registry.record(scope_id, scope_kind(scope_id), is_recall=False)
        return sid

    def session_end(
        self,
        session_id: str,
        *,
        consolidate: bool = False,
        ts: int | None = None,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        """End a session: form episodes from raw events.

        consolidate=False (default): fast path — only encodes the session into
        episodic memories. No LLM call, no replay, no blocking. The agent is
        never made to wait for consolidation.

        consolidate=True: additionally runs replay + latent schema consolidation
        synchronously. Use only for tests, scripts, or explicit one-shot
        invocations. In production, leave consolidate=False and run the
        background worker (slowave worker start) or call
        `slowave worker` or `slowave consolidate` on a schedule.

        Args:
            outcome: "success", "failure", "partial", or None
        """
        self.raw_log.end_session(session_id, ts=ts, outcome=outcome)

        episode_ids = self._ingest.form_episodes(session_id)
        stats: dict[str, Any] = {"session_id": session_id, "episodes_formed": len(episode_ids)}

        # Back-link newly-formed episodes to schemas that were created via
        # remember() during this live session. During a live session, remember()
        # creates schemas with empty supporting_episode_ids and stores
        # schema_evidence rows with episode_id=NULL. The episodes are only
        # formed now, at session end, so we must update the links retroactively.
        # Without this, support_count stays 0 forever for agent-remembered facts,
        # depressing stability_score and schema_utility.
        if episode_ids:
            self._link_session_episodes(
                conn=self.db.connect(), session_id=session_id, episode_ids=episode_ids
            )

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
                    "verdict_counts": dict(cstats.verdict_counts),
                    "near_dup_intercepts": cstats.near_dup_intercepts,
                    "gate_downgrades": dict(cstats.gate_downgrades),
                    "confidence_histogram": list(cstats.confidence_histogram),
                }
        return stats

    def _link_session_episodes(self, *, conn: Any, session_id: str, episode_ids: list[int]) -> None:
        """Back-link newly-formed episodes to schemas remembered during this session.

        During a live session, ``remember()`` creates schemas with empty
        ``supporting_episode_ids`` (the episodes don't exist yet).  Now that
        they have been formed, we walk every raw event in this session,
        look up which episode(s) carry it, and update the schema row so
        ``support_count`` / stability scores reflect real evidence.
        """
        import json

        now = int(_time.time())
        try:
            # Build a raw_event_id → [episode_id, …] map from the just-formed
            # episodes.  episode_text.event_ids is a JSON array of ints.
            ep_rows = conn.execute(
                "SELECT episode_id, event_ids FROM episode_text "
                "WHERE session_id = ? AND episode_id IN ({})".format(
                    ",".join("?" * len(episode_ids))
                ),
                [session_id, *episode_ids],
            ).fetchall()

            ev_to_ep: dict[int, list[int]] = {}
            for r in ep_rows:
                ep_id = int(r["episode_id"])
                try:
                    eids = json.loads(r["event_ids"])
                except (json.JSONDecodeError, TypeError):
                    continue
                # event_ids is stored as {"ids": [1, 2, …]} (see episode_text.py:49).
                raw_ids = eids.get("ids", []) if isinstance(eids, dict) else eids
                for eid in raw_ids:
                    try:
                        ev_to_ep.setdefault(int(eid), []).append(ep_id)
                    except (TypeError, ValueError):
                        continue

            if not ev_to_ep:
                return

            # Find schemas whose schema_evidence still has episode_id=NULL
            # (the placeholder left by remember() during the live session)
            # and that reference a raw event from this session.
            key_ids = list(ev_to_ep.keys())
            ph = ",".join("?" * len(key_ids))
            schema_rows = conn.execute(
                f"SELECT DISTINCT se.schema_id, se.raw_event_id "
                f"FROM schema_evidence se "
                f"WHERE se.raw_event_id IN ({ph}) AND se.episode_id IS NULL",
                tuple(key_ids),
            ).fetchall()

            for sr in schema_rows:
                schema_id = int(sr["schema_id"])
                raw_id = sr["raw_event_id"]
                if raw_id is None:
                    continue
                try:
                    raw_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                ep_ids = ev_to_ep.get(raw_id)
                if not ep_ids:
                    continue

                # Merge into existing supporting_episode_ids.
                cur = conn.execute(
                    "SELECT supporting_episode_ids FROM schemas WHERE id = ?",
                    (schema_id,),
                ).fetchone()
                if cur is None:
                    continue
                try:
                    payload = json.loads(cur["supporting_episode_ids"])
                except (json.JSONDecodeError, TypeError):
                    payload = {}
                existing = set(
                    int(x) for x in (payload.get("ids", []) if isinstance(payload, dict) else [])
                )
                existing.update(ep_ids)
                conn.execute(
                    "UPDATE schemas SET supporting_episode_ids = ?, last_updated_ts = ? "
                    "WHERE id = ?",
                    (
                        json.dumps({"ids": sorted(existing)}),
                        now,
                        schema_id,
                    ),
                )

                # Update the schema_evidence row so future lookups don't
                # re-enter this path for the same schema.
                conn.execute(
                    "UPDATE schema_evidence SET episode_id = ? "
                    "WHERE schema_id = ? AND raw_event_id = ? AND episode_id IS NULL",
                    (ep_ids[0], schema_id, raw_id),
                )

            conn.commit()
        except Exception:
            log.warning(
                "_link_session_episodes failed for session %s",
                session_id,
                exc_info=True,
            )
            try:
                conn.rollback()
            except Exception:
                pass

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
            log.warning(
                "event_append called with empty content for session %s, using placeholder",
                session_id,
            )

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
            logic_version=self.cfg.current_logic_version,
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
            logic_version=self.cfg.current_logic_version,
        )

        superseded_schema_ids: list[int] = []

        # Geometry-based supersession and cross-scope reinforcement.
        #
        # Single pass over all scopes. Two cosine gates:
        #   SAME_SCOPE_COS_THRESHOLD  (0.85) — for same-scope supersede/reinforce/review
        #   CROSS_SCOPE_COS_THRESHOLD (0.78) — for cross-scope generalization linking
        #
        # direction_score from SupersessionManifold SVD1 axis determines action:
        #   >= DIRECTION_THRESHOLD (0.10) → value substitution
        #   in [DIR_REVIEW_BAND (0.05), DIRECTION_THRESHOLD) → ambiguous
        #   < DIR_REVIEW_BAND (0.05) → restatement / same concept
        #
        # Same scope:
        #   value substitution → supersede old schema immediately
        #   ambiguous          → flag labile, take no irreversible action
        #   restatement        → reinforce existing (salience bump)
        #
        # Different scope:
        #   same concept (dir_score < DIRECTION_THRESHOLD) → reinforce existing +
        #     record raw event as schema_evidence so _update_utility_scores can
        #     advance the generalization stage without requiring a recall event first
        #   value divergence (dir_score >= DIRECTION_THRESHOLD) → skip; cross-scope
        #     facts are allowed to diverge independently
        #
        # Language-agnostic: SupersessionManifold was calibrated on multilingual seed
        # pairs (IT/FR/DE included). No regex, no English-only patterns.
        if emb is not None:
            manifold = self._get_manifold()
            seen_ids: set[int] = {new_schema_id}
            try:
                for candidate_id, score in self.schemas.search_embedding(
                    emb, limit=10, scope_id=None
                ):
                    if candidate_id in seen_ids or score < CROSS_SCOPE_COS_THRESHOLD:
                        continue
                    try:
                        candidate = self.schemas.get(candidate_id)
                    except KeyError:
                        continue
                    if candidate.status not in ("active", "needs_review"):
                        continue

                    is_same_scope = candidate.scope_id == scope_id
                    if is_same_scope and score < EXTENDED_SAME_SCOPE_COS_THRESHOLD:
                        continue

                    candidate_emb = self._fetch_schema_embedding(candidate_id)

                    # Missing embedding → no geometric verdict possible.
                    # Profile-layer memories → geometry supersession suppressed.

                    # Profile-layer memories (preferences, constraints, habits)
                    # must not be geometry-superseded. The SVD1 supersession
                    # manifold is anti-aligned with personal preference (−0.17)
                    # and calibrated on concrete value-substitution pairs
                    # (tech/medical/business etc.). A preference flipping from
                    # "dark mode" to "light mode" is a divergence, not a
                    # replacement; treat as reinforcement.
                    _mem_layer = str(candidate.facets.get("memory_layer", "")).lower()
                    _mem_class = str(candidate.facets.get("schema_class", "")).lower()
                    _is_profile = _mem_layer == "profile" or _mem_class in {
                        "preference",
                        "interaction_preference",
                        "constraint",
                        "habit",
                        "relationship",
                    }

                    if candidate_emb is None or _is_profile:
                        # Missing embedding or profile memory — no geometric verdict.
                        # Fall through to reinforcement (same-scope) or skip
                        # (cross-scope / extended-range).
                        dir_score = 0.0
                    else:
                        dir_score = (
                            manifold.direction_score(emb, candidate_emb)
                            if manifold is not None
                            else DIRECTION_THRESHOLD
                        )

                    if is_same_scope:
                        if score >= SAME_SCOPE_COS_THRESHOLD:
                            # High-confidence topical match: full three-way decision
                            if dir_score >= DIRECTION_THRESHOLD:
                                try:
                                    self.schemas.update_status(
                                        candidate_id, status="superseded", salience=0.05
                                    )
                                    self.schemas.add_relation(
                                        src_schema_id=new_schema_id,
                                        dst_schema_id=candidate_id,
                                        relation="supersedes",
                                        confidence=1.0,
                                        reason=f"same-scope value substitution: cos={score:.3f} dir_score={dir_score:.3f}",
                                    )
                                    superseded_schema_ids.append(candidate_id)
                                    seen_ids.add(candidate_id)
                                except Exception as e:
                                    log.warning(
                                        "remember: supersession failed for schema %d: %s",
                                        candidate_id,
                                        e,
                                    )
                            elif dir_score >= DIR_REVIEW_BAND:
                                try:
                                    self.schemas.adjust_feedback_state(candidate_id, is_labile=True)
                                except (KeyError, Exception) as e:
                                    log.warning(
                                        "remember: adjust_feedback_state failed for schema %d: %s",
                                        candidate_id,
                                        e,
                                    )
                            else:
                                try:
                                    self.schemas.reinforce_schema(candidate_id, salience_delta=0.1)
                                except (KeyError, Exception) as e:
                                    log.warning(
                                        "remember: reinforce_schema failed for schema %d: %s",
                                        candidate_id,
                                        e,
                                    )
                        else:
                            # Extended range (0.70–0.85): direction_score-only supersession.
                            # Cosine is too weak to act on ambiguous cases — only clear
                            # value substitutions (dir_score >= threshold) are superseded.
                            # Catches explicit fact updates like wiki S-1/S-2 (cos ~0.80)
                            # that were previously unhandled. No reinforce/review at this range.
                            if dir_score >= DIRECTION_THRESHOLD:
                                self.schemas.update_status(
                                    candidate_id, status="superseded", salience=0.05
                                )
                                try:
                                    self.schemas.add_relation(
                                        src_schema_id=new_schema_id,
                                        dst_schema_id=candidate_id,
                                        relation="supersedes",
                                        confidence=score,
                                        reason=f"extended-range value substitution: cos={score:.3f} dir_score={dir_score:.3f}",
                                    )
                                except ValueError as e:
                                    # Reverse "supersedes" edge already exists
                                    # for this pair (add_relation's directional-
                                    # relation guard) -- a rare modeling
                                    # inconsistency; the status transition above
                                    # still applies, don't abort remember() over it.
                                    log.warning(
                                        "remember: refusing inconsistent supersedes edge: %s", e
                                    )
                                superseded_schema_ids.append(candidate_id)
                                seen_ids.add(candidate_id)
                    else:
                        if dir_score < DIRECTION_THRESHOLD:
                            try:
                                self.schemas.reinforce_schema(
                                    candidate_id,
                                    salience_delta=0.05,
                                    evidence=[(None, event_id, content, 0.5)],
                                )
                            except (KeyError, Exception) as e:
                                log.warning(
                                    "remember: cross-scope reinforce failed for schema %d: %s",
                                    candidate_id,
                                    e,
                                )
            except Exception as e:
                log.warning(
                    "remember: candidate loop iteration failed for schema %d: %s",
                    candidate_id,
                    e,
                )

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
    def consolidate_once(
        self, *, triggered_by: str = "worker", decay_idle_days: float = 30.0
    ) -> dict[str, Any]:
        return self._consolidation.consolidate_once(
            triggered_by=triggered_by, decay_idle_days=decay_idle_days
        )

    def refresh_indices(self) -> None:
        self._retrieval.refresh_indices()

    def recall(
        self,
        query: str,
        *,
        top_k: int = DEFAULT_RECALL_TOP_K,
        evidence: bool = False,
        scope: str | None = None,
        mode: str = "default",
        diagnose: bool = False,
        refresh: bool = True,
    ) -> RecallResult:
        return self._retrieval.recall(
            query,
            top_k=top_k,
            evidence=evidence,
            scope=scope,
            mode=mode,
            diagnose=diagnose,
            refresh=refresh,
        )

    def context(self, *, scope: str | None = None, limit: int = 10) -> list[Schema]:
        return self._retrieval.context(scope=scope, limit=limit)

    def context_brief(self, **kwargs: Any) -> WorkingMemoryState:
        return self._retrieval.context_brief(**kwargs)

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
            "procedures": 0,  # removed in Phase 1 P1
            "edges": self.graph.edge_count(),
        }

    def schema_health(self) -> dict[str, Any]:
        return self.schemas.health()

    def dedup_schemas_exact(self, *, dry_run: bool = True) -> dict[str, Any]:
        return self.schemas.dedup_exact(dry_run=dry_run)

    def forget_schema(self, schema_id: int, *, reason: str | None = None) -> None:
        """Suppress a schema from retrieval. CLI/dashboard-initiated only --
        deliberately not exposed as an MCP tool (see schema_store.VALID_STATUS
        comment for the trust-boundary rationale)."""
        self.schemas.forget(schema_id, reason=reason)

    def unforget_schema(self, schema_id: int) -> str:
        """Undo forget_schema(), returning the schema to its prior status."""
        return self.schemas.unforget(schema_id)

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
