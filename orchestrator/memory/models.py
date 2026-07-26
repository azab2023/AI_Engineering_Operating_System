"""
orchestrator.memory.models
=============================

Data models for Phase-10 (Memory Management).

Design notes:
    - Plain, frozen dataclass only, matching the convention already
      established in ``orchestrator.models`` (Phase-04),
      ``orchestrator.providers.models`` (Phase-07),
      ``orchestrator.prompts.models`` (Phase-08), and
      ``orchestrator.tools.models`` (Phase-09) -- no pydantic / ORM /
      external validation libraries.
    - ``id`` and ``(key, scope)`` serve different purposes: ``id`` is
      the record's own identity (a ``uuid.uuid4()`` ``default_factory``,
      same convention as ``AgentTask.task_id`` / ``AgentExecution.
      execution_id`` in Phase-04), while ``(key, scope)`` is how a
      caller looks a value up. ``scope`` is a free-form namespace
      (e.g. an agent name or session id) and defaults to ``"default"``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class MemoryEntry:
    """One stored value in the Memory subsystem, uniquely identified
    within a ``MemoryStore`` by its ``(key, scope)`` pair.

    Attributes:
        key: the lookup name within ``scope``.
        value: the stored value.
        scope: a free-form namespace the entry belongs to. Defaults to
            ``"default"`` so single-namespace callers never need to
            think about scoping.
        id: the entry's own identity, independent of ``key``/``scope``.
        created_at: UTC timestamp set once, at construction.
        updated_at: UTC timestamp, refreshed by ``MemoryManager.
            remember()`` on every update (see ``memory_manager.py``).
        metadata: free-form string key/value annotations, for callers
            that need to attach extra context (e.g. a source, a
            confidence label) without changing the schema.
    """

    key: str
    value: str
    scope: str = "default"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip():
            raise ValueError("MemoryEntry.key must be a non-empty string")
        if not self.scope or not self.scope.strip():
            raise ValueError("MemoryEntry.scope must be a non-empty string")
        if not self.id or not self.id.strip():
            raise ValueError("MemoryEntry.id must be a non-empty string")
