"""
orchestrator.memory
======================

Phase-10 Memory Management.

Public API surface for this package. Callers should import from here
rather than reaching into individual submodules, so the internal module
layout (schema/serializers split) can change without breaking callers --
the same convention ``orchestrator.persistence`` (Phase-05) established.

Two ``MemoryStore`` implementations are provided:

    - ``InMemoryStore``: Working Memory -- a dict-backed store, not
      persisted across process restarts.
    - ``SQLiteMemoryStore``: Persistent Memory -- durable across
      restarts, stored in the same SQLite database file the Phase-05
      persistence layer uses.

``MemoryManager`` is the Facade both are used through; it defaults to
``InMemoryStore()`` (Working Memory) when no store is supplied.

See ``docs/architecture/decision-records/ADR-0008-memory-management.md``
for the rationale behind these design choices.
"""

from __future__ import annotations

from orchestrator.memory.in_memory_store import InMemoryStore
from orchestrator.memory.memory_manager import MemoryManager
from orchestrator.memory.memory_store import MemoryStore
from orchestrator.memory.models import MemoryEntry
from orchestrator.memory.sqlite_memory_store import SQLiteMemoryStore

__all__ = [
    "MemoryEntry",
    "MemoryManager",
    "MemoryStore",
    "InMemoryStore",
    "SQLiteMemoryStore",
]
