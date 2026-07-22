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
        super().__init__(
            f"Agent {agent_name!r} matched but is not active (status={status!r})"
        )


class UnknownExecutionError(OrchestratorError):
    """Raised when an execution_id is not found in the orchestrator's state store."""

    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        super().__init__(f"No execution found with id={execution_id!r}")


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
