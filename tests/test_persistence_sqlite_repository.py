"""Unit tests for orchestrator.persistence.sqlite_repository.SqliteExecutionRepository.

Covers the Repository Pattern contract (add/get/update/list,
ExecutionAlreadyExistsError / UnknownExecutionError), persistence across
a real reconnect (the actual point of Phase-05), assigned_agent
round-tripping through the registry, and ExecutionSerializationError on
corrupt stored data.
"""

from __future__ import annotations

import sqlite3

import pytest

from orchestrator.exceptions import (
    ExecutionAlreadyExistsError,
    ExecutionSerializationError,
    UnknownExecutionError,
)
from orchestrator.models import AgentExecution, AgentTask, ExecutionState
from orchestrator.persistence.schema import initialize_schema
from orchestrator.persistence.sqlite_repository import SqliteExecutionRepository
from orchestrator.registry import DEFAULT_REGISTRY_PATH, AgentRegistry


@pytest.fixture()
def registry() -> AgentRegistry:
    return AgentRegistry(DEFAULT_REGISTRY_PATH)


@pytest.fixture()
def repo(registry: AgentRegistry):
    repository = SqliteExecutionRepository(registry, db_path=":memory:")
    yield repository
    repository.close()


def _execution(task_type: str = "code_generation") -> AgentExecution:
    task = AgentTask(task_type=task_type, description="A task")
    return AgentExecution(task=task, state=ExecutionState.PENDING)


def test_add_then_get_round_trips(repo: SqliteExecutionRepository):
    execution = _execution()

    repo.add(execution)
    fetched = repo.get(execution.execution_id)

    assert fetched.execution_id == execution.execution_id
    assert fetched.state == ExecutionState.PENDING
    assert fetched.task.task_type == "code_generation"
    assert fetched.task.task_id == execution.task.task_id
    assert fetched.assigned_agent is None


def test_add_duplicate_execution_id_raises(repo: SqliteExecutionRepository):
    execution = _execution()
    repo.add(execution)

    with pytest.raises(ExecutionAlreadyExistsError):
        repo.add(execution)


def test_get_unknown_execution_raises(repo: SqliteExecutionRepository):
    with pytest.raises(UnknownExecutionError):
        repo.get("does-not-exist")


def test_update_unknown_execution_raises(repo: SqliteExecutionRepository):
    execution = _execution()

    with pytest.raises(UnknownExecutionError):
        repo.update(execution)


def test_update_persists_mutated_state_and_assigned_agent(
    repo: SqliteExecutionRepository, registry: AgentRegistry
):
    execution = _execution()
    repo.add(execution)

    agent = registry.get_agent("claude_code")
    execution.assigned_agent = agent
    execution.state = ExecutionState.ASSIGNED
    execution.touch()
    repo.update(execution)

    fetched = repo.get(execution.execution_id)
    assert fetched.state == ExecutionState.ASSIGNED
    assert fetched.assigned_agent is agent  # same registry -> same object


def test_list_returns_all_and_filters_by_state(repo: SqliteExecutionRepository):
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


def test_data_survives_reconnect_to_the_same_file(tmp_path, registry: AgentRegistry):
    """The actual point of Phase-05: state must outlive the process/connection."""
    db_path = tmp_path / "aeos_test.db"
    execution = _execution()

    first = SqliteExecutionRepository(registry, db_path=db_path)
    first.add(execution)
    first.close()

    second = SqliteExecutionRepository(registry, db_path=db_path)
    try:
        fetched = second.get(execution.execution_id)
        assert fetched.state == ExecutionState.PENDING
        assert fetched.task.description == "A task"
    finally:
        second.close()


def test_row_with_invalid_state_raises_serialization_error(registry: AgentRegistry):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    conn.execute(
        """
        INSERT INTO executions (
            execution_id, task_id, task_type, task_description,
            required_capabilities, state, assigned_agent_name, result, error,
            created_at, updated_at
        ) VALUES ('exec-1', 'task-1', 'code_generation', 'desc', '[]',
                  'not_a_real_state', NULL, NULL, NULL,
                  '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00');
        """
    )
    conn.commit()

    from orchestrator.persistence.serializers import row_to_execution

    row = conn.execute("SELECT * FROM executions WHERE execution_id = 'exec-1'").fetchone()
    with pytest.raises(ExecutionSerializationError):
        row_to_execution(row, registry)
    conn.close()


def test_row_with_unknown_assigned_agent_raises_serialization_error(registry: AgentRegistry):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    conn.execute(
        """
        INSERT INTO executions (
            execution_id, task_id, task_type, task_description,
            required_capabilities, state, assigned_agent_name, result, error,
            created_at, updated_at
        ) VALUES ('exec-1', 'task-1', 'code_generation', 'desc', '[]',
                  'assigned', 'an_agent_that_was_deleted', NULL, NULL,
                  '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00');
        """
    )
    conn.commit()

    from orchestrator.persistence.serializers import row_to_execution

    row = conn.execute("SELECT * FROM executions WHERE execution_id = 'exec-1'").fetchone()
    with pytest.raises(ExecutionSerializationError):
        row_to_execution(row, registry)
    conn.close()


def test_initialize_schema_is_idempotent():
    conn = sqlite3.connect(":memory:")
    initialize_schema(conn)
    initialize_schema(conn)  # must not raise
    conn.close()


def test_row_with_invalid_json_capabilities_raises_serialization_error(
    registry: AgentRegistry,
):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    conn.execute(
        """
        INSERT INTO executions (
            execution_id, task_id, task_type, task_description,
            required_capabilities, state, assigned_agent_name, result, error,
            created_at, updated_at
        ) VALUES ('exec-1', 'task-1', 'code_generation', 'desc', 'not-json',
                  'pending', NULL, NULL, NULL,
                  '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00');
        """
    )
    conn.commit()

    from orchestrator.persistence.serializers import row_to_execution

    row = conn.execute("SELECT * FROM executions WHERE execution_id = 'exec-1'").fetchone()
    with pytest.raises(ExecutionSerializationError):
        row_to_execution(row, registry)
    conn.close()


def test_row_with_malformed_timestamp_raises_serialization_error(registry: AgentRegistry):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    conn.execute(
        """
        INSERT INTO executions (
            execution_id, task_id, task_type, task_description,
            required_capabilities, state, assigned_agent_name, result, error,
            created_at, updated_at
        ) VALUES ('exec-1', 'task-1', 'code_generation', 'desc', '[]',
                  'pending', NULL, NULL, NULL,
                  'not-a-timestamp', '2025-01-01T00:00:00+00:00');
        """
    )
    conn.commit()

    from orchestrator.persistence.serializers import row_to_execution

    row = conn.execute("SELECT * FROM executions WHERE execution_id = 'exec-1'").fetchone()
    with pytest.raises(ExecutionSerializationError):
        row_to_execution(row, registry)
    conn.close()


def test_repository_usable_as_a_context_manager(registry: AgentRegistry):
    with SqliteExecutionRepository(registry, db_path=":memory:") as repo:
        execution = _execution()
        repo.add(execution)
        assert repo.get(execution.execution_id).execution_id == execution.execution_id
