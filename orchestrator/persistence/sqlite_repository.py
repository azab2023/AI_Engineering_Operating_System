"""
orchestrator.persistence.sqlite_repository
=============================================

``SqliteExecutionRepository``: the persistent ``ExecutionRepository``
implementation backed by SQLite.

Concurrency note:
    A single connection is opened once, at construction, and reused for
    the repository's lifetime (``close()`` releases it). SQLite's own
    file-level locking, combined with WAL mode (see ``db.connect``), is
    sufficient for the single-process usage this phase targets; nothing
    here attempts multi-process write coordination.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from orchestrator.exceptions import ExecutionAlreadyExistsError, UnknownExecutionError
from orchestrator.logging_setup import get_logger
from orchestrator.models import AgentExecution, ExecutionState
from orchestrator.persistence.db import DEFAULT_SQLITE_PATH, connect
from orchestrator.persistence.repository import ExecutionRepository
from orchestrator.persistence.serializers import execution_to_row, row_to_execution
from orchestrator.registry import AgentRegistry

logger = get_logger("persistence.sqlite")

_INSERT_SQL = """
INSERT INTO executions (
    execution_id, task_id, task_type, task_description,
    required_capabilities, state, assigned_agent_name, result, error,
    created_at, updated_at
) VALUES (
    :execution_id, :task_id, :task_type, :task_description,
    :required_capabilities, :state, :assigned_agent_name, :result, :error,
    :created_at, :updated_at
);
"""

_UPDATE_SQL = """
UPDATE executions SET
    task_id = :task_id,
    task_type = :task_type,
    task_description = :task_description,
    required_capabilities = :required_capabilities,
    state = :state,
    assigned_agent_name = :assigned_agent_name,
    result = :result,
    error = :error,
    created_at = :created_at,
    updated_at = :updated_at
WHERE execution_id = :execution_id;
"""

_SELECT_ONE_SQL = "SELECT * FROM executions WHERE execution_id = ?;"
_SELECT_ALL_SQL = "SELECT * FROM executions;"
_SELECT_BY_STATE_SQL = "SELECT * FROM executions WHERE state = ?;"


class SqliteExecutionRepository(ExecutionRepository):
    """SQLite-backed ``ExecutionRepository``.

    Args:
        registry: the ``AgentRegistry`` used to resolve an execution's
            ``assigned_agent`` (stored as a name) back into a full
            ``Agent`` object when reading rows back out of SQLite.
        db_path: path to the SQLite database file. Defaults to
            ``data/aeos.db`` at the repository root. Pass ``":memory:"``
            for an ephemeral, test-only database.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        db_path: str | Path = DEFAULT_SQLITE_PATH,
    ) -> None:
        self._registry = registry
        self._db_path = db_path
        self._conn: sqlite3.Connection = connect(db_path)
        logger.info("SqliteExecutionRepository connected: db_path=%s", db_path)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteExecutionRepository:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # ExecutionRepository interface
    # ------------------------------------------------------------------ #

    def add(self, execution: AgentExecution) -> None:
        row = execution_to_row(execution)
        try:
            with self._conn:
                self._conn.execute(_INSERT_SQL, row)
        except sqlite3.IntegrityError as exc:
            raise ExecutionAlreadyExistsError(execution.execution_id) from exc

    def update(self, execution: AgentExecution) -> None:
        row = execution_to_row(execution)
        with self._conn:
            cursor = self._conn.execute(_UPDATE_SQL, row)
        if cursor.rowcount == 0:
            raise UnknownExecutionError(execution.execution_id)

    def get(self, execution_id: str) -> AgentExecution:
        cursor = self._conn.execute(_SELECT_ONE_SQL, (execution_id,))
        row = cursor.fetchone()
        if row is None:
            raise UnknownExecutionError(execution_id)
        return row_to_execution(row, self._registry)

    def list(self, state: ExecutionState | None = None) -> list[AgentExecution]:
        if state is None:
            cursor = self._conn.execute(_SELECT_ALL_SQL)
        else:
            cursor = self._conn.execute(_SELECT_BY_STATE_SQL, (state.value,))
        return [row_to_execution(row, self._registry) for row in cursor.fetchall()]
