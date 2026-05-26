"""Schema store: first-class symbolic semantic memories.

A schema is a durable typed claim consolidated from episodic traces. Unlike the
old one-schema-per-prototype model, schemas now have their own identity,
embedding, salience/status, normalized evidence links, prototype associations,
and relations to other schemas.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from slowave.storage.sqlite_db import SQLiteDB
from slowave.utils.vec import dumps_json, loads_json, pack_f32, unpack_f32


VALID_STATUS = ("active", "needs_review", "superseded", "contradicted", "archived")
VALID_RELATIONS = ("reinforces", "refines", "contradicts", "supersedes", "related_to", "part_of")


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
    ) -> int:
        status = status if status in VALID_STATUS else "active"
        now = int(time.time())
        supporting = [int(x) for x in (supporting_episode_ids or [])]
        contradicting = [int(x) for x in (contradicting_episode_ids or [])]
        proto_ids = list(dict.fromkeys(int(p) for p in (prototype_ids or [])))
        primary_proto = proto_ids[0] if proto_ids else None

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

    def search_fts(self, query: str, limit: int = 20) -> list[int]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT rowid FROM schemas_fts WHERE schemas_fts MATCH ? ORDER BY rank LIMIT ?",
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