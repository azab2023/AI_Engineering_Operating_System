"""
orchestrator.persistence
===========================

Phase-05 Persistence Layer.

Public API surface for this package. Callers (primarily
``orchestrator.core.Orchestrator``) should import from here rather than
reaching into individual submodules, so the internal module layout
(schema/serializers/db split) can change without breaking callers.

Two ``ExecutionRepository`` implementations are provided:

    - ``InMemoryExecutionRepository``: a dict-backed store that reproduces
      the exact in-memory behavior ``Orchestrator`` had at the end of
      Phase-04. This is the default used by ``Orchestrator`` when no
      repository is supplied, which is what makes Phase-05 backward
      compatible -- existing callers of ``Orchestrator(registry)`` observe
      no behavior change.
    - ``SqliteExecutionRepository``: a SQLite-backed store that persists
      ``AgentExecution`` records across process restarts.

See ``docs/architecture/decision-records/ADR-0003-persistence-layer.md``
for the rationale behind these design choices.
"""

from __future__ import annotations

from orchestrator.persistence.repository import (
    ExecutionRepository,
    InMemoryExecutionRepository,
)
from orchestrator.persistence.sqlite_repository import SqliteExecutionRepository

__all__ = [
    "ExecutionRepository",
    "InMemoryExecutionRepository",
    "SqliteExecutionRepository",
]
