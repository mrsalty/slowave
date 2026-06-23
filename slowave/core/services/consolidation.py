"""ConsolidationService: replay + latent schema consolidation + decay.

Previously implemented as engine.consolidate_once(). Extracted so it can be
tested and reasoned about independently of the full engine.
"""
from __future__ import annotations

import dataclasses
import logging
import time
from typing import Any

from slowave.core.consolidation import Consolidator
from slowave.core.services.ingest import IngestService
from slowave.latent.replay_engine import ReplayEngine
from slowave.storage.sqlite_db import SQLiteDB
from slowave.symbolic.schema_store import SchemaStore

log = logging.getLogger(__name__)


class ConsolidationService:
    """Runs one replay + latent consolidation + decay pass."""

    def __init__(
        self,
        *,
        db: SQLiteDB,
        replay_engine: ReplayEngine,
        consolidator: Consolidator | None,
        schemas: SchemaStore,
        ingest: IngestService,
        procedures: Any = None,
        encoder: Any = None,
    ):
        self.db = db
        self.replay_engine = replay_engine
        self.consolidator = consolidator
        self.schemas = schemas
        self._ingest = ingest
        self.procedures = procedures
        self.encoder = encoder

    def consolidate_once(self, *, triggered_by: str = "worker") -> dict[str, Any]:
        """Run one replay + latent consolidation pass, then decay unused schemas.

        Returns a stats dict with keys ``replay``, ``consolidation``, and ``decay``.
        """
        conn = self.db.connect()
        started_ts = int(time.time())
        run_id: int | None = None
        try:
            cur = conn.execute(
                "INSERT INTO worker_runs (started_ts, triggered_by) VALUES (?, ?)",
                (started_ts, triggered_by),
            )
            conn.commit()
            run_id = cur.lastrowid
        except Exception as e:
            log.warning("worker_runs insert failed: %s", e)

        error_text: str | None = None
        result: dict[str, Any] = {}
        try:
            replay_stats = self.replay_engine.replay_once()
            consolidation: dict[str, Any] = {}
            if self.consolidator is not None:
                protos = self._ingest.prototypes_for_episodes([])
                cs = self.consolidator.consolidate(prototype_ids=protos)
                consolidation = dataclasses.asdict(cs)
            decay = self.schemas.decay_unused(idle_days=30.0, dry_run=False)
            
            # Tier 2 enrichment: extract remember events and promote procedures
            procedures_result: dict[str, Any] = {}
            if self.procedures is not None and self.encoder is not None:
                try:
                    from slowave.core.procedural_enrichment import ProceduralEnrichment
                    
                    enrichment = ProceduralEnrichment(encoder=self.encoder, db=self.db)
                    
                    # Find feedback groups that need enrichment
                    conn_local = self.db.connect()
                    feedback_rows = conn_local.execute(
                        """
                        SELECT DISTINCT f.goal, f.task_type, GROUP_CONCAT(DISTINCT r.session_id) as session_ids
                        FROM context_feedback_events f
                        LEFT JOIN context_recall_events r ON r.context_id = f.context_id
                        WHERE f.outcome = 'success'
                          AND f.feedback IN ('useful', 'partially_useful')
                          AND f.goal IS NOT NULL
                          AND r.session_id IS NOT NULL
                        GROUP BY f.goal, COALESCE(f.task_type, '')
                        """
                    ).fetchall()
                    
                    enriched_steps_map: dict[tuple[str, str], list[str]] = {}
                    for row in feedback_rows:
                        goal = str(row["goal"] or "")
                        task_type = str(row["task_type"] or "")
                        session_ids = [s.strip() for s in str(row["session_ids"] or "").split(",") if s.strip()]
                        
                        if session_ids:
                            steps = enrichment.enrich(session_ids)
                            if steps:
                                enriched_steps_map[(goal, task_type)] = steps
                    
                    # Promote procedures with enrichment
                    promote_result = self.procedures.promote_candidates_from_feedback(
                        enriched_steps_map=enriched_steps_map if enriched_steps_map else None
                    )
                    procedures_result["promotion"] = promote_result
                    
                    # Generalization: promote procedures across stages
                    gen_result = self.procedures.promote_generalization(
                        registry=self.schemas.scope_registry
                    )
                    procedures_result["generalization"] = gen_result
                except Exception as e:
                    log.warning("Procedural enrichment/generalization failed: %s", e)
                    procedures_result["error"] = str(e)
            result = {
                "replay": replay_stats,
                "consolidation": consolidation,
                "decay": decay,
                "procedures": procedures_result
            }
        except Exception as e:
            error_text = str(e)
            log.error("consolidate_once failed: %s", e, exc_info=True)
            result = {"error": error_text}
        finally:
            if run_id is not None:
                ended_ts = int(time.time())
                cs = result.get("consolidation", {})
                replay_stats = result.get("replay", {})
                decay = result.get("decay", {})
                procedures_result = result.get("procedures", {})
                try:
                    conn.execute(
                        """
                        UPDATE worker_runs SET
                          ended_ts=?, duration_ms=?, prototypes_processed=?,
                          episodes_processed=?,
                          schemas_created=?, schemas_reinforced=?,
                          schemas_contradicted=?, schemas_skipped=?,
                          procedures_promoted=?, procedures_generalized=?,
                          schemas_decayed=?, error_text=?
                        WHERE id=?
                        """,
                        (
                            ended_ts,
                            (ended_ts - started_ts) * 1000,
                            cs.get("prototypes_processed", 0),
                            replay_stats.get("replay_sampled", 0),
                            cs.get("schemas_created", 0),
                            cs.get("schemas_reinforced", 0),
                            cs.get("schemas_contradicted", 0),
                            cs.get("schemas_skipped", 0),
                            len(procedures_result.get("promotion", {}).get("created", [])),
                            len(procedures_result.get("generalization", {}).get("promoted", {})),
                            decay.get("decayed", 0),
                            error_text,
                            run_id,
                        ),
                    )
                    conn.commit()
                except Exception as e2:
                    log.warning("worker_runs update failed: %s", e2)
        return result
