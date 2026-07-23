"""
orchestrator.exceptions
========================

Custom exception hierarchy for the orchestration layer.

Rationale: silent failures / permissive fallbacks are what caused the
prompt_registry.yaml corruption discovered before this phase (a duplicate
top-level key was silently overridden by PyYAML instead of raising).
This package prefers to fail loudly and specifically instead.
"""

from __future__ import annotations


class OrchestratorError(Exception):
    """Base class for all orchestrator-related errors."""


class AgentRegistryError(OrchestratorError):
    """Raised when the agent registry cannot be loaded or fails validation."""


class NoSuitableAgentError(OrchestratorError):
    """Raised when no registered agent matches a task's requirements."""

    def __init__(self, task_type: str, required_capabilities: list[str]):
        self.task_type = task_type
        self.required_capabilities = required_capabilities
        super().__init__(
            f"No suitable agent found for task_type={task_type!r} "
            f"with required_capabilities={required_capabilities!r}"
        )


class AgentUnavailableError(OrchestratorError):
    """Raised when a matched agent's status is not 'active'."""

    def __init__(self, agent_name: str, status: str):
        self.agent_name = agent_name
        self.status = status
        super().__init__(f"Agent {agent_name!r} matched but is not active (status={status!r})")


class UnknownExecutionError(OrchestratorError):
    """Raised when an execution_id is not found in the orchestrator's state store."""

    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        super().__init__(f"No execution found with id={execution_id!r}")


class PersistenceError(OrchestratorError):
    """Base class for all Phase-05 persistence-layer errors.

    Raised for failures in the storage backend itself (schema
    initialization, connection, read/write corruption) as distinct from
    ``AgentRegistryError`` (config loading) or the execution-state errors
    below, which are orchestration-logic errors, not storage errors.
    """


class ExecutionAlreadyExistsError(PersistenceError):
    """Raised when adding an execution whose execution_id is already stored."""

    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        super().__init__(f"Execution already exists with id={execution_id!r}")


class ExecutionSerializationError(PersistenceError):
    """Raised when an ``AgentExecution`` cannot be serialized to, or
    reconstructed from, a persistence backend's stored representation
    (e.g. an unknown ``state``/``priority`` value in a SQLite row, or a
    reference to an ``assigned_agent`` no longer present in the current
    agent registry)."""


class ExecutionEngineError(OrchestratorError):
    """Base class for all Phase-06 agent-execution-engine errors.

    Distinct from ``PersistenceError`` (storage failures) and the
    orchestration-logic errors above (selection/state-transition
    failures) -- these errors originate from actually invoking an
    agent's CLI, not from deciding which agent to use or tracking state.
    """


class AgentCommandNotConfiguredError(ExecutionEngineError):
    """Raised when an agent has no invocation command registered in
    ``config/agent_commands.yaml``."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        super().__init__(f"No invocation command configured for agent {agent_name!r}")


class AgentCommandRegistryError(ExecutionEngineError):
    """Raised when ``config/agent_commands.yaml`` cannot be loaded or fails
    validation. Mirrors ``AgentRegistryError``'s fail-loudly philosophy."""


class AgentInvocationError(ExecutionEngineError):
    """Raised when an agent's CLI could not be started at all (e.g. the
    executable is missing from PATH), as distinct from the CLI running
    and exiting non-zero, which is reported via ``ExecutionResult`` and
    handled as a retryable failure by ``ExecutionEngine`` instead."""

    def __init__(self, agent_name: str, reason: str):
        self.agent_name = agent_name
        self.reason = reason
        super().__init__(f"Failed to invoke agent {agent_name!r}: {reason}")


class AgentTimeoutError(ExecutionEngineError):
    """Raised when an agent's CLI does not complete within its configured
    timeout. Treated as retryable by ``ExecutionEngine``."""

    def __init__(self, agent_name: str, timeout_seconds: float):
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Agent {agent_name!r} timed out after {timeout_seconds}s")


class MaxRetriesExceededError(ExecutionEngineError):
    """Raised internally when every retry attempt for an execution has
    been exhausted. ``ExecutionEngine`` catches this and transitions the
    execution to ``FAILED`` via ``Orchestrator.mark_failed`` rather than
    letting it propagate."""

    def __init__(self, agent_name: str, attempts: int, last_error: str):
        self.agent_name = agent_name
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Agent {agent_name!r} failed after {attempts} attempt(s): {last_error}")


class InvalidStateTransitionError(OrchestratorError):
    """Raised when an orchestrator method is called on an execution whose
    current state does not permit that action.

    Patch note: this exception closes a gap where route()/mark_awaiting_
    approval()/approve() previously performed their state transition
    unconditionally, regardless of the execution's current state -- which
    made it possible to call approve() on an execution that had never
    been routed, reaching COMPLETED with no assigned agent and no human
    review having actually occurred.
    """

    def __init__(self, execution_id: str, action: str, expected_state: str, actual_state: str):
        self.execution_id = execution_id
        self.action = action
        self.expected_state = expected_state
        self.actual_state = actual_state
        super().__init__(
            f"Cannot {action} execution {execution_id!r}: requires state "
            f"{expected_state!r}, but current state is {actual_state!r}"
        )
