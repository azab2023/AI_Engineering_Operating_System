"""
orchestrator.persistence.db
==============================

Connection management for the SQLite persistence backend.

Kept deliberately small: one function to open a correctly-configured
connection. No connection pooling is implemented -- SQLite's own
locking plus WAL mode is sufficient for this phase's scope (a single
AEOS process using the orchestrator), and adding a pool now would be
speculative complexity ADR-0003 explicitly avoids.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from orchestrator.persistence.schema import initialize_schema

DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "aeos.db"


def connect(db_path: str | Path = DEFAULT_SQLITE_PATH) -> sqlite3.Connection:
    """Open a SQLite connection configured for the persistence layer.

    - Rows are returned as ``sqlite3.Row`` (dict-like access by column name)
      so ``serializers.py`` never has to rely on positional indexing.
    - Foreign keys are enabled (defensive default; no FKs exist yet in
      Phase-05's single-table schema, but this avoids a silent footgun
      if a related table is added later).
    - WAL journal mode reduces writer/reader contention. It is a no-op
      (silently ignored) for the special ``:memory:`` database used in
      tests, which is fine.
    - The schema is (re)initialized on every connect call; see
      ``schema.initialize_schema`` for why that is safe to do
      unconditionally.
    """
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")

    initialize_schema(conn)
    return conn
