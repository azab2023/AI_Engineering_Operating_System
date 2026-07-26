"""
orchestrator.memory.schema
==============================

SQLite schema definition and initialization for the Phase-10 Persistent
Memory backend.

This *adds* one table (``memory_entries``) to the same database file
``orchestrator/persistence/db.py`` already manages -- it does not
modify ``orchestrator/persistence/schema.py`` or the ``executions``
table in any way (ADR-0008 decision 4). ``schema_meta`` (created by
``orchestrator.persistence.schema.initialize_schema``, which
``persistence.db.connect()`` already calls before a connection is
handed back) is reused to additionally record
``memory_schema_version``, the same "one row per schema concern"
approach ADR-0003 established.
"""

from __future__ import annotations

import sqlite3

# Bump this if the ``memory_entries`` table shape changes in a future phase.
SCHEMA_VERSION = 1

_CREATE_MEMORY_ENTRIES_TABLE = """
CREATE TABLE IF NOT EXISTS memory_entries (
    id           TEXT PRIMARY KEY,
    key          TEXT NOT NULL,
    scope        TEXT NOT NULL,
    value        TEXT NOT NULL,
    metadata     TEXT NOT NULL,  -- JSON object
    created_at   TEXT NOT NULL,  -- ISO 8601 UTC
    updated_at   TEXT NOT NULL,  -- ISO 8601 UTC
    UNIQUE (key, scope)
);
"""

_CREATE_MEMORY_ENTRIES_SCOPE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_memory_entries_scope ON memory_entries (scope);
"""


def initialize_memory_schema(conn: sqlite3.Connection) -> None:
    """Create the ``memory_entries`` table if it does not already exist.

    Safe to call on every connection open (idempotent, all statements
    use ``IF NOT EXISTS``), matching ``persistence.schema.
    initialize_schema``'s convention and the "all automation must be
    idempotent" principle from ``CLAUDE.md``. Assumes ``schema_meta``
    already exists -- callers use ``persistence.db.connect()``, which
    guarantees that.
    """
    with conn:
        conn.execute(_CREATE_MEMORY_ENTRIES_TABLE)
        conn.execute(_CREATE_MEMORY_ENTRIES_SCOPE_INDEX)
        conn.execute(
            "INSERT OR IGNORE INTO schema_meta (key, value) VALUES (?, ?)",
            ("memory_schema_version", str(SCHEMA_VERSION)),
        )
