"""
orchestrator.workflow.repository
===================================

Defines the ``WorkflowRunRepository`` interface (Repository Pattern)
that ``orchestrator.workflow.workflow_engine.WorkflowEngine`` depends on
for all ``WorkflowRun`` storage, plus ``InMemoryWorkflowRunRepository``,
the default (and, in this phase, only) implementation.

Mirrors ``orchestrator.persistence.repository.ExecutionRepository``
(Phase-05) exactly, one layer up: same four-method shape, same
fail-loudly-on-unknown-id behavior. No SQLite-backed implementation is
added in this phase -- see ADR-0009 decision 5 / Alternatives for why
this is deferred rather than built speculatively, matching how
``ExecutionRepository`` itself shipped in-memory-only in Phase-04, with
``SqliteExecutionRepository`` following a full phase later (Phase-05).
"""

from __future__ import annotations

import abc

from orchestrator.exceptions import UnknownWorkflowRunError, WorkflowRunAlreadyExistsError
from orchestrator.workflow.models import WorkflowRun, WorkflowRunState


class WorkflowRunRepository(abc.ABC):
    """Storage abstraction for ``WorkflowRun`` records."""

    @abc.abstractmethod
    def add(self, run: WorkflowRun) -> None:
        """Store a newly created run.

        Raises:
            WorkflowRunAlreadyExistsError: a run with the same
                ``run_id`` is already stored.
        """

    @abc.abstractmethod
    def update(self, run: WorkflowRun) -> None:
        """Persist the current state of an already-stored run.

        Raises:
            UnknownWorkflowRunError: no run with this ``run_id`` has
                been ``add``-ed yet.
        """

    @abc.abstractmethod
    def get(self, run_id: str) -> WorkflowRun:
        """Look up a single run by id.

        Raises:
            UnknownWorkflowRunError: no run with this id is stored.
        """

    @abc.abstractmethod
    def list(self, state: WorkflowRunState | None = None) -> list[WorkflowRun]:
        """Return all stored runs, optionally filtered by state."""

    def __contains__(self, run_id: str) -> bool:
        try:
            self.get(run_id)
        except UnknownWorkflowRunError:
            return False
        return True


class InMemoryWorkflowRunRepository(WorkflowRunRepository):
    """Dict-backed ``WorkflowRunRepository``. Not persisted across
    restarts -- the default, and in this phase the only, backend."""

    def __init__(self) -> None:
        self._runs: dict[str, WorkflowRun] = {}

    def add(self, run: WorkflowRun) -> None:
        if run.run_id in self._runs:
            raise WorkflowRunAlreadyExistsError(run.run_id)
        self._runs[run.run_id] = run

    def update(self, run: WorkflowRun) -> None:
        if run.run_id not in self._runs:
            raise UnknownWorkflowRunError(run.run_id)
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> WorkflowRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise UnknownWorkflowRunError(run_id) from exc

    def list(self, state: WorkflowRunState | None = None) -> list[WorkflowRun]:
        runs = list(self._runs.values())
        if state is not None:
            runs = [r for r in runs if r.state == state]
        return runs
