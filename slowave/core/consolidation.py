"""Replay-time consolidation into first-class symbolic schemas."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

import numpy as np

from slowave.latent.semantic_store import SemanticStore
from slowave.storage.sqlite_db import SQLiteDB
from slowave.symbolic.encoder import TextEncoder
from slowave.symbolic.episode_text import EpisodeText, EpisodeTextStore
from slowave.symbolic.schema_store import Schema, SchemaStore, canonical_schema_text
from slowave.utils.vec import dumps_json

log = logging.getLogger(__name__)


def _classify_consolidated_schema(text: str, source_kind: str | None) -> str | None:
    """Classify consolidated schema by provenance and structure.

    Args:
        text: Schema content text
        source_kind: Source kind from facets (e.g., "explicit_remember", "consolidation")

    Returns:
        "episodic_summary" if consolidated multi-sentence summary, None for explicit or short,
        "fact" for other consolidated schemas.
    """
    # Explicit memories are never reclassified
    if source_kind == "explicit_remember":
        return None

    # Count sentences: more heuristic to catch multi-claim summaries
    sentence_count = len(re.findall(r"[.!?]", text))
    text_length = len(text)

    # Multi-sentence summaries (>= 3 sentences OR > 300 chars) are tagged as episodic_summary
    if sentence_count >= 3 or text_length > 300:
        return "episodic_summary"

    # Short consolidated schemas are tagged as fact
    return "fact"


@dataclass(frozen=True)
class ConsolidationStats:
    prototypes_processed: int
    schemas_created: int
    schemas_reinforced: int
    schemas_contradicted: int
    schemas_skipped: int
    # Diagnostics (plans/05-consolidation.md Phase 4). verdict_counts keys:
    # "no_candidate" (Phase 3b found nothing to compare against), "missing_embedding"
    # (related schema found but its stored embedding is unreadable), and the four
    # GeometricContradictionJudge verdicts ("unrelated", "reinforces", "refines",
    # "contradicts" — the last counts every judge call that said contradicts, even
    # if a gate below downgraded the outcome to reinforcement).
    verdict_counts: dict[str, int] = field(default_factory=dict)
    # Prototypes absorbed by the >=0.92 near-duplicate guard before the
    # geometric judge was ever reached (Phase 3a).
    near_dup_intercepts: int = 0
    # Of judge verdicts "contradicts", how many were downgraded to reinforcement
    # by each supersession gate (Phase 4 Step 4).
    gate_downgrades: dict[str, int] = field(default_factory=dict)
    # Per-prototype LatentSchemaBuilder confidence values, for calibration checks
    # against variance_floor (Q5).
    confidence_histogram: list[float] = field(default_factory=list)


class Consolidator:
    """Lift replayed latent prototypes into symbolic semantic memory."""

    def __init__(
        self,
        *,
        db: SQLiteDB,
        semantic: SemanticStore,
        episode_text: EpisodeTextStore,
        schemas: SchemaStore,
        encoder: TextEncoder | None,
        max_episodes_per_prototype: int = 8,
        # Brain-only path. Schemas are built from prototype geometry and
        # lexical signatures. Zero LLM calls.
        latent_builder=None,
        geometric_judge=None,
        episodic_store=None,
    ):
        self.db = db
        self.semantic = semantic
        self.episode_text = episode_text
        self.schemas = schemas
        self.encoder = encoder
        self.max_episodes_per_prototype = max_episodes_per_prototype
        self.latent_builder = latent_builder
        self.geometric_judge = geometric_judge
        self._latent_mode = latent_builder is not None
        if self._latent_mode and geometric_judge is None:
            raise ValueError("Consolidator: latent_builder given but no geometric_judge")

    def consolidate(self, *, prototype_ids: list[int]) -> ConsolidationStats:
        """Consolidate prototypes into latent schemas. Zero LLM calls."""
        return self._consolidate_latent(prototype_ids=prototype_ids)

    # ------------------------------------------------------------------
    # Stage 6: brain-only consolidation path
    # ------------------------------------------------------------------

    def _consolidate_latent(self, *, prototype_ids: list[int]) -> ConsolidationStats:
        """Latent-schema consolidation. Zero LLM calls."""
        created = 0
        reinforced = 0
        contradicted = 0
        skipped = 0
        diag: dict = {
            "verdict_counts": {
                "no_candidate": 0,
                "missing_embedding": 0,
                "unrelated": 0,
                "reinforces": 0,
                "refines": 0,
                "contradicts": 0,
            },
            "near_dup_intercepts": 0,
            "gate_downgrades": {"support_gate": 0, "recency_gate": 0},
            "confidence_histogram": [],
        }

        # Build global background corpus for contrastive TF-IDF.
        # Using all existing schema content texts as the background
        # ensures IDF reflects global rarity, not intra-cluster
        # commonality. Terms appearing across many schemas get low
        # IDF (generic/stopword-like); terms unique to this cluster
        # get high IDF (truly distinctive).
        _global_corpus: list[str] = []
        try:
            _global_corpus = [
                s.content_text for s in self.schemas.list(limit=500) if s.content_text
            ]
        except Exception:
            pass

        for pid in prototype_ids:
            ep_ids = self._episodes_for_prototype(pid)
            if not ep_ids:
                skipped += 1
                continue
            sample_ids = ep_ids[: self.max_episodes_per_prototype]
            ep_texts = self.episode_text.get_many(sample_ids)
            if not ep_texts:
                skipped += 1
                continue

            # Episodes backed exclusively by explicit remember events never
            # re-consolidate into schemas: remember() already created the
            # first-class schema synchronously, so lifting these episodes only
            # produces composite near-duplicates (adjacent remembers merged
            # into one macro-episode concatenate two unrelated claims, which
            # defeats both text dedupe and the geometric near-dup guard).
            # Still link related schemas via the prototype centroid so the
            # schema graph is populated even in pure-remember sessions.
            if self._episodes_all_explicit_remember(sample_ids):
                try:
                    proto = self.semantic.get(pid)
                    self._link_schemas_via_prototype_centroid(pid, proto.centroid)
                except Exception:
                    pass
                skipped += 1
                continue

            # Fetch the prototype's centroid (already maintained by replay).
            try:
                proto = self.semantic.get(pid)
            except KeyError:
                skipped += 1
                continue
            centroid = proto.centroid

            # Fetch member-episode embeddings + timestamps.
            ep_records = []
            store = getattr(self, "_episodic_store_ref", None)
            if store is not None:
                ep_records = store.get_many([e.episode_id for e in ep_texts])
            by_eid = {r.id: r for r in ep_records}
            embs, ts_list, kept_eps, kept_ids = [], [], [], []
            for ep in ep_texts:
                rec = by_eid.get(ep.episode_id)
                if rec is None or rec.embedding is None:
                    continue
                embs.append(rec.embedding)
                ts_list.append(int(rec.ts))
                kept_eps.append(ep)
                kept_ids.append(int(ep.episode_id))
            if not embs:
                skipped += 1
                continue

            member_embeddings = np.asarray(embs, dtype=np.float32)
            schema = self.latent_builder.build(
                centroid=centroid,
                member_embeddings=member_embeddings,
                member_episodes=kept_eps,
                member_episode_ids=kept_ids,
                member_timestamps=ts_list,
                background_corpus_texts=_global_corpus,
            )
            if schema is None:
                skipped += 1
                continue
            diag["confidence_histogram"].append(float(schema.confidence))

            outcome, new_id = self._write_latent_schema(
                prototype_id=pid,
                schema=schema,
                diag=diag,
            )
            if outcome == "created":
                created += 1
            elif outcome == "reinforced":
                reinforced += 1
            elif outcome == "contradicted":
                contradicted += 1
            else:
                skipped += 1

            self._record_debug(
                prototype_id=pid,
                episode_ids=sample_ids,
                created_schema_ids=[new_id] if new_id is not None else [],
            )

        return ConsolidationStats(
            prototypes_processed=len(prototype_ids),
            schemas_created=created,
            schemas_reinforced=reinforced,
            schemas_contradicted=contradicted,
            schemas_skipped=skipped,
            verdict_counts=diag["verdict_counts"],
            near_dup_intercepts=diag["near_dup_intercepts"],
            gate_downgrades=diag["gate_downgrades"],
            confidence_histogram=diag["confidence_histogram"],
        )

    def _write_latent_schema(
        self,
        *,
        prototype_id: int,
        schema,
        diag: dict | None = None,
    ) -> tuple[str, int | None]:
        """Persist a LatentSchema. Geometric verdict against the closest
        existing schema. Mirrors `_create_and_relate_schema`."""
        from slowave.latent.schema import LatentSchema as _LS

        claim_embedding = schema.centroid
        claim_text = schema.claim

        evidence_rows: list[tuple[int | None, int | None, str | None, float]] = []
        for eid in schema.member_episode_ids:
            evidence_rows.append((int(eid), None, None, 1.0))

        scope_id = self._scope_for_episodes(schema.member_episode_ids)

        # Near-duplicate guard: if an existing active schema is geometrically
        # almost identical (>= near_dup_guard_cosine, same threshold as
        # working-memory MMR dedup by default), strengthen it instead of
        # creating another copy. Without this, every consolidation pass
        # re-encoded each explicit remember into a duplicate summary schema.
        near_dup_cosine = getattr(self.geometric_judge.cfg, "near_dup_guard_cosine", 0.92)
        if claim_embedding is not None:
            near = self.schemas.search_embedding(claim_embedding, limit=1)
            if near and near[0][1] >= near_dup_cosine:
                try:
                    existing = self.schemas.get(near[0][0])
                except KeyError:
                    existing = None
                if existing is not None and existing.status == "active":
                    self.schemas.reinforce_schema(
                        existing.id,
                        prototype_ids=[prototype_id],
                        supporting_episode_ids=schema.member_episode_ids,
                        evidence=evidence_rows,
                        confidence=schema.confidence,
                    )
                    if scope_id and existing.scope_id and scope_id != existing.scope_id:
                        try:
                            self.schemas.increment_cross_scope_reinforcement(existing.id)
                        except Exception:
                            pass
                    if diag is not None:
                        diag["near_dup_intercepts"] += 1
                    return "reinforced", existing.id

        related = self._best_related_schema(
            claim=claim_text,
            embedding=claim_embedding,
        )

        # Classify consolidated schema by provenance and structure;
        # tag schema_class so the eligibility gate can filter broad summaries.
        facets = dict(schema.facets) if schema.facets else {}
        source_kind = facets.get("source_kind") or "consolidation"
        schema_class = _classify_consolidated_schema(claim_text, source_kind)
        if schema_class is not None:
            facets["schema_class"] = schema_class

        new_schema_id = self.schemas.create(
            prototype_ids=[prototype_id],
            content_text=claim_text,
            facets=facets,
            tags=schema.tags,
            confidence=schema.confidence,
            salience=0.5 + schema.confidence,
            embedding=claim_embedding,
            scope_id=scope_id,
            supporting_episode_ids=schema.member_episode_ids,
            evidence=evidence_rows,
            facet_axes=schema.facet_axes,
            facet_strengths=schema.facet_strengths,
        )

        dedup_existing_id = self.schemas.last_create_reinforced_existing_id
        if dedup_existing_id is not None:
            return "reinforced", dedup_existing_id

        if related is None:
            if diag is not None:
                diag["verdict_counts"]["no_candidate"] += 1
            return "created", new_schema_id

        # Re-fetch the related schema's stored embedding from the DB. We
        # need it as a numpy array to compare centroids with the geometric
        # judge. A missing embedding is not evidence for contradiction or
        # supersession — fall back to creation without a geometric verdict.
        related_emb = self._fetch_schema_embedding(related.id)
        if related_emb is None:
            log.warning(
                "consolidation: schema %d has no stored embedding; "
                "skipping geometric verdict, creating new schema %d",
                related.id,
                new_schema_id,
            )
            if diag is not None:
                diag["verdict_counts"]["missing_embedding"] += 1
            return "created", new_schema_id

        # Real facet axes/strengths for the old schema, unpacked by
        # SchemaStore._row_to_schema from the persisted blobs (see
        # schema.sql). Falls back to an empty placeholder only when the
        # related schema genuinely has none (legacy row created before
        # this persistence was added, or it had too few members) — this
        # used to be an unconditional placeholder regardless of the old
        # schema's real facet data, which made "contradicts" provably
        # unreachable (fixed 2026-07-09, see PROGRESS.md and
        # tests/unit/test_contradicts_verdict_unreachable.py).
        related_facet_axes = related.facet_axes
        if not isinstance(related_facet_axes, np.ndarray) or related_facet_axes.ndim != 2:
            related_facet_axes = np.zeros((0, claim_embedding.shape[0]), dtype=np.float32)
        related_facet_strengths = related.facet_strengths
        if not isinstance(related_facet_strengths, np.ndarray) or related_facet_strengths.ndim != 1:
            related_facet_strengths = np.zeros((0,), dtype=np.float32)

        old_view = _LS(
            centroid=np.asarray(related_emb, dtype=np.float32),
            facet_axes=related_facet_axes,
            facet_strengths=related_facet_strengths,
            member_episode_ids=[],
            central_episode_id=0,
            central_episode_text=related.content_text or "",
            mean_ts=(
                int(related.facets.get("mean_ts", 0)) if isinstance(related.facets, dict) else 0
            ),
            ts_span_s=(
                int(related.facets.get("ts_span_s", 0)) if isinstance(related.facets, dict) else 0
            ),
            confidence=float(related.confidence),
            support_count=1,
        )
        verdict = self.geometric_judge.judge(old=old_view, new=schema)

        if verdict.verdict == "reinforces":
            if diag is not None:
                diag["verdict_counts"]["reinforces"] += 1
            self.schemas.add_relation(
                src_schema_id=new_schema_id,
                dst_schema_id=related.id,
                relation="reinforces",
                confidence=schema.confidence,
            )
            # Cross-scope offline reinforcement: when consolidation finds that a
            # newly-formed schema reinforces an existing schema from a different
            # scope, record it as a distinct signal (not as fabricated recall).
            # This breaks the bootstrap deadlock where stage-0 schemas can never
            # accumulate cross-scope evidence without already being promoted.
            if scope_id and related.scope_id and scope_id != related.scope_id:
                try:
                    self.schemas.increment_cross_scope_reinforcement(related.id)
                except Exception:
                    pass
            return "reinforced", new_schema_id
        if verdict.verdict == "refines":
            if diag is not None:
                diag["verdict_counts"]["refines"] += 1
            self.schemas.add_relation(
                src_schema_id=new_schema_id,
                dst_schema_id=related.id,
                relation="refines",
                confidence=schema.confidence,
            )
            return "reinforced", new_schema_id
        if verdict.verdict == "contradicts":
            if diag is not None:
                diag["verdict_counts"]["contradicts"] += 1
            # Gate: only supersede when the new schema has enough support
            # AND sufficient temporal distance from the old one.
            # A single episode or a near-simultaneous contradiction
            # should not bury a well-established schema.
            min_support = getattr(self.geometric_judge.cfg, "min_support_to_supersede", 2)
            if schema.support_count < min_support:
                if diag is not None:
                    diag["gate_downgrades"]["support_gate"] += 1
                return "reinforced", new_schema_id

            min_dt = getattr(self.geometric_judge.cfg, "min_time_delta_to_supersede_s", 3600.0)
            if 0 < verdict.time_delta_s < min_dt:
                if diag is not None:
                    diag["gate_downgrades"]["recency_gate"] += 1
                return "reinforced", new_schema_id

            relation = "supersedes" if verdict.time_delta_s > 0 else "contradicts"
            old_status = "superseded" if relation == "supersedes" else "contradicted"
            # Transition the old schema out of active so belief-revision
            # silencing in _schema_priors() actually fires at recall time.
            # Without this call the relation edge exists but status stays
            # "active" and the damping factor is never applied.
            self.schemas.update_status(related.id, status=old_status, salience=0.05)
            self.schemas.add_relation(
                src_schema_id=new_schema_id,
                dst_schema_id=related.id,
                relation=relation,
                confidence=max(schema.confidence, 0.5),
            )
            return "contradicted", new_schema_id
        # unrelated
        if diag is not None:
            diag["verdict_counts"]["unrelated"] += 1
        return "created", new_schema_id

    def _record_debug(
        self, *, prototype_id: int, episode_ids: list[int], created_schema_ids: list[int]
    ) -> None:
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO consolidation_debug "
            "(prototype_id, episode_ids, created_schema_ids, ts) "
            "VALUES (?, ?, ?, ?)",
            (
                int(prototype_id),
                dumps_json({"ids": [int(e) for e in episode_ids]}),
                dumps_json({"ids": [int(s) for s in created_schema_ids]}),
                int(time.time()),
            ),
        )
        conn.commit()

    def _embed(self, text: str) -> np.ndarray | None:
        if self.encoder is None:
            return None
        try:
            return self.encoder.encode(text)
        except Exception as e:
            log.warning("schema claim embedding failed: %s", e)
            return None

    def _fetch_schema_embedding(self, schema_id: int) -> np.ndarray | None:
        """Read a schema's stored embedding directly from the DB. Used by
        the latent path's geometric judge."""
        from slowave.utils.vec import unpack_f32

        conn = self.db.connect()
        row = conn.execute(
            "SELECT embedding, dim FROM schemas WHERE id = ?", (int(schema_id),)
        ).fetchone()
        if row is None or row["embedding"] is None:
            return None
        return unpack_f32(row["embedding"], int(row["dim"]))

    def _best_related_schema(self, *, claim: str, embedding: np.ndarray | None) -> Schema | None:
        related_cosine = getattr(self.geometric_judge.cfg, "related_schema_cosine", 0.72)
        if embedding is not None:
            scored = self.schemas.search_embedding(embedding, limit=5, include_inactive=False)
            if scored and scored[0][1] >= related_cosine:
                try:
                    return self.schemas.get(scored[0][0])
                except KeyError:
                    pass
        for sid in self.schemas.search_fts(claim, limit=3):
            try:
                return self.schemas.get(sid)
            except KeyError:
                continue
        return None

    def _looks_like_update(self, claim: str) -> bool:
        text = claim.lower()
        markers = (
            "now",
            "updated",
            "changed",
            "instead",
            "actually",
            "no longer",
            "rather than",
            "switched",
            "moved",
            "current",
            "latest",
        )
        return any(m in text for m in markers)

    def _episodes_for_prototype(self, prototype_id: int) -> list[int]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT episode_id FROM episode_prototype_map WHERE prototype_id = ? ORDER BY episode_id DESC",
            (int(prototype_id),),
        ).fetchall()
        return [int(r["episode_id"]) for r in rows]

    def _episodes_all_explicit_remember(self, episode_ids: list[int]) -> bool:
        """True when every raw event behind these episodes is a remember event."""
        event_ids: list[int] = []
        for ep in self.episode_text.get_many(episode_ids):
            event_ids.extend(int(e) for e in (ep.event_ids or []))
        if not event_ids:
            return False
        ph = ",".join(["?"] * len(event_ids))
        conn = self.db.connect()
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM raw_events WHERE id IN ({ph}) "
            "AND type NOT LIKE 'remember:%'",
            tuple(event_ids),
        ).fetchone()
        return int(row["n"] or 0) == 0

    def _link_schemas_via_prototype_centroid(self, prototype_id: int, centroid: np.ndarray) -> None:
        """Link the two schemas closest to this prototype's centroid with a
        reinforces relation.

        Called when all episodes are explicit-remember so no new schema should
        be created, but the prototype cluster still signals that the two nearest
        schemas are semantically related. Populates schema_relations without
        touching schema counts.
        """
        top = self.schemas.search_embedding(centroid, limit=3)
        if len(top) < 2:
            return
        s1_id, s1_cos = top[0]
        s2_id, s2_cos = top[1]
        if s1_cos < 0.65 or s2_cos < 0.60:
            return
        try:
            s1 = self.schemas.get(s1_id)
            s2 = self.schemas.get(s2_id)
        except KeyError:
            return
        if s1.status not in ("active", "needs_review"):
            return
        if s2.status not in ("active", "needs_review"):
            return
        self.schemas.add_relation(
            src_schema_id=s1_id,
            dst_schema_id=s2_id,
            relation="reinforces",
            confidence=round(s2_cos, 3),
            reason=f"co-clustered via prototype {prototype_id}",
        )

    def _scope_for_episodes(self, episode_ids: list[int]) -> str | None:
        if not episode_ids:
            return None
        ph = ",".join(["?"] * len(episode_ids))
        conn = self.db.connect()
        row = conn.execute(
            "SELECT s.scope_id AS scope_id FROM episode_text et "
            "JOIN sessions s ON s.id = et.session_id "
            f"WHERE et.episode_id IN ({ph}) AND s.scope_id IS NOT NULL "
            "ORDER BY et.episode_id DESC LIMIT 1",
            tuple(int(e) for e in episode_ids),
        ).fetchone()
        return None if row is None else str(row["scope_id"])
