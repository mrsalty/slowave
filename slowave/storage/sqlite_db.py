from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SQLiteConfig:
    path: str = "slowwave.db"


class SQLiteDB:
    """Very small SQLite wrapper.

    We keep this intentionally minimal to avoid overengineering.
    """

    def __init__(self, cfg: SQLiteConfig):
        self.cfg = cfg
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.cfg.path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def init_schema(self, schema_path: str) -> None:
        conn = self.connect()
        sql = Path(schema_path).read_text(encoding="utf-8")
        # Pre-migrations: bring legacy tables up to the column shape the
        # schema script expects. The script creates indexes on columns
        # (e.g. scale) that did not exist before Stage 9; without this
        # pre-pass, executing the script against an old DB would fail
        # on the CREATE INDEX before the migrations had a chance to run.
        self._apply_pre_migrations()
        conn.executescript(sql)
        conn.commit()
        # Post-migrations: anything that needs the new schema script to
        # have run first (table rebuilds for PK changes, index refresh).
        self._apply_post_migrations()

    def _apply_pre_migrations(self) -> None:
        """Bring legacy tables up to the column shape the schema script
        expects. Runs BEFORE the schema script's CREATE INDEX statements.

        Adds columns that didn't exist in earlier versions of the DB but
        that newer indexes / queries depend on. Must be idempotent and
        must not fail when the table doesn't exist yet (fresh install).

        The catalogue below lists every (table, column, sqlite_type)
        added across the project's lifetime. Adding a new column to
        schema.sql? Add a row here too, or legacy DBs will break on the
        next open.
        """
        import sqlite3 as _sqlite3
        conn = self.connect()

        missing_columns = [
            # Stage 9 (commit 777ea1d)
            ("semantic_prototypes", "scale", "TEXT NOT NULL DEFAULT 'fine'"),
            # `schemas` table evolved heavily between v1 (May) and now.
            # Every column the current schema.sql declares but legacy
            # DBs may lack:
            ("schemas", "prototype_id", "INTEGER"),
            ("schemas", "facets_json", "TEXT NOT NULL DEFAULT '{}'"),
            ("schemas", "tags_json", "TEXT NOT NULL DEFAULT '{\"tags\":[]}'"),
            ("schemas", "project", "TEXT"),
            ("schemas", "status", "TEXT NOT NULL DEFAULT 'active'"),
            ("schemas", "confidence", "REAL NOT NULL DEFAULT 1.0"),
            ("schemas", "salience", "REAL NOT NULL DEFAULT 1.0"),
            ("schemas", "embedding", "BLOB"),
            ("schemas", "dim", "INTEGER"),
        ]

        for table, column, type_spec in missing_columns:
            # Skip silently when the table itself doesn't exist (fresh
            # install — the schema script will create it with the right
            # shape in a moment).
            t = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if t is None:
                continue
            try:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {type_spec}"
                )
            except _sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
        conn.commit()

    def _apply_post_migrations(self) -> None:
        """Idempotent forward migrations that need the schema script to
        have already run (e.g. table rebuilds that change a PK).

        See slowave/storage/schema.sql for the authoritative shape.
        """
        conn = self.connect()

        # ---- Stage 9: episode_prototype_map composite PK ---------------
        # Legacy schema declared PRIMARY KEY (episode_id) which constrained
        # an episode to one prototype. Stage 9 needs one mapping per
        # scale, so the PK is now (episode_id, prototype_id). SQLite
        # cannot ALTER a PRIMARY KEY in place; detect the old shape and
        # rebuild the table preserving every row.
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='episode_prototype_map'"
        ).fetchone()
        if row is not None:
            old_sql = str(row["sql"])
            needs_rebuild = (
                "PRIMARY KEY (episode_id)" in old_sql
                and "PRIMARY KEY (episode_id, prototype_id)" not in old_sql
            )
            if needs_rebuild:
                # Disable FK enforcement for the rebuild. Some legacy
                # rows may reference deleted episodes/prototypes (the
                # old PK constraint didn't have FKs); the rebuild
                # preserves what's there and the engine treats orphans
                # as no-ops on read. Re-enable FKs after.
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.executescript(
                    """
                    CREATE TABLE episode_prototype_map_new (
                      episode_id INTEGER NOT NULL,
                      prototype_id INTEGER NOT NULL,
                      PRIMARY KEY (episode_id, prototype_id),
                      FOREIGN KEY (episode_id) REFERENCES episodic_memories(id) ON DELETE CASCADE,
                      FOREIGN KEY (prototype_id) REFERENCES semantic_prototypes(id) ON DELETE CASCADE
                    );
                    INSERT OR IGNORE INTO episode_prototype_map_new (episode_id, prototype_id)
                      SELECT episode_id, prototype_id FROM episode_prototype_map;
                    DROP TABLE episode_prototype_map;
                    ALTER TABLE episode_prototype_map_new RENAME TO episode_prototype_map;
                    """
                )
                conn.execute("PRAGMA foreign_keys = ON")
        # Always (re-)create the indexes; IF NOT EXISTS makes it safe.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_map_prototype_id "
            "ON episode_prototype_map (prototype_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_map_episode_id "
            "ON episode_prototype_map (episode_id)"
        )

        conn.commit()
