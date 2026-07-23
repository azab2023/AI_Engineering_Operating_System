"""Unit tests for orchestrator.persistence.repository.InMemoryExecutionRepository.

These pin down that the default repository still behaves exactly like
Phase-04's dict-backed store: add/get/update/list semantics, and
UnknownExecutionError / ExecutionAlreadyExistsError on the expected
failure paths.
"""

from __future__ import annotations

import pytest

from orchestrator.exceptions import ExecutionAlreadyExistsError, UnknownExecutionError
from orchestrator.models import AgentExecution, AgentTask, ExecutionState
from orchestrator.persistence import InMemoryExecutionRepository


def _execution(task_type: str = "code_generation") -> AgentExecution:
    task = AgentTask(task_type=task_type, description="A task")
    return AgentExecution(task=task, state=ExecutionState.PENDING)


def test_add_then_get_round_trips():
    repo = InMemoryExecutionRepository()
    execution = _execution()

    repo.add(execution)

    assert repo.get(execution.execution_id) is execution


def test_add_duplicate_execution_id_raises():
    repo = InMemoryExecutionRepository()
    execution = _execution()
    repo.add(execution)

    with pytest.raises(ExecutionAlreadyExistsError):
        repo.add(execution)


def test_get_unknown_execution_raises():
    repo = InMemoryExecutionRepository()

    with pytest.raises(UnknownExecutionError):
        repo.get("does-not-exist")


def test_update_unknown_execution_raises():
    repo = InMemoryExecutionRepository()
    execution = _execution()

    with pytest.raises(UnknownExecutionError):
        repo.update(execution)


def test_update_persists_mutated_state():
    repo = InMemoryExecutionRepository()
    execution = _execution()
    repo.add(execution)

    execution.state = ExecutionState.RUNNING
    repo.update(execution)

    assert repo.get(execution.execution_id).state == ExecutionState.RUNNING


def test_list_returns_all_and_filters_by_state():
    repo = InMemoryExecutionRepository()
    pending = _execution()
    running = _execution()
    running.state = ExecutionState.RUNNING
    repo.add(pending)
    repo.add(running)

    assert {e.execution_id for e in repo.list()} == {
        pending.execution_id,
        running.execution_id,
    }
    assert [e.execution_id for e in repo.list(state=ExecutionState.RUNNING)] == [
        running.execution_id
    ]
    assert repo.list(state=ExecutionState.FAILED) == []


def test_contains_reflects_membership():
    repo = InMemoryExecutionRepository()
    execution = _execution()

    assert execution.execution_id not in repo
    repo.add(execution)
    assert execution.execution_id in repo
