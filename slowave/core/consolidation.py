"""Replay-time consolidation into first-class symbolic schemas."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

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
            raise ValueError(
                "Consolidator: latent_builder given but no geometric_judge"
            )

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

        # Build global background corpus for contrastive TF-IDF.
        # Using all existing schema content texts as the background
        # ensures IDF reflects global rarity, not intra-cluster
        # commonality. Terms appearing across many schemas get low
        # IDF (generic/stopword-like); terms unique to this cluster
        # get high IDF (truly distinctive).
        _global_corpus: list[str] = []
        try:
            _global_corpus = [
                s.content_text
                for s in self.schemas.list(limit=500)
                if s.content_text
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

            outcome, new_id = self._write_latent_schema(
                prototype_id=pid, schema=schema,
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
        )

    def _write_latent_schema(
        self, *, prototype_id: int, schema,
    ) -> tuple[str, int | None]:
        """Persist a LatentSchema. Geometric verdict against the closest
        existing schema. Mirrors `_create_and_relate_schema`."""
        from slowave.latent.schema import LatentSchema as _LS

        claim_embedding = schema.centroid
        claim_text = schema.claim
        related = self._best_related_schema(
            claim=claim_text, embedding=claim_embedding,
        )

        evidence_rows: list[tuple[int | None, int | None, str | None, float]] = []
        for eid in schema.member_episode_ids:
            evidence_rows.append((int(eid), None, None, 1.0))

        scope_id = self._scope_for_episodes(schema.member_episode_ids)
        
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
        )

        dedup_existing_id = self.schemas.last_create_reinforced_existing_id
        if dedup_existing_id is not None:
            return "reinforced", dedup_existing_id

        if related is None:
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
                related.id, new_schema_id,
            )
            return "created", new_schema_id

        old_view = _LS(
            centroid=np.asarray(related_emb, dtype=np.float32),
            facet_axes=np.zeros((0, claim_embedding.shape[0]), dtype=np.float32),
            facet_strengths=np.zeros((0,), dtype=np.float32),
            member_episode_ids=[],
            central_episode_id=0,
            central_episode_text=related.content_text or "",
            mean_ts=int(related.facets.get("mean_ts", 0)) if isinstance(related.facets, dict) else 0,
            ts_span_s=int(related.facets.get("ts_span_s", 0)) if isinstance(related.facets, dict) else 0,
            confidence=float(related.confidence),
            support_count=1,
        )
        verdict = self.geometric_judge.judge(old=old_view, new=schema)

        if verdict.verdict == "reinforces":
            self.schemas.add_relation(
                src_schema_id=new_schema_id, dst_schema_id=related.id,
                relation="reinforces", confidence=schema.confidence,
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
            self.schemas.add_relation(
                src_schema_id=new_schema_id, dst_schema_id=related.id,
                relation="refines", confidence=schema.confidence,
            )
            return "reinforced", new_schema_id
        if verdict.verdict == "contradicts":
            relation = "supersedes" if verdict.time_delta_s > 0 else "contradicts"
            old_status = "superseded" if relation == "supersedes" else "contradicted"
            # Transition the old schema out of active so belief-revision
            # silencing in _schema_priors() actually fires at recall time.
            # Without this call the relation edge exists but status stays
            # "active" and the damping factor is never applied.
            self.schemas.update_status(related.id, status=old_status, salience=0.05)
            self.schemas.add_relation(
                src_schema_id=new_schema_id, dst_schema_id=related.id,
                relation=relation, confidence=max(schema.confidence, 0.5),
            )
            return "contradicted", new_schema_id
        # unrelated
        return "created", new_schema_id

    def _record_debug(self, *, prototype_id: int, episode_ids: list[int], created_schema_ids: list[int]) -> None:
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO consolidation_debug "
            "(prototype_id, episode_ids, prompt_text, response_json, extracted_claims_json, created_schema_ids, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                int(prototype_id),
                dumps_json({"ids": [int(e) for e in episode_ids]}),
                "",
                dumps_json({}),
                dumps_json({"claims": []}),
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
        if embedding is not None:
            scored = self.schemas.search_embedding(embedding, limit=5, include_inactive=False)
            if scored and scored[0][1] >= 0.72:
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
            "now", "updated", "changed", "instead", "actually", "no longer",
            "rather than", "switched", "moved", "current", "latest",
        )
        return any(m in text for m in markers)

    def _episodes_for_prototype(self, prototype_id: int) -> list[int]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT episode_id FROM episode_prototype_map WHERE prototype_id = ? ORDER BY episode_id DESC",
            (int(prototype_id),),
        ).fetchall()
        return [int(r["episode_id"]) for r in rows]

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