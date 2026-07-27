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

Among eligible agents, the one with the highest AgentPriority (high >
medium > low) is selected. Ties within the same priority are broken by
registry insertion order (stable sort), which was the sole ordering rule
prior to the Phase-04 patch release. A further scoring strategy beyond
priority is a natural Phase-05+ extension and is not implemented here to
avoid speculative complexity.

State transitions (route/mark_awaiting_approval/approve) are guarded:
each method only accepts an execution in the specific prior state it is
meant to follow, and raises InvalidStateTransitionError otherwise. This
was added in the Phase-04 patch release to close a gap where, e.g.,
approve() could previously be called on an execution that had never been
routed.

Persistence (Phase-05): execution storage is delegated to an
``ExecutionRepository`` (see ``orchestrator.persistence``) instead of a
hard-coded dict. Every method that used to mutate ``self._executions``
directly now also calls ``self._repository.update(execution)`` right
after mutating the execution, so state changes are durable when a
persistent repository (e.g. ``SqliteExecutionRepository``) is supplied.
When no repository is supplied, ``InMemoryExecutionRepository`` is used,
which reproduces Phase-04's exact in-memory-only behavior -- see
ADR-0003 for why this keeps existing callers unaffected.
"""

from __future__ import annotations

from orchestrator.exceptions import (
    AgentUnavailableError,
    InvalidStateTransitionError,
    NoSuitableAgentError,
    UnknownExecutionError,
)
from orchestrator.logging_setup import get_logger
from orchestrator.models import (
    Agent,
    AgentExecution,
    AgentPriority,
    AgentTask,
    ExecutionState,
)
from orchestrator.observability.models import MetricPoint, ObservabilityEvent
from orchestrator.observability.recorder import ObservabilityRecorder
from orchestrator.persistence.repository import (
    ExecutionRepository,
    InMemoryExecutionRepository,
)
from orchestrator.registry import AgentRegistry

logger = get_logger("core")

# Lower rank = higher priority. Used to sort eligible agents deterministically;
# ties (equal priority) preserve registry insertion order via a stable sort.
_PRIORITY_RANK: dict[AgentPriority, int] = {
    AgentPriority.HIGH: 0,
    AgentPriority.MEDIUM: 1,
    AgentPriority.LOW: 2,
}


class Orchestrator:
    """Coordinates task submission, agent selection, and execution tracking.

    Args:
        registry: the agent registry used for selection.
        repository: where execution records are stored. Defaults to
            ``InMemoryExecutionRepository()`` (Phase-04 behavior: state
            lives only for the lifetime of the process) when not given.
            Pass a ``SqliteExecutionRepository`` for durable, cross-restart
            execution history.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        repository: ExecutionRepository | None = None,
        observer: ObservabilityRecorder | None = None,
    ):
        self._registry = registry
        self._repository = repository if repository is not None else InMemoryExecutionRepository()
        self._observer = observer

    # ------------------------------------------------------------------ #
    # Phase-13 (ADR-0011) observability helper
    # ------------------------------------------------------------------ #

    def _observe_event(self, event_type: str, **attributes: str) -> None:
        if self._observer is None:
            return
        self._observer.record_event(
            ObservabilityEvent(
                component="orchestrator", event_type=event_type, attributes=attributes
            )
        )

    def _observe_metric(self, name: str, value: float, metric_type: str, **tags: str) -> None:
        if self._observer is None:
            return
        self._observer.record_metric(
            MetricPoint(name=name, value=value, metric_type=metric_type, tags=tags)
        )

    # ------------------------------------------------------------------ #
    # Public workflow
    # ------------------------------------------------------------------ #

    def submit_task(self, task: AgentTask) -> AgentExecution:
        """Register a new task and create its execution record (state=PENDING)."""
        execution = AgentExecution(task=task, state=ExecutionState.PENDING)
        self._repository.add(execution)
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

        # Stable sort: agents are ordered by priority (high first); agents
        # sharing the same priority keep their original registry order.
        ranked_candidates = sorted(
            active_candidates, key=lambda agent: _PRIORITY_RANK[agent.priority]
        )
        selected = ranked_candidates[0]
        logger.info(
            "Agent selected: task_type=%s selected_agent=%s (priority=%s) candidates=%s",
            task.task_type,
            selected.name,
            selected.priority.value,
            [(a.name, a.priority.value) for a in ranked_candidates],
        )
        return selected

    def route(self, execution: AgentExecution) -> AgentExecution:
        """Assign an agent to the execution and mark it as routed (RUNNING).

        Does not invoke the agent. Transitions:
            PENDING -> (select agent) -> ASSIGNED -> RUNNING
        """
        if execution.execution_id not in self._repository:
            raise UnknownExecutionError(execution.execution_id)

        if execution.state != ExecutionState.PENDING:
            raise InvalidStateTransitionError(
                execution.execution_id,
                action="route",
                expected_state=ExecutionState.PENDING.value,
                actual_state=execution.state.value,
            )

        try:
            agent = self.select_agent(execution.task)
        except (NoSuitableAgentError, AgentUnavailableError) as exc:
            execution.state = ExecutionState.FAILED
            execution.error = str(exc)
            execution.touch()
            self._repository.update(execution)
            logger.warning("Routing failed for execution_id=%s: %s", execution.execution_id, exc)
            self._observe_event(
                "route_failed", execution_id=execution.execution_id, reason=str(exc)
            )
            self._observe_metric("orchestrator.routes_total", 1, "counter", outcome="failed")
            raise

        execution.assigned_agent = agent
        execution.state = ExecutionState.ASSIGNED
        execution.touch()
        self._repository.update(execution)

        # No execution backend exists yet in this phase; we represent the
        # hand-off itself as reaching RUNNING, then immediately require
        # human approval before it can be considered COMPLETED, keeping
        # human-in-the-loop review structurally mandatory.
        execution.state = ExecutionState.RUNNING
        execution.touch()
        self._repository.update(execution)

        logger.info(
            "Execution routed: execution_id=%s agent=%s state=%s",
            execution.execution_id,
            agent.name,
            execution.state.value,
        )
        self._observe_event(
            "task_routed", execution_id=execution.execution_id, agent_name=agent.name
        )
        self._observe_metric("orchestrator.routes_total", 1, "counter", outcome="success")
        return execution

    def mark_awaiting_approval(self, execution_id: str, result: str) -> AgentExecution:
        """Mark a running execution as complete pending human approval.

        Only valid from RUNNING; raises InvalidStateTransitionError otherwise.
        """
        execution = self.track(execution_id)
        if execution.state != ExecutionState.RUNNING:
            raise InvalidStateTransitionError(
                execution_id,
                action="mark_awaiting_approval",
                expected_state=ExecutionState.RUNNING.value,
                actual_state=execution.state.value,
            )
        execution.result = result
        execution.state = ExecutionState.AWAITING_APPROVAL
        execution.touch()
        self._repository.update(execution)
        logger.info("Execution awaiting approval: execution_id=%s", execution_id)
        self._observe_event("execution_awaiting_approval", execution_id=execution_id)
        return execution

    def approve(self, execution_id: str) -> AgentExecution:
        """Human approval step: AWAITING_APPROVAL -> COMPLETED.

        Only valid from AWAITING_APPROVAL; raises InvalidStateTransitionError
        otherwise. This is the sole path to COMPLETED, so an execution can
        only be completed after having actually been routed to an agent and
        produced a result awaiting review.
        """
        execution = self.track(execution_id)
        if execution.state != ExecutionState.AWAITING_APPROVAL:
            raise InvalidStateTransitionError(
                execution_id,
                action="approve",
                expected_state=ExecutionState.AWAITING_APPROVAL.value,
                actual_state=execution.state.value,
            )
        execution.state = ExecutionState.COMPLETED
        execution.touch()
        self._repository.update(execution)
        logger.info("Execution approved and completed: execution_id=%s", execution_id)
        self._observe_event("execution_approved", execution_id=execution_id)
        return execution

    def mark_failed(self, execution_id: str, error: str) -> AgentExecution:
        """Mark a running execution as failed.

        Used by ``orchestrator.execution.ExecutionEngine`` (Phase-06) once
        an agent invocation has exhausted its retries, so a failed run is
        recorded with the same rigor as a successful one instead of being
        left stuck in RUNNING. Only valid from RUNNING; raises
        InvalidStateTransitionError otherwise.
        """
        execution = self.track(execution_id)
        if execution.state != ExecutionState.RUNNING:
            raise InvalidStateTransitionError(
                execution_id,
                action="mark_failed",
                expected_state=ExecutionState.RUNNING.value,
                actual_state=execution.state.value,
            )
        execution.error = error
        execution.state = ExecutionState.FAILED
        execution.touch()
        self._repository.update(execution)
        logger.warning("Execution failed: execution_id=%s error=%s", execution_id, error)
        self._observe_event("execution_failed", execution_id=execution_id, error=error)
        return execution

    def track(self, execution_id: str) -> AgentExecution:
        """Look up the current state of an execution by id."""
        return self._repository.get(execution_id)

    def list_executions(self, state: ExecutionState | None = None) -> list[AgentExecution]:
        return self._repository.list(state)
