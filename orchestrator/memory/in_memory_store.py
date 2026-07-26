"""
orchestrator.memory.in_memory_store
=======================================

``InMemoryStore``: the Working Memory ``MemoryStore`` implementation --
a dict-backed store, not persisted across process restarts. This is the
Memory-subsystem analogue of ``InMemoryExecutionRepository`` (Phase-05).

It is also ``MemoryManager``'s default backend (see
``memory_manager.py``), so constructing ``MemoryManager()`` with no
arguments gives Working Memory, matching how ``Orchestrator()``
defaults to an in-memory ``ExecutionRepository`` in Phase-05.
"""

from __future__ import annotations

from orchestrator.exceptions import MemoryEntryAlreadyExistsError, MemoryEntryNotFoundError
from orchestrator.memory.models import MemoryEntry


class InMemoryStore:
    """Dict-backed ``MemoryStore``, keyed by ``(scope, key)``. Not
    persisted across restarts."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], MemoryEntry] = {}

    def add(self, entry: MemoryEntry) -> None:
        index = (entry.scope, entry.key)
        if index in self._entries:
            raise MemoryEntryAlreadyExistsError(entry.key, entry.scope)
        self._entries[index] = entry

    def update(self, entry: MemoryEntry) -> None:
        index = (entry.scope, entry.key)
        if index not in self._entries:
            raise MemoryEntryNotFoundError(entry.key, entry.scope)
        self._entries[index] = entry

    def get(self, key: str, scope: str = "default") -> MemoryEntry:
        try:
            return self._entries[(scope, key)]
        except KeyError as exc:
            raise MemoryEntryNotFoundError(key, scope) from exc

    def delete(self, key: str, scope: str = "default") -> None:
        try:
            del self._entries[(scope, key)]
        except KeyError as exc:
            raise MemoryEntryNotFoundError(key, scope) from exc

    def list(self, scope: str | None = None) -> list[MemoryEntry]:
        entries = list(self._entries.values())
        if scope is not None:
            entries = [e for e in entries if e.scope == scope]
        return entries
