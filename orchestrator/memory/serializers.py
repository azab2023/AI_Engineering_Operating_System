"""
orchestrator.memory.serializers
===================================

Conversion between ``MemoryEntry`` (the in-memory domain model) and the
flat row representation stored in the SQLite ``memory_entries`` table.
Mirrors ``orchestrator.persistence.serializers`` (Phase-05): a pure,
storage-shape concern kept separate from ``sqlite_memory_store.py``'s
SQL/connection logic, per the same rationale ADR-0003 already
established.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from orchestrator.exceptions import MemorySerializationError
from orchestrator.memory.models import MemoryEntry


def memory_entry_to_row(entry: MemoryEntry) -> dict[str, Any]:
    """Flatten a ``MemoryEntry`` into column values for SQLite."""
    return {
        "id": entry.id,
        "key": entry.key,
        "scope": entry.scope,
        "value": entry.value,
        "metadata": json.dumps(entry.metadata),
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


def row_to_memory_entry(row: sqlite3.Row) -> MemoryEntry:
    """Reconstruct a ``MemoryEntry`` from one ``memory_entries`` row.

    Raises:
        MemorySerializationError: ``metadata`` is not valid JSON, or a
            timestamp column is not valid ISO 8601 -- both treated as
            stored-data corruption, per the project's fail-loudly
            philosophy (``orchestrator/exceptions.py``).
    """
    try:
        metadata = json.loads(row["metadata"])
    except json.JSONDecodeError as exc:
        raise MemorySerializationError(
            f"Memory entry {row['id']!r} has non-JSON metadata: {row['metadata']!r}"
        ) from exc

    try:
        created_at = datetime.fromisoformat(row["created_at"])
        updated_at = datetime.fromisoformat(row["updated_at"])
    except ValueError as exc:
        raise MemorySerializationError(
            f"Memory entry {row['id']!r} has an unparsable timestamp"
        ) from exc

    return MemoryEntry(
        id=row["id"],
        key=row["key"],
        scope=row["scope"],
        value=row["value"],
        metadata=metadata,
        created_at=created_at.astimezone(UTC),
        updated_at=updated_at.astimezone(UTC),
    )
