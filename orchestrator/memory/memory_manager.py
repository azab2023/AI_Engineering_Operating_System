"""
orchestrator.memory.memory_manager
======================================

``MemoryManager``: the sole Facade for using the Memory subsystem,
following the same architectural style as ``PromptManager`` (Phase-08)
and ``ToolExecutor`` (Phase-09) -- it composes a single dependency
behind its own Protocol/Port and adds higher-level operations a raw
store does not provide (see ADR-0008 decision 5).

Phase-10 does not wire this into ``AgentTask``, ``ExecutionEngine``, or
``ToolExecutor`` -- see ADR-0008 decision 7. It is a self-contained,
additive package with no call sites elsewhere in the codebase yet.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from orchestrator.exceptions import MemoryEntryNotFoundError
from orchestrator.logging_setup import get_logger
from orchestrator.memory.in_memory_store import InMemoryStore
from orchestrator.memory.memory_store import MemoryStore
from orchestrator.memory.models import MemoryEntry

logger = get_logger("memory.memory_manager")


class MemoryManager:
    """Remember, recall, and forget named values through a
    ``MemoryStore``.

    Args:
        store: the ``MemoryStore`` backend to use. Defaults to
            ``InMemoryStore()`` -- i.e. Working Memory -- mirroring how
            ``Orchestrator`` (Phase-05) defaults to an in-memory
            ``ExecutionRepository``. Pass a ``SQLiteMemoryStore``
            instance for Persistent Memory.
    """

    def __init__(self, store: MemoryStore | None = None):
        self._store = store or InMemoryStore()

    def remember(
        self,
        key: str,
        value: str,
        scope: str = "default",
        metadata: dict[str, str] | None = None,
    ) -> MemoryEntry:
        """Store ``value`` under ``(key, scope)``, creating a new entry
        or updating the existing one -- callers never need to know in
        advance which case applies.

        A new entry gets a fresh ``id``/``created_at``. Updating an
        existing entry preserves its ``id``/``created_at`` and refreshes
        ``updated_at``.
        """
        metadata = metadata or {}
        try:
            existing = self._store.get(key, scope)
        except MemoryEntryNotFoundError:
            entry = MemoryEntry(key=key, value=value, scope=scope, metadata=metadata)
            self._store.add(entry)
            logger.info("Memory entry created: key=%s scope=%s", key, scope)
            return entry

        updated = replace(
            existing,
            value=value,
            metadata=metadata,
            updated_at=datetime.now(UTC),
        )
        self._store.update(updated)
        logger.info("Memory entry updated: key=%s scope=%s", key, scope)
        return updated

    def recall(self, key: str, scope: str = "default") -> MemoryEntry:
        """Return the entry stored under ``(key, scope)``.

        Raises:
            MemoryEntryNotFoundError: no entry exists for this pair.
        """
        return self._store.get(key, scope)

    def forget(self, key: str, scope: str = "default") -> None:
        """Remove the entry stored under ``(key, scope)``.

        Raises:
            MemoryEntryNotFoundError: no entry exists for this pair.
        """
        self._store.delete(key, scope)
        logger.info("Memory entry forgotten: key=%s scope=%s", key, scope)

    def list(self, scope: str | None = None) -> list[MemoryEntry]:
        """Return all stored entries, optionally filtered by ``scope``."""
        return self._store.list(scope)
