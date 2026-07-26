"""
orchestrator.memory.sqlite_memory_store
===========================================

``SQLiteMemoryStore``: the Persistent Memory ``MemoryStore``
implementation, backed by SQLite. Reuses
``orchestrator.persistence.db.connect()`` for connection setup (row
factory, foreign keys, WAL mode) exactly as ``SqliteExecutionRepository``
(Phase-05) does, and stores its ``memory_entries`` table in the same
database file -- no new persistence framework is introduced (ADR-0008
decision 4).

Concurrency note:
    Same as ``SqliteExecutionRepository``: a single connection is opened
    once, at construction, and reused for the store's lifetime
    (``close()`` releases it). SQLite's own file-level locking, combined
    with WAL mode, is sufficient for this phase's single-process scope.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from orchestrator.exceptions import MemoryEntryAlreadyExistsError, MemoryEntryNotFoundError
from orchestrator.logging_setup import get_logger
from orchestrator.memory.models import MemoryEntry
from orchestrator.memory.schema import initialize_memory_schema
from orchestrator.memory.serializers import memory_entry_to_row, row_to_memory_entry
from orchestrator.persistence.db import DEFAULT_SQLITE_PATH, connect

logger = get_logger("memory.sqlite_memory_store")

_INSERT_SQL = """
INSERT INTO memory_entries (
    id, key, scope, value, metadata, created_at, updated_at
) VALUES (
    :id, :key, :scope, :value, :metadata, :created_at, :updated_at
);
"""

_UPDATE_SQL = """
UPDATE memory_entries SET
    id = :id,
    value = :value,
    metadata = :metadata,
    created_at = :created_at,
    updated_at = :updated_at
WHERE key = :key AND scope = :scope;
"""

_SELECT_ONE_SQL = "SELECT * FROM memory_entries WHERE key = ? AND scope = ?;"
_DELETE_SQL = "DELETE FROM memory_entries WHERE key = ? AND scope = ?;"
_SELECT_ALL_SQL = "SELECT * FROM memory_entries;"
_SELECT_BY_SCOPE_SQL = "SELECT * FROM memory_entries WHERE scope = ?;"


class SQLiteMemoryStore:
    """SQLite-backed ``MemoryStore``.

    Args:
        db_path: path to the SQLite database file. Defaults to the same
            ``data/aeos.db`` file the Phase-05 persistence layer uses.
            Pass ``":memory:"`` for an ephemeral, test-only database.
    """

    def __init__(self, db_path: str | Path = DEFAULT_SQLITE_PATH) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection = connect(db_path)
        initialize_memory_schema(self._conn)
        logger.info("SQLiteMemoryStore connected: db_path=%s", db_path)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SQLiteMemoryStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # MemoryStore interface
    # ------------------------------------------------------------------ #

    def add(self, entry: MemoryEntry) -> None:
        row = memory_entry_to_row(entry)
        try:
            with self._conn:
                self._conn.execute(_INSERT_SQL, row)
        except sqlite3.IntegrityError as exc:
            raise MemoryEntryAlreadyExistsError(entry.key, entry.scope) from exc

    def update(self, entry: MemoryEntry) -> None:
        row = memory_entry_to_row(entry)
        with self._conn:
            cursor = self._conn.execute(_UPDATE_SQL, row)
        if cursor.rowcount == 0:
            raise MemoryEntryNotFoundError(entry.key, entry.scope)

    def get(self, key: str, scope: str = "default") -> MemoryEntry:
        cursor = self._conn.execute(_SELECT_ONE_SQL, (key, scope))
        row = cursor.fetchone()
        if row is None:
            raise MemoryEntryNotFoundError(key, scope)
        return row_to_memory_entry(row)

    def delete(self, key: str, scope: str = "default") -> None:
        with self._conn:
            cursor = self._conn.execute(_DELETE_SQL, (key, scope))
        if cursor.rowcount == 0:
            raise MemoryEntryNotFoundError(key, scope)

    def list(self, scope: str | None = None) -> list[MemoryEntry]:
        if scope is None:
            cursor = self._conn.execute(_SELECT_ALL_SQL)
        else:
            cursor = self._conn.execute(_SELECT_BY_SCOPE_SQL, (scope,))
        return [row_to_memory_entry(row) for row in cursor.fetchall()]
