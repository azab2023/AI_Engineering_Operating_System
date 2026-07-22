"""
orchestrator.core
====================

The Orchestrator: receives tasks, selects a suitable agent, routes the
execution, and tracks execution state.

Scope note (Phase-04): this class performs SELECTION and STATE TRACKING
only. It does not invoke any agent CLI/API/subprocess -- there is no
execution backend yet (that is Phase-02/agent-adapter territory). Calling
`route()` transitions an execution from ASSIGNED to RUNNING to represent
"handed off for execution", but nothing external is actually called.

Selection strategy: deterministic, rule-based (per docs/architecture/
data-flow.md, which explicitly describes routing as a non-LLM-based
layer). An agent is eligible for a task if:
    1. its status is ACTIVE, and
    2. it supports the task's task_type, and
    3. it has every capability listed in task.required_capabilities.

Among eligible agents, the first one registered (registry insertion
order) is selected. This is intentionally simple; a scoring/priority
based strategy is a natural Phase-05+ extension and is not implemented
here to avoid speculative complexity.
"""

from __future__ import annotations

from orchestrator.exceptions import (
    AgentUnavailableError,
    NoSuitableAgentError,
    UnknownExecutionError,
)
from orchestrator.logging_setup import get_logger
from orchestrator.models import (
    Agent,
    AgentExecution,
    AgentStatus,
    AgentTask,
    ExecutionState,
)
from orchestrator.registry import AgentRegistry

logger = get_logger("core")


class Orchestrator:
    """Coordinates task submission, agent selection, and execution tracking.

    State is held in memory only for this phase (no persistence layer was
    requested). Each Orchestrator instance owns its own execution store.
    """

    def __init__(self, registry: AgentRegistry):
        self._registry = registry
        self._executions: dict[str, AgentExecution] = {}

    # ------------------------------------------------------------------ #
    # Public workflow
    # ------------------------------------------------------------------ #

    def submit_task(self, task: AgentTask) -> AgentExecution:
        """Register a new task and create its execution record (state=PENDING)."""
        execution = AgentExecution(task=task, state=ExecutionState.PENDING)
        self._executions[execution.execution_id] = execution
        logger.info(
            "Task submitted: task_id=%s task_type=%s execution_id=%s",
            task.task_id,
            task.task_type,
            execution.execution_id,
        )
        return execution

    def select_agent(self, task: AgentTask) -> Agent:
        """Select the best-matching active agent for a task.

        Raises:
            NoSuitableAgentError: no active agent supports the task_type
                and all required_capabilities.
        """
        candidates = self._registry.find_by_task(task.task_type)
        candidates = [
            agent
            for agent in candidates
            if all(agent.has_capability(cap) for cap in task.required_capabilities)
        ]
        active_candidates = [a for a in candidates if a.is_active()]

        if not active_candidates:
            if candidates:
                # Matched on capability/task but every match is inactive.
                inactive = candidates[0]
                raise AgentUnavailableError(inactive.name, inactive.status.value)
            raise NoSuitableAgentError(task.task_type, list(task.required_capabilities))

        selected = active_candidates[0]
        logger.info(
            "Agent selected: task_type=%s selected_agent=%s candidates=%s",
            task.task_type,
            selected.name,
            [a.name for a in active_candidates],
        )
        return selected

    def route(self, execution: AgentExecution) -> AgentExecution:
        """Assign an agent to the execution and mark it as routed (RUNNING).

        Does not invoke the agent. Transitions:
            PENDING -> (select agent) -> ASSIGNED -> RUNNING
        """
        if execution.execution_id not in self._executions:
            raise UnknownExecutionError(execution.execution_id)

        try:
            agent = self.select_agent(execution.task)
        except (NoSuitableAgentError, AgentUnavailableError) as exc:
            execution.state = ExecutionState.FAILED
            execution.error = str(exc)
            execution.touch()
            logger.warning(
                "Routing failed for execution_id=%s: %s", execution.execution_id, exc
            )
            raise

        execution.assigned_agent = agent
        execution.state = ExecutionState.ASSIGNED
        execution.touch()

        # No execution backend exists yet in this phase; we represent the
        # hand-off itself as reaching RUNNING, then immediately require
        # human approval before it can be considered COMPLETED, keeping
        # human-in-the-loop review structurally mandatory.
        execution.state = ExecutionState.RUNNING
        execution.touch()

        logger.info(
            "Execution routed: execution_id=%s agent=%s state=%s",
            execution.execution_id,
            agent.name,
            execution.state.value,
        )
        return execution

    def mark_awaiting_approval(self, execution_id: str, result: str) -> AgentExecution:
        """Mark a running execution as complete pending human approval."""
        execution = self.track(execution_id)
        execution.result = result
        execution.state = ExecutionState.AWAITING_APPROVAL
        execution.touch()
        logger.info("Execution awaiting approval: execution_id=%s", execution_id)
        return execution

    def approve(self, execution_id: str) -> AgentExecution:
        """Human approval step: AWAITING_APPROVAL -> COMPLETED."""
        execution = self.track(execution_id)
        execution.state = ExecutionState.COMPLETED
        execution.touch()
        logger.info("Execution approved and completed: execution_id=%s", execution_id)
        return execution

    def track(self, execution_id: str) -> AgentExecution:
        """Look up the current state of an execution by id."""
        try:
            return self._executions[execution_id]
        except KeyError as exc:
            raise UnknownExecutionError(execution_id) from exc

    def list_executions(self, state: ExecutionState | None = None) -> list[AgentExecution]:
        executions = list(self._executions.values())
        if state is not None:
            executions = [e for e in executions if e.state == state]
        return executions
