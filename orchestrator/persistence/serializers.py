"""
orchestrator.persistence.serializers
=======================================

Conversion between ``AgentExecution`` (the in-memory domain model from
``orchestrator.models``) and the flat row representation stored in the
SQLite ``executions`` table.

Why this lives in its own module instead of on ``SqliteExecutionRepository``:
    Serialization is a pure, storage-shape concern with no SQL/connection
    logic of its own. Separating it makes both halves easier to test in
    isolation and keeps ``sqlite_repository.py`` focused on the
    Repository Pattern's CRUD surface.

Reconstructing ``assigned_agent``:
    ``AgentExecution.assigned_agent`` is a full ``Agent`` object, not a
    name. Only the agent's *name* is stored in SQLite (``agent_registry.
    yaml`` is the source of truth for everything else about an agent).
    Deserializing therefore requires the current ``AgentRegistry`` to
    resolve that name back into an ``Agent``. If the name is no longer
    present in the registry (e.g. an agent was removed from
    ``config/agent_registry.yaml`` after the execution was stored), this
    is treated as data corruption relative to the current registry and
    raises ``ExecutionSerializationError`` rather than silently dropping
    the assignment -- per the "fail loudly" philosophy already
    established in ``orchestrator/exceptions.py``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from orchestrator.exceptions import AgentRegistryError, ExecutionSerializationError
from orchestrator.models import AgentExecution, AgentTask, ExecutionState
from orchestrator.registry import AgentRegistry


def execution_to_row(execution: AgentExecution) -> dict[str, Any]:
    """Flatten an ``AgentExecution`` into column values for SQLite."""
    task = execution.task
    return {
        "execution_id": execution.execution_id,
        "task_id": task.task_id,
        "task_type": task.task_type,
        "task_description": task.description,
        "required_capabilities": json.dumps(list(task.required_capabilities)),
        "state": execution.state.value,
        "assigned_agent_name": execution.assigned_agent.name
        if execution.assigned_agent is not None
        else None,
        "result": execution.result,
        "error": execution.error,
        "created_at": execution.created_at.isoformat(),
        "updated_at": execution.updated_at.isoformat(),
    }


def row_to_execution(row: sqlite3.Row, registry: AgentRegistry) -> AgentExecution:
    """Reconstruct an ``AgentExecution`` from a stored SQLite row.

    Raises:
        ExecutionSerializationError: the row's ``state`` is not a valid
            ``ExecutionState``, ``required_capabilities`` is not valid
            JSON, or ``assigned_agent_name`` no longer exists in
            ``registry``.
    """
    execution_id = row["execution_id"]

    try:
        required_capabilities = tuple(json.loads(row["required_capabilities"]))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ExecutionSerializationError(
            f"Execution {execution_id!r}: 'required_capabilities' column is not valid JSON"
        ) from exc

    task = AgentTask(
        task_type=row["task_type"],
        description=row["task_description"],
        required_capabilities=required_capabilities,
        task_id=row["task_id"],
    )

    try:
        state = ExecutionState(row["state"])
    except ValueError as exc:
        raise ExecutionSerializationError(
            f"Execution {execution_id!r}: unrecognized state {row['state']!r}"
        ) from exc

    assigned_agent = None
    assigned_agent_name = row["assigned_agent_name"]
    if assigned_agent_name is not None:
        try:
            assigned_agent = registry.get_agent(assigned_agent_name)
        except AgentRegistryError as exc:
            raise ExecutionSerializationError(
                f"Execution {execution_id!r}: assigned_agent "
                f"{assigned_agent_name!r} not found in the current agent registry"
            ) from exc

    return AgentExecution(
        task=task,
        execution_id=execution_id,
        state=state,
        assigned_agent=assigned_agent,
        result=row["result"],
        error=row["error"],
        created_at=_parse_timestamp(row["created_at"], execution_id, "created_at"),
        updated_at=_parse_timestamp(row["updated_at"], execution_id, "updated_at"),
    )


def _parse_timestamp(raw: str, execution_id: str, column: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ExecutionSerializationError(
            f"Execution {execution_id!r}: column {column!r} is not a valid ISO 8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
