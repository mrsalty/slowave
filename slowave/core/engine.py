"""Slowave engine: top-level facade.

Wires SlowWave's latent CLS substrate (episodic+semantic+graph+transition+replay)
to Slowave's symbolic layer (raw events + episode text + typed schemas + LLM
extraction). Public API for CLI and MCP integrations.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np

from slowave.core.config import SlowaveConfig
from slowave.core.consolidation import ConsolidationStats, Consolidator
from slowave.latent.episodic_store import EpisodicStore, EpisodicStoreConfig
from slowave.latent.graph_manager import GraphManager
from slowave.latent.replay_engine import ReplayEngine
from slowave.latent.retrieval import RetrievalPipeline
from slowave.latent.salience import SalienceEngine
from slowave.latent.semantic_store import SemanticStore, SemanticStoreConfig
from slowave.latent.transition_model import TransitionModel, TransitionModelConfig
from slowave.latent.types import RetrievedMemorySet
from slowave.llm import make_backend
from slowave.storage.sqlite_db import SQLiteConfig, SQLiteDB
from slowave.symbolic.contradiction import ContradictionJudge
from slowave.symbolic.encoder import TextEncoder
from slowave.symbolic.episode_text import EpisodeTextStore
from slowave.symbolic.raw_log import RawLog
from slowave.symbolic.schema_extractor import SchemaExtractor
from slowave.symbolic.schema_store import Schema, SchemaStore

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecallResult:
    """Recall result: schemas + episodes + raw events with provenance."""
    schemas: list[Schema]
    episode_texts: list[dict[str, Any]]  # episode_id, content_text, salience
    raw_events: list[dict[str, Any]]     # id, content, ts, type
    expanded_neighbors: dict[int, list[tuple[int, float]]]


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
        tcfg = self.cfg.transition or TransitionModelConfig(dim=self.cfg.dim)
        self.transition_model = TransitionModel(tcfg)
        self.replay_engine = ReplayEngine(
            db=self.db, episodic=self.episodic, semantic=self.semantic,
            graph=self.graph, salience=self.salience,
            transition_model=self.transition_model, cfg=self.cfg.replay,
        )
        self.retrieval = RetrievalPipeline(
            episodic=self.episodic, semantic=self.semantic, graph=self.graph,
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

        # encoder (lazy) — accept a pre-built shared encoder to avoid
        # reloading weights across multiple engines (e.g. in benchmarking).
        if shared_encoder is not None:
            self.encoder: TextEncoder | None = shared_encoder
        elif self.cfg.disable_encoder:
            self.encoder = None
        else:
            self.encoder = TextEncoder(self.cfg.encoder)

        # consolidator (optional). Two paths:
        #   schema_mode == "llm"    — original path, LLM extracts schemas
        #   schema_mode == "latent" — Stage 6, schemas are prototype geometry
        # The "latent" path does NOT need an LLM and can run even when
        # disable_llm is True (the disable_llm flag becomes irrelevant
        # for brain-only mode — there is no LLM to disable).
        self.consolidator: Consolidator | None = None
        if self.cfg.schema_mode == "latent":
            from slowave.latent.schema import (
                GeometricContradictionJudge,
                LatentSchemaBuilder,
            )
            self.consolidator = Consolidator(
                db=self.db, semantic=self.semantic, episode_text=self.episode_text,
                schemas=self.schemas, extractor=None, judge=None,
                encoder=self.encoder,
                latent_builder=LatentSchemaBuilder(),
                geometric_judge=GeometricContradictionJudge(),
            )
            # The latent consolidator needs episode embeddings + ts. Pass
            # the episodic store via attribute (kept off __init__ so the
            # LLM-mode constructor signature is unchanged for callers).
            self.consolidator._episodic_store_ref = self.episodic
        elif not self.cfg.disable_llm:
            raw_llm = make_backend(self.cfg.llm)
            llm = _CountingLLM(raw_llm)
            self._counting_llm = llm  # exposed for harness instrumentation
            extractor = SchemaExtractor(llm, min_confidence=self.cfg.schema_min_confidence)
            judge = ContradictionJudge(llm)
            self.consolidator = Consolidator(
                db=self.db, semantic=self.semantic, episode_text=self.episode_text,
                schemas=self.schemas, extractor=extractor, judge=judge, encoder=self.encoder,
            )

        # rebuild FAISS indices from DB
        self.episodic.reset_faiss_from_db()
        self.semantic.reset_faiss_from_db()

    # ---- sessions ----------------------------------------------------------
    def session_start(self, *, agent: str, project: str | None = None) -> str:
        sid = f"sess_{uuid.uuid4().hex[:12]}"
        self.raw_log.start_session(session_id=sid, agent=agent, project=project)
        return sid

    def session_end(self, session_id: str, *, consolidate: bool = False) -> dict[str, Any]:
        """End a session: form episodes from raw events.

        consolidate=False (default): fast path — only encodes the session into
        episodic memories. No LLM call, no replay, no blocking. The agent is
        never made to wait for consolidation.

        consolidate=True: additionally runs replay + LLM schema extraction
        synchronously. Use only for tests, scripts, or explicit one-shot
        invocations. In production, leave consolidate=False and run the
        background worker (slowave worker start) or call
        slowave_consolidate / `slowave consolidate` on a schedule.
        """
        self.raw_log.end_session(session_id)
        episode_ids = self._form_episodes_from_session(session_id)
        stats: dict[str, Any] = {"session_id": session_id, "episodes_formed": len(episode_ids)}
        if consolidate:
            replay_stats = self.replay_engine.replay_once()
            stats["replay"] = replay_stats
            if self.consolidator is not None:
                # Consolidate the prototypes touched by this replay's mapped episodes.
                # Touched prototypes are those that have at least one of our new
                # episodes mapped to them, but we conservatively grab all current
                # prototypes that have a mapped episode in this session.
                touched = self._prototypes_for_episodes(episode_ids)
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
    ) -> int:
        emb = None
        if self.encoder is not None:
            try:
                emb = self.encoder.encode(content)
            except Exception as e:
                log.warning("encoder failed: %s", e)
        return self.raw_log.append(
            session_id=session_id, type=type, content=content,
            metadata=metadata, embedding=emb,
        )

    def remember(
        self,
        *,
        content: str,
        type: str = "decision",
        session_id: str | None = None,
        agent: str = "cli",
        project: str | None = None,
    ) -> int:
        """Explicit user-driven memory. Logged as a high-salience event.

        Creates an ad-hoc session if none provided.
        """
        if session_id is None:
            session_id = self.session_start(agent=agent, project=project)
        event_id = self.event_append(
            session_id=session_id, type=f"remember:{type}", content=content,
            metadata={"explicit": True, "declared_type": type},
        )
        # Explicit memory bypasses LLM/replay: the user already provided the
        # durable typed claim. Create an immediate schema and episode.
        if session_id is not None:
            self.raw_log.end_session(session_id)
            episode_ids = self._form_episodes_from_session(session_id)
            emb = self.encoder.encode(content) if self.encoder is not None else None
            self.schemas.create(
                content_text=content,
                facets={"schema_class": type, "source": "explicit_remember"},
                tags=[type, "explicit"],
                embedding=emb,
                project=project,
                confidence=1.0,
                salience=1.4,
                supporting_episode_ids=episode_ids,
                evidence=[(episode_ids[0] if episode_ids else None, event_id, content, 1.0)],
            )
        return event_id

    # ---- recall -----------------------------------------------------------
    def refresh_indices(self) -> None:
        """Rebuild in-memory FAISS indices from SQLite.

        Required when this engine instance may be reading data written by a
        different process or a sibling engine (e.g. the MCP server caches
        multiple engine variants, and one may write while another reads).
        Cheap for MVP scale (~1k-100k vectors).
        """
        self.episodic.reset_faiss_from_db()
        self.semantic.reset_faiss_from_db()

    def recall(self, query: str, *, top_k: int = 5, evidence: bool = False) -> RecallResult:
        if self.encoder is None:
            raise RuntimeError("recall requires an encoder; cfg.disable_encoder=True")
        self.refresh_indices()
        q = self.encoder.encode(query)
        retrieved: RetrievedMemorySet = self.retrieval.retrieve(q)

        # Schema-first semantic recall, plus prototype-associated schemas.
        schema_scores: dict[int, float] = {}
        for sid, score in self.schemas.search_embedding(q, limit=max(20, top_k * 4)):
            schema_scores[sid] = max(schema_scores.get(sid, -1e9), score + 0.25)
        for sid in self.schemas.search_fts(query, limit=max(10, top_k * 2)):
            schema_scores[sid] = max(schema_scores.get(sid, -1e9), 0.35)
        proto_ids = [p.id for p in retrieved.prototypes]
        for s in self.schemas.get_many_by_prototypes(proto_ids):
            schema_scores[s.id] = max(schema_scores.get(s.id, -1e9), 0.15 + s.salience * 0.05)
        schemas_all = self.schemas.get_many(schema_scores.keys())
        schemas = sorted(
            schemas_all,
            key=lambda s: schema_scores.get(s.id, 0.0) + 0.1 * s.salience,
            reverse=True,
        )[:top_k]
        for s in schemas:
            self.schemas.reinforce(s.id, amount=0.05)

        # ---- Schemas-as-priors + belief-revision silencing (Stage 2) ----
        # Brain-inspired rationale:
        #   M1 (steering): a matched neocortical schema biases the hippocampus
        #       to recall evidence consistent with it.
        #   M2 (belief revision): a superseded / contradicted schema actively
        #       suppresses recall of the episodes that supported it.
        # Both effects apply to the candidate pool returned by RetrievalPipeline;
        # they never add new candidates and the magnitudes are small so cosine
        # still dominates when schemas are absent or noisy.
        prior_boost, silence_factor = self._schema_priors(
            candidate_episode_ids=[int(m.id) for m in retrieved.episodic],
            matched_schema_scores=schema_scores,
            matched_schemas=schemas_all,
        )

        # Episode text — apply priors / silencing AFTER the latent ranker.
        ep_texts = self.episode_text.get_many([m.id for m in retrieved.episodic])
        ep_by_id = {e.episode_id: e for e in ep_texts}
        scored_pairs: list[tuple[float, Any]] = []
        n_ep = len(retrieved.episodic)
        for rank, m in enumerate(retrieved.episodic):
            base = 1.0 - (rank / max(1, n_ep))
            eid = int(m.id)
            score = (base + prior_boost.get(eid, 0.0)) * silence_factor.get(eid, 1.0)
            scored_pairs.append((score, m))
        scored_pairs.sort(key=lambda t: t[0], reverse=True)

        episode_dicts = []
        for _score, m in scored_pairs[: top_k]:
            ep = ep_by_id.get(m.id)
            episode_dicts.append({
                "id": m.id,
                "content_text": ep.content_text if ep else "",
                "salience": float(m.salience),
                "ts": int(m.ts),
                "schema_prior_boost": round(float(prior_boost.get(int(m.id), 0.0)), 4),
                "schema_silence_factor": round(float(silence_factor.get(int(m.id), 1.0)), 4),
            })

        # Optional drill to raw events for evidence.
        raw_events_out: list[dict[str, Any]] = []
        if evidence:
            wanted: list[int] = []
            for s in schemas:
                for ev in self.schemas.evidence_for_schema(s.id, limit=5):
                    if ev.raw_event_id is not None:
                        wanted.append(ev.raw_event_id)
                    elif ev.episode_id is not None:
                        ep = self.episode_text.get(ev.episode_id)
                        if ep is not None:
                            wanted.extend(ep.event_ids[:3])
            for ep in ep_texts:
                wanted.extend(ep.event_ids[:3])
            seen = set()
            for rid in wanted:
                if rid in seen:
                    continue
                seen.add(rid)
                try:
                    e = self.raw_log.get(rid)
                except KeyError:
                    continue
                raw_events_out.append({
                    "id": e.id, "ts": e.ts, "type": e.type, "content": e.content,
                })

        return RecallResult(
            schemas=schemas,
            episode_texts=episode_dicts,
            raw_events=raw_events_out,
            expanded_neighbors=retrieved.expanded_neighbors,
        )

    def context(self, *, project: str | None = None, limit: int = 10) -> list[Schema]:
        """Return a memory brief: top active schemas, optionally project-scoped."""
        return self.schemas.list(limit=limit, project=project, status="active")

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
            "edges": self.graph.edge_count(),
        }

    def schema_health(self) -> dict[str, Any]:
        return self.schemas.health()

    def dedup_schemas_exact(self, *, dry_run: bool = True) -> dict[str, Any]:
        return self.schemas.dedup_exact(dry_run=dry_run)

    def close(self) -> None:
        self.db.close()

    # ---- internals --------------------------------------------------------
    def _schema_priors(
        self,
        *,
        candidate_episode_ids: list[int],
        matched_schema_scores: dict[int, float],
        matched_schemas: list[Schema],
    ) -> tuple[dict[int, float], dict[int, float]]:
        """Compute schemas-as-priors boosts and belief-revision silences.

        For each candidate episode, look up all schemas whose evidence points
        at it and combine:

          * ``active`` / ``needs_review`` schemas that *also match the query*
            inject a small additive boost (proportional to query-similarity
            and schema confidence). Brain analogue: cortical priors steering
            hippocampal recall toward consistent evidence.

          * ``superseded`` / ``contradicted`` schemas inject a multiplicative
            damping factor with a freshness term (recent supersessions
            silence harder; old ones fade toward 1.0). Brain analogue:
            belief revision / use-dependent suppression.

        The bias magnitudes are deliberately small: schemas should tilt
        ties, not overwhelm cosine. If schemas are absent or noisy, the
        cosine ranking is recovered exactly.
        """
        if not candidate_episode_ids:
            return {}, {}
        ep_schema_index = self.schemas.schemas_for_episodes(candidate_episode_ids)
        # Pre-index query-similarity for matched schemas. ``matched_schema_scores``
        # carries the additive offsets that ``recall`` adds during the
        # schema-channel ranking (+0.25 for embed, +0.35 for FTS, etc.).
        # Subtract the offset to recover a sane [0, 1] similarity.
        offsets = {"embed": 0.25, "fts": 0.35, "proto": 0.15}
        matched_q_score: dict[int, float] = {}
        for s in matched_schemas:
            raw = matched_schema_scores.get(int(s.id), 0.0)
            qsim = max(0.0, min(1.0, raw - offsets["embed"]))
            if qsim > 0.0:
                matched_q_score[int(s.id)] = qsim

        now_ts = int(time.time())
        # 14-day half-life: a fresh supersede silences hard, an ancient one
        # is barely felt. The exact value is a knob worth ablating but is
        # benchmark-agnostic.
        silence_halflife_s = 14.0 * 86400.0
        prior_boost: dict[int, float] = {}
        silence_factor: dict[int, float] = {}
        for eid, entries in ep_schema_index.items():
            for sid, status, conf, last_ts in entries:
                if status in ("active", "needs_review"):
                    qsim = matched_q_score.get(sid)
                    if qsim is None:
                        continue
                    # Steering bias: small additive ~ qsim * confidence.
                    boost = 0.08 * float(qsim) * float(conf)
                    prior_boost[eid] = max(prior_boost.get(eid, 0.0), boost)
                elif status in ("superseded", "contradicted"):
                    age = max(0.0, float(now_ts - int(last_ts)))
                    fresh = 0.5 ** (age / silence_halflife_s)
                    damp = 0.6 * fresh * float(conf)  # ≤ 60% damp
                    factor = max(0.05, 1.0 - damp)
                    silence_factor[eid] = min(silence_factor.get(eid, 1.0), factor)
        return prior_boost, silence_factor


    def _form_episodes_from_session(self, session_id: str) -> list[int]:
        """Convert a session's raw events into multi-scale episodes.

        Brain-inspired strategy: encode both local event fragments
        (micro-episodes) and a whole-session trace (macro-episode). Micro
        episodes preserve buried preferences/facts; macro episodes preserve
        global context. The transition model contributes predictive-surprise
        salience for each episode once prior episodes exist.
        """
        import numpy as np

        events = self.raw_log.list_session(session_id)
        embeddable = [e for e in events if e.embedding is not None]
        if not embeddable:
            return []

        made: list[int] = []

        # Micro episodes: sliding windows over adjacent events. Window=2 keeps
        # user/assistant exchanges compact; singleton fallback handles 1-turn sessions.
        window = 2 if len(embeddable) >= 2 else 1
        for start in range(0, len(embeddable) - window + 1):
            chunk = embeddable[start : start + window]
            emb = self._mean_embedding([e.embedding for e in chunk if e.embedding is not None])
            if emb is None:
                continue
            text = "\n".join(self._event_text(e) for e in chunk if e.content.strip())
            salience, surprise = self._episode_salience(emb)
            if any(e.type.startswith("remember:") for e in chunk):
                salience = min(1.5, salience + 0.6)
            ep_id = self.episodic.add(
                event_id=f"micro_{session_id}_{start}",
                ts=chunk[len(chunk) // 2].ts,
                embedding=emb,
                salience=salience,
                metadata={
                    "session_id": session_id,
                    "kind": "micro",
                    "n_events": len(chunk),
                    "prediction_error": surprise,
                },
            )
            self.episode_text.put(
                episode_id=ep_id,
                content_text=text,
                event_ids=[e.id for e in chunk],
                session_id=session_id,
            )
            made.append(ep_id)

        # Macro episode: whole session trace.
        macro_emb = self._mean_embedding([e.embedding for e in embeddable if e.embedding is not None])
        if macro_emb is not None:
            macro_text = "\n".join(self._event_text(e) for e in events if e.content.strip())
            salience, surprise = self._episode_salience(macro_emb)
            salience = max(salience * 0.8, 0.05)  # macro is useful but less atomic
            if any(e.type.startswith("remember:") for e in events):
                salience = min(1.5, salience + 0.6)
            ep_id = self.episodic.add(
                event_id=f"macro_{session_id}",
                ts=embeddable[len(embeddable) // 2].ts,
                embedding=macro_emb,
                salience=salience,
                metadata={
                    "session_id": session_id,
                    "kind": "macro",
                    "n_events": len(embeddable),
                    "prediction_error": surprise,
                },
            )
            self.episode_text.put(
                episode_id=ep_id,
                content_text=macro_text,
                event_ids=[e.id for e in embeddable],
                session_id=session_id,
            )
            made.append(ep_id)

        return made

    def _event_text(self, e: Any) -> str:
        role = "User" if "user" in e.type.lower() else "Assistant"
        if e.type.startswith("remember:"):
            role = "Remember"
        return f"{role}: {e.content.strip()}"

    def _mean_embedding(self, embeddings: list[np.ndarray]) -> np.ndarray | None:
        if not embeddings:
            return None
        emb = np.stack(embeddings, axis=0).mean(axis=0).astype(np.float32)
        norm = float(np.linalg.norm(emb))
        return emb / norm if norm > 1e-12 else emb

    def _episode_salience(self, embedding: np.ndarray) -> tuple[float, float]:
        if self.episodic.count() >= 1:
            scores, ids = self.episodic.search(embedding, top_k=1)
            nn_sim = float(scores[0]) if scores.size else -1.0
            nearest_id = int(ids[0]) if ids.size and int(ids[0]) != -1 else None
        else:
            nn_sim = -1.0
            nearest_id = None
        novelty = self.salience.compute_novelty_salience(nn_similarity=nn_sim)
        surprise = 0.0
        if nearest_id is not None:
            try:
                prev = self.episodic.get(nearest_id)
                pred = self.transition_model.predict(prev.embedding.reshape(1, -1)).reshape(-1).astype(np.float32)
                pred_norm = float(np.linalg.norm(pred))
                if pred_norm > 1e-12:
                    pred = pred / pred_norm
                surprise = max(0.0, min(1.0, 1.0 - float(pred.dot(embedding))))
            except Exception:
                surprise = 0.0
        salience = max(0.01, novelty + 0.3 * surprise)
        return salience, surprise

    def _prototypes_for_episodes(self, episode_ids: list[int]) -> list[int]:
        if not episode_ids:
            # Fall back: any prototype with a recent map entry.
            conn = self.db.connect()
            rows = conn.execute(
                "SELECT DISTINCT prototype_id FROM episode_prototype_map"
            ).fetchall()
            return [int(r["prototype_id"]) for r in rows]
        ph = ",".join(["?"] * len(episode_ids))
        conn = self.db.connect()
        rows = conn.execute(
            f"SELECT DISTINCT prototype_id FROM episode_prototype_map "
            f"WHERE episode_id IN ({ph})",
            tuple(int(e) for e in episode_ids),
        ).fetchall()
        return [int(r["prototype_id"]) for r in rows]


# --------------------------------------------------------------------------
# Token-usage counter wrapper
# --------------------------------------------------------------------------


class _CountingLLM:
    """Thin wrapper around an ``LLMBackend`` that accumulates token usage
    across all ``complete_json`` calls.

    Exposed via ``SlowaveEngine._counting_llm`` so test harnesses can
    read totals per-question and report them alongside accuracy/latency.

    The wrapper is transparent: it forwards every call to the underlying
    backend and adds the per-call usage to its own running counters. The
    underlying backend's ``last_usage`` is preserved on it as well.
    """

    def __init__(self, backend) -> None:
        self._backend = backend
        self.n_calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def complete_json(self, *, prompt: str, system: str | None = None):
        result = self._backend.complete_json(prompt=prompt, system=system)
        usage = getattr(self._backend, "last_usage", None) or {}
        self.n_calls += 1
        self.total_prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.total_completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        return result

    def reset_counters(self) -> None:
        self.n_calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def snapshot(self) -> dict:
        return {
            "n_calls": int(self.n_calls),
            "prompt_tokens": int(self.total_prompt_tokens),
            "completion_tokens": int(self.total_completion_tokens),
            "total_tokens": int(
                self.total_prompt_tokens + self.total_completion_tokens
            ),
        }

    # Pass through any attribute we don't override (e.g. ``last_usage``).
    def __getattr__(self, name):
        return getattr(self._backend, name)

