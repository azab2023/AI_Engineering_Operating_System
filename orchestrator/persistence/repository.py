"""
orchestrator.persistence.repository
======================================

Defines the ``ExecutionRepository`` interface (Repository Pattern) that
``orchestrator.core.Orchestrator`` depends on for all execution
state storage, plus ``InMemoryExecutionRepository``, the default,
non-persistent implementation.

Why an interface instead of hard-coding SQLite into ``Orchestrator``:
    ``Orchestrator`` should not know or care whether execution state
    lives in a dict, a SQLite file, or (later) something else entirely.
    Depending on an abstraction keeps ``core.py`` unit-testable without a
    real database and keeps the door open for a future backend (e.g.
    Postgres) without touching orchestration logic again.

Why ``InMemoryExecutionRepository`` still exists and is the default:
    Phase-04's ``Orchestrator`` stored executions in a plain
    ``dict[str, AgentExecution]`` with no persistence at all. This class
    reproduces that exact behavior (same lookups, same
    ``UnknownExecutionError`` on a missing id) so that
    ``Orchestrator(registry)`` -- the Phase-04 call signature -- keeps
    working unmodified. Backward compatibility is structural, not a
    side effect: nothing about default construction changed.
"""

from __future__ import annotations

import abc

from orchestrator.exceptions import ExecutionAlreadyExistsError, UnknownExecutionError
from orchestrator.models import AgentExecution, ExecutionState


class ExecutionRepository(abc.ABC):
    """Storage abstraction for ``AgentExecution`` records.

    Implementations are responsible for persisting whatever fields
    ``AgentExecution`` currently has, including the resolved
    ``assigned_agent`` (an ``Agent`` instance, not just its name), so
    that callers reading an execution back get a fully usable object
    regardless of backend.
    """

    @abc.abstractmethod
    def add(self, execution: AgentExecution) -> None:
        """Store a newly created execution.

        Raises:
            ExecutionAlreadyExistsError: an execution with the same
                ``execution_id`` is already stored.
        """

    @abc.abstractmethod
    def update(self, execution: AgentExecution) -> None:
        """Persist the current state of an already-stored execution.

        Raises:
            UnknownExecutionError: no execution with this ``execution_id``
                has been ``add``-ed yet.
        """

    @abc.abstractmethod
    def get(self, execution_id: str) -> AgentExecution:
        """Look up a single execution by id.

        Raises:
            UnknownExecutionError: no execution with this id is stored.
        """

    @abc.abstractmethod
    def list(self, state: ExecutionState | None = None) -> list[AgentExecution]:
        """Return all stored executions, optionally filtered by state."""

    def __contains__(self, execution_id: str) -> bool:
        try:
            self.get(execution_id)
        except UnknownExecutionError:
            return False
        return True


class InMemoryExecutionRepository(ExecutionRepository):
    """Dict-backed ``ExecutionRepository``. Not persisted across restarts.

    This is the Phase-04 behavior, unchanged, wrapped behind the Phase-05
    ``ExecutionRepository`` interface.
    """

    def __init__(self) -> None:
        self._executions: dict[str, AgentExecution] = {}

    def add(self, execution: AgentExecution) -> None:
        if execution.execution_id in self._executions:
            raise ExecutionAlreadyExistsError(execution.execution_id)
        self._executions[execution.execution_id] = execution

    def update(self, execution: AgentExecution) -> None:
        if execution.execution_id not in self._executions:
            raise UnknownExecutionError(execution.execution_id)
        self._executions[execution.execution_id] = execution

    def get(self, execution_id: str) -> AgentExecution:
        try:
            return self._executions[execution_id]
        except KeyError as exc:
            raise UnknownExecutionError(execution_id) from exc

    def list(self, state: ExecutionState | None = None) -> list[AgentExecution]:
        executions = list(self._executions.values())
        if state is not None:
            executions = [e for e in executions if e.state == state]
        return executions
