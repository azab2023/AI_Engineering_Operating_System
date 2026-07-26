"""
orchestrator.memory.memory_store
====================================

Defines ``MemoryStore``, the Port (Strategy/Protocol pattern) a Memory
backend must conform to.

This mirrors ``ModelProvider`` (Phase-07) and ``Tool`` (Phase-09) one
layer over: ``MemoryManager`` (``memory_manager.py``) depends only on
this Protocol -- never on a concrete implementation -- so adding a new
backend never requires modifying ``MemoryManager``. See
ADR-0008 decision 2 for why this is a ``typing.Protocol`` rather than
the ``abc.ABC`` shape ``ExecutionRepository`` (Phase-05) uses.

An entry is uniquely identified by its ``(key, scope)`` pair, not by
its own ``MemoryEntry.id``. ``add()``/``update()``/``get()``/
``delete()`` all fail loudly rather than silently succeeding on a
missing or duplicate pair, matching ``ExecutionRepository``'s Phase-05
philosophy.
"""

from __future__ import annotations

from typing import Protocol

from orchestrator.memory.models import MemoryEntry


class MemoryStore(Protocol):
    """Port: storage for named ``MemoryEntry`` records, keyed by
    ``(key, scope)``."""

    def add(self, entry: MemoryEntry) -> None:
        """Store a new entry.

        Raises:
            MemoryEntryAlreadyExistsError: an entry already exists for
                ``(entry.key, entry.scope)``.
        """
        ...

    def update(self, entry: MemoryEntry) -> None:
        """Persist the current state of an already-stored entry.

        Raises:
            MemoryEntryNotFoundError: no entry exists yet for
                ``(entry.key, entry.scope)``.
        """
        ...

    def get(self, key: str, scope: str = "default") -> MemoryEntry:
        """Look up a single entry by ``(key, scope)``.

        Raises:
            MemoryEntryNotFoundError: no entry exists for this pair.
        """
        ...

    def delete(self, key: str, scope: str = "default") -> None:
        """Remove a single entry by ``(key, scope)``.

        Raises:
            MemoryEntryNotFoundError: no entry exists for this pair.
        """
        ...

    def list(self, scope: str | None = None) -> list[MemoryEntry]:
        """Return all stored entries, optionally filtered by ``scope``."""
        ...
