"""Episode text store: human-readable content + provenance to raw events.

Lives alongside the latent EpisodicStore (which holds embeddings). Joined
via episode_id (1:1 with episodic_memories.id).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from slowave.storage.sqlite_db import SQLiteDB
from slowave.utils.vec import dumps_json, loads_json


@dataclass(frozen=True)
class EpisodeText:
    episode_id: int
    content_text: str
    source_content: str  # raw event content without role prefix; used as schema claim
    event_ids: list[int]
    session_id: str | None


class EpisodeTextStore:
    def __init__(self, db: SQLiteDB):
        self.db = db

    def put(
        self,
        *,
        episode_id: int,
        content_text: str,
        source_content: str | None = None,
        event_ids: list[int],
        session_id: str | None = None,
    ) -> None:
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO episode_text (episode_id, content_text, source_content, event_ids, session_id) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(episode_id) DO UPDATE SET "
            "content_text=excluded.content_text, source_content=excluded.source_content, "
            "event_ids=excluded.event_ids, session_id=excluded.session_id",
            (
                int(episode_id),
                str(content_text),
                source_content,
                dumps_json({"ids": [int(e) for e in event_ids]}),
                session_id,
            ),
        )
        # Keep FTS aligned. Standard (non-contentless) FTS5 supports plain
        # DELETE by rowid; the followup INSERT re-indexes.
        conn.execute("DELETE FROM episodes_fts WHERE rowid = ?", (int(episode_id),))
        conn.execute(
            "INSERT INTO episodes_fts (rowid, content_text) VALUES (?, ?)",
            (int(episode_id), content_text),
        )
        conn.commit()

    def get(self, episode_id: int) -> EpisodeText | None:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT * FROM episode_text WHERE episode_id = ?", (int(episode_id),)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_episode_text(row)

    def get_many(self, episode_ids: Iterable[int]) -> list[EpisodeText]:
        ids = list(dict.fromkeys(int(i) for i in episode_ids))
        if not ids:
            return []
        ph = ",".join(["?"] * len(ids))
        conn = self.db.connect()
        rows = conn.execute(
            f"SELECT * FROM episode_text WHERE episode_id IN ({ph})", tuple(ids)
        ).fetchall()
        by_id = {int(r["episode_id"]): r for r in rows}
        out = []
        for i in ids:
            r = by_id.get(i)
            if r is None:
                continue
            out.append(self._row_to_episode_text(r))
        return out

    def search_fts(self, query: str, limit: int = 20) -> list[int]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT rowid FROM episodes_fts WHERE episodes_fts MATCH ? " "ORDER BY rank LIMIT ?",
            (query, int(limit)),
        ).fetchall()
        return [int(r["rowid"]) for r in rows]

    def _row_to_episode_text(self, row: Any) -> EpisodeText:
        event_ids = loads_json(row["event_ids"]).get("ids", [])
        raw_source = (
            row["source_content"] if row["source_content"] is not None else row["content_text"]
        )
        return EpisodeText(
            episode_id=int(row["episode_id"]),
            content_text=str(row["content_text"]),
            source_content=str(raw_source),
            event_ids=[int(x) for x in event_ids],
            session_id=None if row["session_id"] is None else str(row["session_id"]),
        )
