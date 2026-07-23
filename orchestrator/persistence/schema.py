"""
orchestrator.persistence.schema
==================================

SQLite schema definition and initialization for the Phase-05 persistence
layer.

Only one table is needed for this phase's scope (``executions``) plus a
tiny ``schema_meta`` table used to record the schema version a database
file was created with. This is intentionally minimal, not a migration
framework: if a future phase needs real migrations, ``schema_meta`` is
the hook a migration runner would read/write, but no such runner exists
yet (out of scope for Phase-05, per ADR-0003).
"""

from __future__ import annotations

import sqlite3

# Bump this if the ``executions`` table shape changes in a future phase.
SCHEMA_VERSION = 1

_CREATE_SCHEMA_META_TABLE = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_CREATE_EXECUTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS executions (
    execution_id           TEXT PRIMARY KEY,
    task_id                TEXT NOT NULL,
    task_type               TEXT NOT NULL,
    task_description         TEXT NOT NULL,
    required_capabilities     TEXT NOT NULL,  -- JSON array of strings
    state                       TEXT NOT NULL,
    assigned_agent_name         TEXT,          -- NULL until routed
    result                        TEXT,        -- NULL until awaiting_approval
    error                          TEXT,       -- NULL unless failed
    created_at                      TEXT NOT NULL,  -- ISO 8601 UTC
    updated_at                       TEXT NOT NULL   -- ISO 8601 UTC
);
"""

_CREATE_EXECUTIONS_STATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_executions_state ON executions (state);
"""


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Create the persistence schema if it does not already exist.

    Safe to call on every connection open (idempotent, all statements use
    ``IF NOT EXISTS``), matching the "all automation must be idempotent"
    principle from ``CLAUDE.md``.
    """
    with conn:
        conn.execute(_CREATE_SCHEMA_META_TABLE)
        conn.execute(_CREATE_EXECUTIONS_TABLE)
        conn.execute(_CREATE_EXECUTIONS_STATE_INDEX)
        conn.execute(
            "INSERT OR IGNORE INTO schema_meta (key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
