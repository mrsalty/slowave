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
        encoder: Any = None,
    ):
        self.db = db
        self.replay_engine = replay_engine
        self.consolidator = consolidator
        self.schemas = schemas
        self._ingest = ingest

    def consolidate_once(
        self, *, triggered_by: str = "worker", decay_idle_days: float = 30.0
    ) -> dict[str, Any]:
        """Run one replay + latent consolidation pass, reconsolidate labile
        schemas, then decay unused schemas.

        Returns a stats dict with keys ``replay``, ``consolidation``,
        ``reconsolidation``, and ``decay``.
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
            reconsolidation: dict[str, Any] = {}
            if self.consolidator is not None:
                # Consolidate only the prototypes this replay pass actually
                # touched (new/updated episode assignments), not every
                # prototype in the store — reprocessing untouched prototypes
                # every tick re-triggers their near-duplicate "reinforces"
                # verdict against an unchanged schema, inflating salience
                # indefinitely with no new evidence behind it.
                protos = replay_stats.get("touched_prototype_ids", [])
                cs = self.consolidator.consolidate(prototype_ids=protos)
                consolidation = dataclasses.asdict(cs)
                # Reconsolidation (2026-07-10): re-examine labile schemas
                # (needs_review=True) by replaying them against their
                # nearest active neighbor via the same judge, instead of
                # leaving them flagged indefinitely. "Labile" is the state,
                # "reconsolidation" is the process that resolves it — see
                # core/08-feedback.md's "Labile State & Reconsolidation"
                # section and outcomes/08-feedback.md.
                reconsolidation = self.consolidator.reconsolidate_labile_schemas()
            # Backfill facet axes for schemas that have accumulated enough
            # supporting episodes but lack them (engine.remember() creates
            # schemas from single episodes so axes can only be computed
            # retroactively once 3+ supporting IDs exist).
            facet_backfill = self.schemas.backfill_facet_axes(limit=200)
            # part_of edges depend on facet axes existing (subspace containment
            # needs both sides' axes), so this must run after facet_backfill.
            # Only the schemas that just gained facet axes this cycle can
            # possibly produce a *new* part_of edge (an unchanged pool already
            # had its chance against itself in a prior cycle), so restrict_ids
            # keeps this an O(new_ids * N) incremental pass instead of a full
            # O(N^2) sweep every cycle; skip the call entirely when nothing
            # changed rather than paying even the query/matrix-build cost.
            if facet_backfill.get("backfilled", 0) > 0:
                part_of_backfill = self.schemas.backfill_part_of_edges(
                    restrict_ids=facet_backfill["backfilled_ids"]
                )
            else:
                part_of_backfill = {"compared": 0, "created": 0, "skipped_no_facets": 0}
            decay = self.schemas.decay_unused(idle_days=decay_idle_days, dry_run=False)

            result = {
                "replay": replay_stats,
                "consolidation": consolidation,
                "reconsolidation": reconsolidation,
                "facet_backfill": facet_backfill,
                "part_of_backfill": part_of_backfill,
                "decay": decay,
                "procedures": {},  # removed Phase 1 P1
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

                try:
                    conn.execute(
                        """
                        UPDATE worker_runs SET
                          ended_ts=?, duration_ms=?, prototypes_processed=?,
                          episodes_processed=?,
                          schemas_created=?, schemas_reinforced=?,
                          schemas_contradicted=?, schemas_skipped=?,

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
                            decay.get("decayed", 0),
                            error_text,
                            run_id,
                        ),
                    )
                    conn.commit()
                except Exception as e2:
                    log.warning("worker_runs update failed: %s", e2)

                # Graph health snapshot — best-effort, non-fatal
                try:
                    from slowave.core.graph_health import snapshot

                    snapshot(conn, run_id)
                except Exception as e3:
                    log.debug("graph_health snapshot skipped: %s", e3)
        return result
