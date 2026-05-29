"""Schema store: first-class symbolic semantic memories.

A schema is a durable typed claim consolidated from episodic traces. Unlike the
old one-schema-per-prototype model, schemas now have their own identity,
embedding, salience/status, normalized evidence links, prototype associations,
and relations to other schemas.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from slowave.storage.sqlite_db import SQLiteDB
from slowave.utils.vec import dumps_json, loads_json, pack_f32, unpack_f32


VALID_STATUS = ("active", "needs_review", "superseded", "contradicted", "archived")
VALID_RELATIONS = ("reinforces", "refines", "contradicts", "supersedes", "related_to", "part_of")
DEDUP_ACTIVE_STATUSES = ("active", "needs_review")


def normalize_schema_text(text: str) -> str:
    """Normalize schema claims for deterministic duplicate detection.

    This is deliberately conservative: it collapses whitespace and case, but
    does not strip semantic words or perform project-specific filtering. More
    aggressive semantic merging is handled by embeddings/relations elsewhere;
    this function exists to stop exact duplicate claims from multiplying during
    repeated consolidation passes.
    """
    return re.sub(r"\s+", " ", str(text).strip().lower())


@dataclass(frozen=True)
class Schema:
    id: int
    prototype_id: int | None
    content_text: str
    facets: dict[str, Any]
    tags: list[str]
    project: str | None
    status: str
    confidence: float
    salience: float
    supporting_episode_ids: list[int]
    contradicting_episode_ids: list[int]
    needs_review: bool
    first_formed_ts: int
    last_updated_ts: int


@dataclass(frozen=True)
class SchemaEvidence:
    schema_id: int
    episode_id: int | None
    raw_event_id: int | None
    quote: str | None
    weight: float


def canonical_schema_text(
    *,
    claim: str,
    facets: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> str:
    """Return the semantic text representation used for schema similarity.

    The user-visible claim remains concise, but recall/relation matching should
    see the full flexible schema: scope, positive/negative affordances, salient
    entities, attributes, and tags. This is benchmark-agnostic: any schema with
    useful facets becomes easier to retrieve by its meaning rather than only by
    the wording of its claim.
    """
    facets = facets or {}
    tags = tags or []
    parts = [f"Claim: {claim.strip()}"]

    def add_value(label: str, value: Any) -> None:
        if value is None or value == "" or value == [] or value == {}:
            return
        if isinstance(value, list):
            text = ", ".join(str(v) for v in value if str(v).strip())
        elif isinstance(value, dict):
            text = dumps_json(value)
        else:
            text = str(value)
        if text.strip():
            parts.append(f"{label}: {text.strip()}")

    add_value("Class", facets.get("schema_class"))
    add_value("Scope", facets.get("scope"))
    add_value("Polarity", facets.get("polarity"))
    add_value("Stability", facets.get("stability"))
    add_value("Positive", facets.get("positive"))
    add_value("Negative", facets.get("negative"))
    add_value("Entities", facets.get("entities"))
    add_value("Attributes", facets.get("attributes"))
    add_value("Tags", tags)
    return "\n".join(parts)


class SchemaStore:
    def __init__(self, db: SQLiteDB, *, dim: int):
        self.db = db
        self.dim = int(dim)
        self.last_create_reinforced_existing_id: int | None = None

    def create(
        self,
        *,
        content_text: str,
        facets: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        embedding: np.ndarray | None,
        prototype_ids: list[int] | None = None,
        project: str | None = None,
        status: str = "active",
        confidence: float = 1.0,
        salience: float = 1.0,
        supporting_episode_ids: list[int] | None = None,
        contradicting_episode_ids: list[int] | None = None,
        needs_review: bool = False,
        evidence: list[tuple[int | None, int | None, str | None, float]] | None = None,
        dedupe: bool = True,
    ) -> int:
        self.last_create_reinforced_existing_id = None
        status = status if status in VALID_STATUS else "active"
        now = int(time.time())
        supporting = [int(x) for x in (supporting_episode_ids or [])]
        contradicting = [int(x) for x in (contradicting_episode_ids or [])]
        proto_ids = list(dict.fromkeys(int(p) for p in (prototype_ids or [])))
        primary_proto = proto_ids[0] if proto_ids else None

        if dedupe and status in DEDUP_ACTIVE_STATUSES:
            existing_id = self.find_duplicate(
                content_text=content_text,
                project=project,
                statuses=DEDUP_ACTIVE_STATUSES,
            )
            if existing_id is not None:
                self.reinforce_schema(
                    existing_id,
                    prototype_ids=proto_ids,
                    supporting_episode_ids=supporting,
                    contradicting_episode_ids=contradicting,
                    evidence=evidence,
                    salience_delta=max(0.05, min(float(salience) * 0.25, 0.5)),
                    confidence=confidence,
                    facets=facets,
                    tags=tags,
                )
                self.last_create_reinforced_existing_id = existing_id
                return existing_id

        emb_blob = None
        emb_dim = None
        if embedding is not None:
            vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
            if vec.size != self.dim:
                raise ValueError(f"schema embedding dim mismatch: expected {self.dim}, got {vec.size}")
            emb_blob = pack_f32(vec)
            emb_dim = self.dim

        conn = self.db.connect()
        cur = conn.execute(
            """
            INSERT INTO schemas (
              prototype_id, content_text, facets_json, tags_json, project, status, confidence,
              salience, embedding, dim, supporting_episode_ids,
              contradicting_episode_ids, needs_review, first_formed_ts,
              last_updated_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                primary_proto, content_text, dumps_json(facets or {}),
                dumps_json({"tags": [str(t) for t in (tags or [])]}),
                project, status, float(confidence),
                float(salience), emb_blob, emb_dim, dumps_json({"ids": supporting}),
                dumps_json({"ids": contradicting}), 1 if needs_review else 0, now, now,
            ),
        )
        sid = int(cur.lastrowid)
        conn.execute("INSERT INTO schemas_fts (rowid, content_text) VALUES (?, ?)", (sid, content_text))
        for pid in proto_ids:
            conn.execute(
                "INSERT INTO schema_prototype_map (schema_id, prototype_id, weight) VALUES (?, ?, ?) "
                "ON CONFLICT(schema_id, prototype_id) DO UPDATE SET weight=excluded.weight",
                (sid, pid, 1.0),
            )
        for episode_id, raw_event_id, quote, weight in evidence or []:
            conn.execute(
                "INSERT OR REPLACE INTO schema_evidence "
                "(schema_id, episode_id, raw_event_id, quote, weight) VALUES (?, ?, ?, ?, ?)",
                (sid, episode_id, raw_event_id, quote, float(weight)),
            )
        conn.commit()
        return sid

    def find_duplicate(
        self,
        *,
        content_text: str,
        project: str | None,
        statuses: Iterable[str] = DEDUP_ACTIVE_STATUSES,
        exclude_id: int | None = None,
    ) -> int | None:
        """Return the strongest existing schema with identical normalized text.

        Duplicate identity is project-aware, not project-specific: schemas are
        merged within the same project namespace (including ``NULL``), but no
        project names are special-cased.
        """
        wanted = normalize_schema_text(content_text)
        if not wanted:
            return None
        valid_statuses = [s for s in statuses if s in VALID_STATUS]
        if not valid_statuses:
            return None
        ph = ",".join(["?"] * len(valid_statuses))
        sql = (
            "SELECT id, content_text FROM schemas "
            f"WHERE status IN ({ph}) "
        )
        args: list[Any] = list(valid_statuses)
        if project is None:
            sql += "AND project IS NULL "
        else:
            sql += "AND project = ? "
            args.append(project)
        if exclude_id is not None:
            sql += "AND id != ? "
            args.append(int(exclude_id))
        sql += "ORDER BY salience DESC, last_updated_ts DESC, id ASC"
        conn = self.db.connect()
        for row in conn.execute(sql, tuple(args)).fetchall():
            if normalize_schema_text(row["content_text"]) == wanted:
                return int(row["id"])
        return None

    def reinforce_schema(
        self,
        schema_id: int,
        *,
        prototype_ids: list[int] | None = None,
        supporting_episode_ids: list[int] | None = None,
        contradicting_episode_ids: list[int] | None = None,
        evidence: list[tuple[int | None, int | None, str | None, float]] | None = None,
        salience_delta: float = 0.2,
        confidence: float | None = None,
        facets: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Reinforce an existing schema with new provenance.

        This is the consolidation analogue of biological strengthening: repeat
        evidence should increase salience/support on the same semantic memory,
        not create another active copy of the same claim.
        """
        conn = self.db.connect()
        row = conn.execute(
            "SELECT supporting_episode_ids, contradicting_episode_ids, salience, "
            "confidence, facets_json, tags_json FROM schemas WHERE id = ?",
            (int(schema_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"No schema id={schema_id}")

        def merge_ids(current_json: str, extra: list[int] | None) -> list[int]:
            payload = loads_json(current_json)
            current = payload.get("ids", []) if isinstance(payload, dict) else []
            merged = list(dict.fromkeys([int(x) for x in current] + [int(x) for x in (extra or [])]))
            return merged

        supporting = merge_ids(row["supporting_episode_ids"], supporting_episode_ids)
        contradicting = merge_ids(row["contradicting_episode_ids"], contradicting_episode_ids)
        merged_confidence = max(float(row["confidence"]), float(confidence or 0.0))

        # Keep existing facets/tags stable, only filling missing keys/tags from
        # the incoming observation. This avoids oscillating canonical memories.
        merged_facets = loads_json(row["facets_json"])
        if isinstance(facets, dict):
            for key, value in facets.items():
                if key not in merged_facets or merged_facets[key] in (None, "", [], {}):
                    merged_facets[key] = value
        existing_tags = [str(t) for t in loads_json(row["tags_json"]).get("tags", [])]
        merged_tags = list(dict.fromkeys(existing_tags + [str(t) for t in (tags or [])]))

        conn.execute(
            """
            UPDATE schemas
            SET salience = salience + ?,
                confidence = ?,
                supporting_episode_ids = ?,
                contradicting_episode_ids = ?,
                facets_json = ?,
                tags_json = ?,
                last_updated_ts = ?
            WHERE id = ?
            """,
            (
                float(salience_delta), merged_confidence,
                dumps_json({"ids": supporting}), dumps_json({"ids": contradicting}),
                dumps_json(merged_facets), dumps_json({"tags": merged_tags}),
                int(time.time()), int(schema_id),
            ),
        )
        for pid in list(dict.fromkeys(int(p) for p in (prototype_ids or []))):
            conn.execute(
                "INSERT INTO schema_prototype_map (schema_id, prototype_id, weight) VALUES (?, ?, ?) "
                "ON CONFLICT(schema_id, prototype_id) DO UPDATE SET weight=max(weight, excluded.weight)",
                (int(schema_id), pid, 1.0),
            )
        for episode_id, raw_event_id, quote, weight in evidence or []:
            conn.execute(
                "INSERT OR REPLACE INTO schema_evidence "
                "(schema_id, episode_id, raw_event_id, quote, weight) VALUES (?, ?, ?, ?, ?)",
                (int(schema_id), episode_id, raw_event_id, quote, float(weight)),
            )
        conn.commit()
        self._update_utility_scores(schema_id, recall_hit=False)

    def update_status(
        self,
        schema_id: int,
        *,
        status: str,
        needs_review: bool | None = None,
        salience: float | None = None,
    ) -> None:
        status = status if status in VALID_STATUS else "active"
        sets = ["status = ?", "last_updated_ts = ?"]
        args: list[Any] = [status, int(time.time())]
        if needs_review is not None:
            sets.append("needs_review = ?")
            args.append(1 if needs_review else 0)
        if salience is not None:
            sets.append("salience = ?")
            args.append(float(salience))
        args.append(int(schema_id))
        conn = self.db.connect()
        conn.execute(f"UPDATE schemas SET {', '.join(sets)} WHERE id = ?", tuple(args))
        conn.commit()

    def add_relation(
        self,
        *,
        src_schema_id: int,
        dst_schema_id: int,
        relation: str,
        confidence: float = 1.0,
        reason: str | None = None,
    ) -> None:
        relation = relation if relation in VALID_RELATIONS else "related_to"
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO schema_relations "
            "(src_schema_id, dst_schema_id, relation, confidence, reason, created_ts) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(src_schema_id, dst_schema_id, relation) DO UPDATE SET "
            "confidence=excluded.confidence, reason=excluded.reason, created_ts=excluded.created_ts",
            (int(src_schema_id), int(dst_schema_id), relation, float(confidence), reason, int(time.time())),
        )
        conn.commit()

    def reinforce(self, schema_id: int, *, amount: float = 0.2) -> None:
        conn = self.db.connect()
        conn.execute(
            "UPDATE schemas SET salience = salience + ?, last_updated_ts = ? WHERE id = ?",
            (float(amount), int(time.time()), int(schema_id)),
        )
        conn.commit()
        self._update_utility_scores(schema_id, recall_hit=True)

    def _update_utility_scores(self, schema_id: int, *, recall_hit: bool = False) -> None:
        """Recompute and persist stability_score, recurrence_score, schema_utility.

        Called after every reinforce() and reinforce_schema() so the composite
        signal stays fresh without a separate background job.

        stability_score  = sigmoid-like score based on schema age (days since
                           first_formed_ts) and support count. Old, well-supported
                           schemas score near 1.0; brand-new schemas start near 0.

        recurrence_count = cumulative recall/reinforce hits (bumped each call).
        recurrence_score = soft-capped normalisation: count / (count + 5).

        schema_utility   = 0.5 * stability_score + 0.5 * recurrence_score.
        """
        conn = self.db.connect()
        row = conn.execute(
            "SELECT facets_json, first_formed_ts, last_updated_ts, supporting_episode_ids "
            "FROM schemas WHERE id = ?",
            (int(schema_id),),
        ).fetchone()
        if row is None:
            return

        now = int(time.time())
        facets = loads_json(row["facets_json"])
        if not isinstance(facets, dict):
            facets = {}

        # --- stability_score ---
        age_days = max(0.0, (now - int(row["first_formed_ts"])) / 86400.0)
        supporting = loads_json(row["supporting_episode_ids"])
        support_count = len(supporting.get("ids", [])) if isinstance(supporting, dict) else 0
        # age component: saturates at ~30 days (0→0, 7d→0.5, 30d→0.88)
        age_score = 1.0 - 1.0 / (1.0 + age_days / 7.0)
        # support component: saturates at ~10 episodes
        support_score = support_count / (support_count + 10.0)
        stability_score = round(0.5 * age_score + 0.5 * support_score, 4)

        # --- recurrence_score ---
        recurrence_count = int(facets.get("recurrence_count", 0))
        if recall_hit:
            recurrence_count += 1
        recurrence_score = round(recurrence_count / (recurrence_count + 5.0), 4)

        # --- schema_utility ---
        schema_utility = round(0.5 * stability_score + 0.5 * recurrence_score, 4)

        facets["stability_score"] = stability_score
        facets["recurrence_count"] = recurrence_count
        facets["recurrence_score"] = recurrence_score
        facets["schema_utility"] = schema_utility

        conn.execute(
            "UPDATE schemas SET facets_json = ? WHERE id = ?",
            (dumps_json(facets), int(schema_id)),
        )
        conn.commit()

    def get(self, schema_id: int) -> Schema:
        conn = self.db.connect()
        row = conn.execute("SELECT * FROM schemas WHERE id = ?", (int(schema_id),)).fetchone()
        if row is None:
            raise KeyError(f"No schema id={schema_id}")
        return self._row_to_schema(row)

    def get_many(self, schema_ids: Iterable[int]) -> list[Schema]:
        ids = list(dict.fromkeys(int(i) for i in schema_ids))
        if not ids:
            return []
        ph = ",".join(["?"] * len(ids))
        conn = self.db.connect()
        rows = conn.execute(f"SELECT * FROM schemas WHERE id IN ({ph})", tuple(ids)).fetchall()
        by_id = {int(r["id"]): r for r in rows}
        return [self._row_to_schema(by_id[i]) for i in ids if i in by_id]

    def get_by_prototypes(self, prototype_ids: Iterable[int], *, include_inactive: bool = False) -> list[Schema]:
        ids = list(dict.fromkeys(int(i) for i in prototype_ids))
        if not ids:
            return []
        ph = ",".join(["?"] * len(ids))
        sql = (
            "SELECT DISTINCT s.* FROM schemas s "
            "JOIN schema_prototype_map m ON m.schema_id = s.id "
            f"WHERE m.prototype_id IN ({ph})"
        )
        args: list[Any] = list(ids)
        if not include_inactive:
            sql += " AND s.status IN ('active', 'needs_review')"
        sql += " ORDER BY s.salience DESC, s.last_updated_ts DESC"
        conn = self.db.connect()
        rows = conn.execute(sql, tuple(args)).fetchall()
        return [self._row_to_schema(r) for r in rows]

    # Backward-compatible method name for call sites; behavior is now many-per-prototype.
    def get_many_by_prototypes(self, prototype_ids: Iterable[int]) -> list[Schema]:
        return self.get_by_prototypes(prototype_ids)

    def list(
        self,
        *,
        needs_review: bool | None = None,
        project: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Schema]:
        conn = self.db.connect()
        sql = "SELECT * FROM schemas WHERE 1=1"
        args: list[Any] = []
        if needs_review is not None:
            sql += " AND needs_review = ?"
            args.append(1 if needs_review else 0)
        if project is not None:
            sql += " AND project = ?"
            args.append(project)
        if status is not None:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY salience DESC, last_updated_ts DESC LIMIT ?"
        args.append(int(limit))
        rows = conn.execute(sql, tuple(args)).fetchall()
        return [self._row_to_schema(r) for r in rows]

    def search_fts(self, query: str, limit: int = 20, *, include_inactive: bool = False) -> list[int]:
        conn = self.db.connect()
        try:
            if include_inactive:
                rows = conn.execute(
                    "SELECT rowid FROM schemas_fts WHERE schemas_fts MATCH ? ORDER BY rank LIMIT ?",
                    (query, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT rowid FROM schemas_fts "
                    "WHERE schemas_fts MATCH ? "
                    "AND rowid IN (SELECT id FROM schemas WHERE status IN ('active', 'needs_review')) "
                    "ORDER BY rank LIMIT ?",
                    (query, int(limit)),
                ).fetchall()
        except Exception:
            return []
        return [int(r["rowid"]) for r in rows]

    def search_embedding(
        self,
        query: np.ndarray,
        *,
        limit: int = 20,
        project: str | None = None,
        include_inactive: bool = False,
    ) -> list[tuple[int, float]]:
        q = np.asarray(query, dtype=np.float32).reshape(-1)
        qn = float(np.linalg.norm(q)) + 1e-12
        conn = self.db.connect()
        sql = "SELECT id, embedding, dim FROM schemas WHERE embedding IS NOT NULL"
        args: list[Any] = []
        if project is not None:
            sql += " AND project = ?"
            args.append(project)
        if not include_inactive:
            sql += " AND status IN ('active', 'needs_review')"
        rows = conn.execute(sql, tuple(args)).fetchall()
        scored: list[tuple[int, float]] = []
        for r in rows:
            try:
                v = unpack_f32(r["embedding"], int(r["dim"]))
            except Exception:
                continue
            score = float(q.dot(v) / (qn * (float(np.linalg.norm(v)) + 1e-12)))
            scored.append((int(r["id"]), score))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[: int(limit)]

    def schemas_for_episodes(
        self,
        episode_ids: Iterable[int],
        *,
        include_inactive: bool = True,
    ) -> dict[int, list[tuple[int, str, float, int]]]:
        """Reverse index: episode_id -> list of (schema_id, status, confidence, last_updated_ts).

        Used by the schemas-as-priors retrieval step: a matched-query schema
        biases retrieval *toward* its evidence episodes, and a ``superseded``
        / ``contradicted`` schema silences them. Returning status, confidence
        and recency lets the caller weight the bias and the silence with a
        belief-revision-style freshness factor.

        Episodes are looked up via both ``schema_evidence`` (normalised
        table) and the legacy ``schemas.supporting_episode_ids`` JSON
        column, since older consolidations only populated the JSON column.
        """
        eids = list({int(e) for e in episode_ids})
        if not eids:
            return {}
        ph = ",".join(["?"] * len(eids))
        out: dict[int, list[tuple[int, str, float, int]]] = {e: [] for e in eids}
        conn = self.db.connect()

        # Normalised path: schema_evidence table.
        rows = conn.execute(
            f"""
            SELECT se.episode_id, s.id, s.status, s.confidence, s.last_updated_ts
            FROM schema_evidence se
            JOIN schemas s ON s.id = se.schema_id
            WHERE se.episode_id IN ({ph})
            """,
            tuple(eids),
        ).fetchall()
        for r in rows:
            eid = int(r["episode_id"])
            status = str(r["status"])
            if not include_inactive and status not in ("active", "needs_review"):
                continue
            out.setdefault(eid, []).append((
                int(r["id"]), status, float(r["confidence"]), int(r["last_updated_ts"]),
            ))

        # Legacy JSON path: scan schemas with non-empty supporting_episode_ids.
        # Cheap enough for MVP scale (~thousands of schemas) and avoids a
        # silent recall regression for databases that pre-date schema_evidence.
        legacy_rows = conn.execute(
            "SELECT id, status, confidence, last_updated_ts, supporting_episode_ids "
            "FROM schemas WHERE supporting_episode_ids != '[]'"
        ).fetchall()
        target = set(eids)
        for r in legacy_rows:
            status = str(r["status"])
            if not include_inactive and status not in ("active", "needs_review"):
                continue
            payload = loads_json(r["supporting_episode_ids"])
            supporting = payload.get("ids", []) if isinstance(payload, dict) else []
            sid = int(r["id"])
            for eid in supporting:
                try:
                    eid_i = int(eid)
                except (TypeError, ValueError):
                    continue
                if eid_i in target:
                    entry = (sid, status, float(r["confidence"]), int(r["last_updated_ts"]))
                    # Dedupe with normalised-path entries.
                    if entry not in out.get(eid_i, []):
                        out.setdefault(eid_i, []).append(entry)
        return out

    def evidence_for_schema(self, schema_id: int, *, limit: int = 10) -> list[SchemaEvidence]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT * FROM schema_evidence WHERE schema_id = ? ORDER BY weight DESC LIMIT ?",
            (int(schema_id), int(limit)),
        ).fetchall()
        return [
            SchemaEvidence(
                schema_id=int(r["schema_id"]),
                episode_id=None if r["episode_id"] is None else int(r["episode_id"]),
                raw_event_id=None if r["raw_event_id"] is None else int(r["raw_event_id"]),
                quote=None if r["quote"] is None else str(r["quote"]),
                weight=float(r["weight"]),
            )
            for r in rows
        ]

    def dedup_exact(
        self,
        *,
        status: str = "active",
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Merge exact normalized duplicate schemas within each project.

        Generic cleanup: groups by ``(project, normalize_schema_text(content))``.
        The canonical row is the highest-salience, then oldest schema. Duplicate
        rows are marked ``archived`` and related to the canonical schema; their
        evidence/prototype links are moved onto the canonical row.
        """
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT * FROM schemas WHERE status = ? ORDER BY project, content_text, salience DESC, id ASC",
            (status,),
        ).fetchall()
        groups: dict[tuple[str | None, str], list[Any]] = {}
        for row in rows:
            norm = normalize_schema_text(row["content_text"])
            if not norm:
                continue
            project = None if row["project"] is None else str(row["project"])
            groups.setdefault((project, norm), []).append(row)

        duplicate_groups = [items for items in groups.values() if len(items) > 1]
        duplicate_rows = sum(len(items) - 1 for items in duplicate_groups)
        result: dict[str, Any] = {
            "status": status,
            "groups": len(duplicate_groups),
            "duplicate_rows": duplicate_rows,
            "canonical_rows": len(duplicate_groups),
            "dry_run": dry_run,
            "merged_rows": 0,
        }
        if dry_run or not duplicate_groups:
            return result

        now = int(time.time())
        for items in duplicate_groups:
            canonical = sorted(
                items,
                key=lambda r: (-float(r["salience"]), int(r["first_formed_ts"]), int(r["id"])),
            )[0]
            canonical_id = int(canonical["id"])
            dupes = [r for r in items if int(r["id"]) != canonical_id]
            for dupe in dupes:
                dupe_id = int(dupe["id"])
                supporting = loads_json(dupe["supporting_episode_ids"]).get("ids", [])
                contradicting = loads_json(dupe["contradicting_episode_ids"]).get("ids", [])
                proto_rows = conn.execute(
                    "SELECT prototype_id FROM schema_prototype_map WHERE schema_id = ?",
                    (dupe_id,),
                ).fetchall()
                evidence_rows = conn.execute(
                    "SELECT episode_id, raw_event_id, quote, weight FROM schema_evidence WHERE schema_id = ?",
                    (dupe_id,),
                ).fetchall()
                self.reinforce_schema(
                    canonical_id,
                    prototype_ids=[int(r["prototype_id"]) for r in proto_rows],
                    supporting_episode_ids=[int(x) for x in supporting],
                    contradicting_episode_ids=[int(x) for x in contradicting],
                    evidence=[
                        (r["episode_id"], r["raw_event_id"], r["quote"], float(r["weight"]))
                        for r in evidence_rows
                    ],
                    salience_delta=max(0.01, min(float(dupe["salience"]) * 0.1, 0.2)),
                    confidence=float(dupe["confidence"]),
                    facets=loads_json(dupe["facets_json"]),
                    tags=[str(t) for t in loads_json(dupe["tags_json"]).get("tags", [])],
                )
                conn.execute(
                    "UPDATE schemas SET status = 'archived', salience = 0.05, last_updated_ts = ? WHERE id = ?",
                    (now, dupe_id),
                )
                conn.execute(
                    "INSERT INTO schema_relations "
                    "(src_schema_id, dst_schema_id, relation, confidence, reason, created_ts) "
                    "VALUES (?, ?, 'reinforces', ?, ?, ?) "
                    "ON CONFLICT(src_schema_id, dst_schema_id, relation) DO UPDATE SET "
                    "confidence=excluded.confidence, reason=excluded.reason, created_ts=excluded.created_ts",
                    (
                        canonical_id, dupe_id, 1.0,
                        "exact normalized duplicate archived after merging into canonical schema",
                        now,
                    ),
                )
                result["merged_rows"] += 1
        conn.commit()
        return result

    def health(self) -> dict[str, Any]:
        """Return lightweight schema quality metrics."""
        conn = self.db.connect()
        total = int(conn.execute("SELECT COUNT(*) AS n FROM schemas").fetchone()["n"])
        by_status = {
            str(r["status"]): int(r["n"])
            for r in conn.execute(
                "SELECT status, COUNT(*) AS n FROM schemas GROUP BY status ORDER BY n DESC"
            ).fetchall()
        }
        rows = conn.execute(
            "SELECT project, content_text FROM schemas WHERE status = 'active'"
        ).fetchall()
        active = len(rows)
        unique_keys = {
            (None if r["project"] is None else str(r["project"]), normalize_schema_text(r["content_text"]))
            for r in rows
        }
        exact_duplicate_rows = active - len(unique_keys)
        sal = conn.execute(
            "SELECT MIN(salience) AS min_sal, AVG(salience) AS avg_sal, MAX(salience) AS max_sal "
            "FROM schemas WHERE status = 'active'"
        ).fetchone()
        return {
            "schemas_total": total,
            "schemas_by_status": by_status,
            "active_schemas": active,
            "active_unique_exact_by_project": len(unique_keys),
            "active_exact_duplicate_rows": exact_duplicate_rows,
            "active_exact_duplicate_ratio": (exact_duplicate_rows / active) if active else 0.0,
            "active_salience": {
                "min": None if sal["min_sal"] is None else float(sal["min_sal"]),
                "avg": None if sal["avg_sal"] is None else float(sal["avg_sal"]),
                "max": None if sal["max_sal"] is None else float(sal["max_sal"]),
            },
        }

    def decay_unused(
        self,
        *,
        idle_days: float = 30.0,
        decay_amount: float = 0.15,
        review_threshold: float = 0.30,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Decay salience of active schemas that have never been recalled.

        Brain analogue: memories that are never activated during waking or sleep
        phases weaken over time. Schemas with zero recurrence that are older than
        ``idle_days`` lose ``decay_amount`` salience per call. Those whose salience
        falls below ``review_threshold`` are flagged ``needs_review`` for eventual
        pruning.

        Only affects ``active`` schemas with ``recurrence_count == 0`` (or missing)
        and ``first_formed_ts`` older than ``idle_days``. Explicit-remember schemas
        (``source_kind == "explicit_remember"``) are intentionally excluded — the
        user asked us to keep those.

        Returns a stats dict with ``decayed``, ``flagged_review``, ``dry_run``.
        """
        now = int(time.time())
        cutoff_ts = now - int(idle_days * 86400)
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT id, salience, facets_json, first_formed_ts FROM schemas "
            "WHERE status = 'active' AND first_formed_ts < ?",
            (cutoff_ts,),
        ).fetchall()

        decayed = 0
        flagged = 0
        for row in rows:
            facets = loads_json(row["facets_json"])
            if not isinstance(facets, dict):
                facets = {}
            # Skip explicitly remembered schemas — user-authored memories are preserved.
            source_kind = str(facets.get("source_kind") or facets.get("source") or "")
            if source_kind == "explicit_remember":
                continue
            recurrence = int(facets.get("recurrence_count", 0))
            if recurrence > 0:
                continue  # schema has been recalled at least once — leave it alone

            sid = int(row["id"])
            new_salience = max(0.01, float(row["salience"]) - decay_amount)
            flag_review = new_salience < review_threshold

            if not dry_run:
                sets = ["salience = ?", "last_updated_ts = ?"]
                args: list[Any] = [new_salience, now]
                if flag_review:
                    sets.append("needs_review = 1")
                args.append(sid)
                conn.execute(f"UPDATE schemas SET {', '.join(sets)} WHERE id = ?", tuple(args))
            decayed += 1
            if flag_review:
                flagged += 1

        if not dry_run:
            conn.commit()

        return {
            "idle_days": idle_days,
            "decay_amount": decay_amount,
            "review_threshold": review_threshold,
            "decayed": decayed,
            "flagged_review": flagged,
            "dry_run": dry_run,
        }

    def count(self) -> int:
        conn = self.db.connect()
        row = conn.execute("SELECT COUNT(*) AS n FROM schemas").fetchone()
        return int(row["n"])

    def _row_to_schema(self, row: Any) -> Schema:
        supporting = loads_json(row["supporting_episode_ids"]).get("ids", [])
        contradicting = loads_json(row["contradicting_episode_ids"]).get("ids", [])
        return Schema(
            id=int(row["id"]),
            prototype_id=None if row["prototype_id"] is None else int(row["prototype_id"]),
            content_text=str(row["content_text"]),
            facets=loads_json(row["facets_json"]),
            tags=[str(t) for t in loads_json(row["tags_json"]).get("tags", [])],
            project=None if row["project"] is None else str(row["project"]),
            status=str(row["status"]),
            confidence=float(row["confidence"]),
            salience=float(row["salience"]),
            supporting_episode_ids=[int(x) for x in supporting],
            contradicting_episode_ids=[int(x) for x in contradicting],
            needs_review=bool(row["needs_review"]),
            first_formed_ts=int(row["first_formed_ts"]),
            last_updated_ts=int(row["last_updated_ts"]),
        )