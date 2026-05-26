"""Replay-time consolidation into first-class symbolic schemas."""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from slowave.latent.semantic_store import SemanticStore
from slowave.storage.sqlite_db import SQLiteDB
from slowave.symbolic.contradiction import ContradictionJudge
from slowave.symbolic.encoder import TextEncoder
from slowave.symbolic.episode_text import EpisodeText, EpisodeTextStore
from slowave.symbolic.schema_extractor import ExtractedSchema, SchemaExtractor
from slowave.symbolic.schema_store import Schema, SchemaStore, canonical_schema_text
from slowave.utils.vec import dumps_json

log = logging.getLogger(__name__)


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
        extractor: SchemaExtractor | None,
        judge: ContradictionJudge | None,
        encoder: TextEncoder | None,
        max_episodes_per_prototype: int = 8,
        # Stage 6: brain-only path. When set, the consolidator runs in
        # latent mode and never calls an LLM. ``extractor`` and ``judge``
        # may both be None in that case. ``episodic_store`` is required
        # in latent mode (we need the episode embeddings for SVD).
        latent_builder=None,
        geometric_judge=None,
        episodic_store=None,
    ):
        self.db = db
        self.semantic = semantic
        self.episode_text = episode_text
        self.schemas = schemas
        self.extractor = extractor
        self.judge = judge
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
        # Stage 6: brain-only path. Schemas are built geometrically from
        # the prototype centroid + member episode embeddings. Zero LLM
        # calls. See `_consolidate_latent` below.
        if self._latent_mode:
            return self._consolidate_latent(prototype_ids=prototype_ids)

        created = 0
        reinforced = 0
        contradicted = 0
        skipped = 0

        # Phase 1: gather per-prototype episode payloads (cheap, serial).
        payloads: list[tuple[int, list[int], list[EpisodeText]]] = []
        for pid in prototype_ids:
            supporting_episode_ids = self._episodes_for_prototype(pid)
            if not supporting_episode_ids:
                skipped += 1
                continue
            sample_ids = supporting_episode_ids[: self.max_episodes_per_prototype]
            episode_texts = self.episode_text.get_many(sample_ids)
            if not episode_texts:
                skipped += 1
                continue
            payloads.append((pid, sample_ids, episode_texts))

        # Phase 2: run schema extraction in parallel. These are independent
        # LLM calls; parallelising them is the single biggest speedup when
        # using a network-latency-bound backend (OpenRouter, etc.). For the
        # local Ollama backend the speedup is smaller (it serialises at the
        # model anyway) but never harmful. Workers default to 8 and can be
        # overridden via SLOWAVE_LLM_WORKERS.
        max_workers = int(os.environ.get("SLOWAVE_LLM_WORKERS", "8"))
        extracted_by_pid: dict[int, list[ExtractedSchema]] = {}
        debug_by_pid: dict[int, dict] = {}

        def _extract_for_pid(item):
            pid, _sample_ids, eps = item
            try:
                items = self.extractor.extract(
                    episode_texts=[ep.content_text for ep in eps]
                )
                # SchemaExtractor stores last_debug on itself which doesn't
                # survive concurrent calls; capture it explicitly here is not
                # straightforward without changing SchemaExtractor's API.
                # Per-prototype debug is best-effort under parallelism.
                return pid, items, dict(getattr(self.extractor, "last_debug", {}) or {})
            except Exception as e:
                log.warning("schema extraction failed for prototype %s: %s", pid, e)
                return pid, [], {"error": str(e)}

        if payloads and max_workers > 1:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(payloads))) as ex:
                for pid, items, dbg in ex.map(_extract_for_pid, payloads):
                    extracted_by_pid[pid] = items
                    debug_by_pid[pid] = dbg
        else:
            for item in payloads:
                pid, items, dbg = _extract_for_pid(item)
                extracted_by_pid[pid] = items
                debug_by_pid[pid] = dbg

        # Phase 3: write-back to DB. SQLite + contradiction judging stay
        # serial to keep the write path simple. Contradiction judging is
        # also one LLM call per (new, related) pair; future work could
        # parallelise judging too if a benchmark requires it.
        for pid, sample_ids, episode_texts in payloads:
            extracted_items = extracted_by_pid.get(pid, [])
            if not extracted_items:
                self._record_debug(
                    prototype_id=pid,
                    episode_ids=sample_ids,
                    created_schema_ids=[],
                )
                skipped += 1
                continue

            by_prompt_index = {i + 1: ep for i, ep in enumerate(episode_texts)}
            created_schema_ids: list[int] = []
            for extracted in extracted_items:
                outcome, schema_id = self._create_and_relate_schema(
                    prototype_id=pid,
                    extracted=extracted,
                    by_prompt_index=by_prompt_index,
                )
                if schema_id is not None:
                    created_schema_ids.append(schema_id)
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
                created_schema_ids=created_schema_ids,
            )

        return ConsolidationStats(
            prototypes_processed=len(prototype_ids),
            schemas_created=created,
            schemas_reinforced=reinforced,
            schemas_contradicted=contradicted,
            schemas_skipped=skipped,
        )

    # ------------------------------------------------------------------
    # Stage 6: brain-only consolidation path
    # ------------------------------------------------------------------

    def _consolidate_latent(self, *, prototype_ids: list[int]) -> ConsolidationStats:
        """Latent-schema consolidation. Zero LLM calls."""
        created = 0
        reinforced = 0
        contradicted = 0
        skipped = 0

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

        project = self._project_for_episodes(schema.member_episode_ids)
        new_schema_id = self.schemas.create(
            prototype_ids=[prototype_id],
            content_text=claim_text,
            facets=schema.facets,
            tags=schema.tags,
            confidence=schema.confidence,
            salience=0.5 + schema.confidence,
            embedding=claim_embedding,
            project=project,
            supporting_episode_ids=schema.member_episode_ids,
            evidence=evidence_rows,
        )

        if related is None:
            return "created", new_schema_id

        # Re-fetch the related schema's stored embedding from the DB. We
        # need it as a numpy array to compare centroids with the geometric
        # judge. Falls back to a zero vector if missing (degenerate case
        # that the judge will treat as "unrelated").
        related_emb = self._fetch_schema_embedding(related.id)
        if related_emb is None:
            related_emb = np.zeros_like(claim_embedding)

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
            return "reinforced", new_schema_id
        if verdict.verdict == "refines":
            self.schemas.add_relation(
                src_schema_id=new_schema_id, dst_schema_id=related.id,
                relation="refines", confidence=schema.confidence,
            )
            return "reinforced", new_schema_id
        if verdict.verdict == "contradicts":
            relation = "supersedes" if verdict.time_delta_s > 0 else "contradicts"
            self.schemas.add_relation(
                src_schema_id=new_schema_id, dst_schema_id=related.id,
                relation=relation, confidence=schema.confidence,
            )
            return "contradicted", new_schema_id
        # unrelated
        return "created", new_schema_id

    # ------------------------------------------------------------------
    # LLM consolidation path (Stage 0-5 default, kept for A/B comparison)
    # ------------------------------------------------------------------

    def _create_and_relate_schema(
        self,
        *,
        prototype_id: int,
        extracted: ExtractedSchema,
        by_prompt_index: dict[int, EpisodeText],
    ) -> tuple[str, int | None]:
        schema_text_for_matching = canonical_schema_text(
            claim=extracted.claim,
            facets=extracted.facets,
            tags=extracted.tags,
        )
        claim_embedding = self._embed(schema_text_for_matching)
        related = self._best_related_schema(claim=schema_text_for_matching, embedding=claim_embedding)

        evidence_episode_ids: list[int] = []
        evidence_rows: list[tuple[int | None, int | None, str | None, float]] = []
        for idx in extracted.evidence_indices:
            ep = by_prompt_index.get(idx)
            if ep is None:
                continue
            evidence_episode_ids.append(ep.episode_id)
            # Link episode evidence; raw-event drill-through is expanded at recall.
            evidence_rows.append((ep.episode_id, None, extracted.evidence_quote, 1.0))
        if not evidence_episode_ids:
            for ep in by_prompt_index.values():
                evidence_episode_ids.append(ep.episode_id)
                evidence_rows.append((ep.episode_id, None, extracted.evidence_quote, 1.0))

        project = self._project_for_episodes(evidence_episode_ids)
        new_schema_id = self.schemas.create(
            prototype_ids=[prototype_id],
            content_text=extracted.claim,
            facets=extracted.facets,
            tags=extracted.tags,
            confidence=extracted.confidence,
            salience=0.5 + extracted.confidence,
            embedding=claim_embedding,
            project=project,
            supporting_episode_ids=evidence_episode_ids,
            evidence=evidence_rows,
        )

        if related is None:
            return "created", new_schema_id

        verdict = self.judge.judge(
            existing_type=str(related.facets.get("schema_class", "schema")),
            existing_text=canonical_schema_text(
                claim=related.content_text,
                facets=related.facets,
                tags=related.tags,
            ),
            new_type=str(extracted.facets.get("schema_class", "schema")),
            new_text=schema_text_for_matching,
        )
        if verdict.verdict == "reinforces":
            self.schemas.add_relation(
                src_schema_id=new_schema_id,
                dst_schema_id=related.id,
                relation="reinforces",
                confidence=extracted.confidence,
                reason=verdict.reasoning,
            )
            self.schemas.reinforce(related.id, amount=0.2)
            return "reinforced", new_schema_id
        if verdict.verdict == "refines":
            self.schemas.add_relation(
                src_schema_id=new_schema_id,
                dst_schema_id=related.id,
                relation="refines",
                confidence=extracted.confidence,
                reason=verdict.reasoning,
            )
            self.schemas.reinforce(related.id, amount=0.1)
            return "created", new_schema_id
        if verdict.verdict == "contradicts":
            relation = "supersedes" if self._looks_like_update(extracted.claim) else "contradicts"
            self.schemas.add_relation(
                src_schema_id=new_schema_id,
                dst_schema_id=related.id,
                relation=relation,
                confidence=extracted.confidence,
                reason=verdict.reasoning,
            )
            if relation == "supersedes":
                self.schemas.update_status(related.id, status="superseded", salience=0.05)
            else:
                self.schemas.update_status(related.id, status="contradicted", needs_review=True)
                self.schemas.update_status(new_schema_id, status="needs_review", needs_review=True)
            return "contradicted", new_schema_id
        return "created", new_schema_id

    def _record_debug(self, *, prototype_id: int, episode_ids: list[int], created_schema_ids: list[int]) -> None:
        dbg = getattr(self.extractor, "last_debug", {}) or {}
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO consolidation_debug "
            "(prototype_id, episode_ids, prompt_text, response_json, extracted_claims_json, created_schema_ids, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                int(prototype_id),
                dumps_json({"ids": [int(e) for e in episode_ids]}),
                str(dbg.get("prompt_text", "")),
                dumps_json(dbg.get("response_json", {}) if isinstance(dbg.get("response_json", {}), dict) else {"raw": str(dbg.get("response_json"))}),
                dumps_json({"claims": dbg.get("extracted_claims", [])}),
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

    def _project_for_episodes(self, episode_ids: list[int]) -> str | None:
        if not episode_ids:
            return None
        ph = ",".join(["?"] * len(episode_ids))
        conn = self.db.connect()
        row = conn.execute(
            "SELECT s.project AS project FROM episode_text et "
            "JOIN sessions s ON s.id = et.session_id "
            f"WHERE et.episode_id IN ({ph}) AND s.project IS NOT NULL "
            "ORDER BY et.episode_id DESC LIMIT 1",
            tuple(int(e) for e in episode_ids),
        ).fetchone()
        return None if row is None else str(row["project"])