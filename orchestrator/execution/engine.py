"""
orchestrator.execution.engine
================================

``ExecutionEngine``: the Phase-06 Agent Execution Engine.

Scope: this is the layer that makes ``Orchestrator.route()``'s RUNNING
state mean something. It takes an execution that has been (or can be)
routed, actually invokes the assigned agent via an injected
``AgentInvoker``, retries transient failures per an injected
``RetryPolicy``, and records the final outcome back through
``Orchestrator`` -- ``mark_awaiting_approval`` on success,
``mark_failed`` once retries are exhausted -- so persistence (Phase-05)
and the human-in-the-loop approval gate (Phase-04) apply to executed
results exactly as they already do to everything else in the state
machine. See ADR-0004.
"""

from __future__ import annotations

import time

from orchestrator.core import Orchestrator
from orchestrator.exceptions import (
    AgentInvocationError,
    AgentTimeoutError,
    AgentUnavailableError,
    InvalidStateTransitionError,
    MaxRetriesExceededError,
    NoSuitableAgentError,
)
from orchestrator.execution.invoker import AgentInvoker
from orchestrator.execution.models import RetryPolicy
from orchestrator.logging_setup import get_logger
from orchestrator.models import AgentExecution, ExecutionState

logger = get_logger("execution.engine")


class ExecutionEngine:
    """Drives one ``AgentExecution`` from routing through to a recorded
    final outcome, retrying transient agent-invocation failures.

    Args:
        orchestrator: used for routing (if needed) and to record the
            final outcome (``mark_awaiting_approval`` / ``mark_failed``).
        invoker: the ``AgentInvoker`` used to actually run the assigned
            agent. Defaults to ``SubprocessAgentInvoker()`` when not
            given.
        retry_policy: retry/backoff behavior for transient failures.
            Defaults to ``RetryPolicy()`` (3 attempts, exponential
            backoff) when not given.
    """

    def __init__(
        self,
        orchestrator: Orchestrator,
        invoker: AgentInvoker | None = None,
        retry_policy: RetryPolicy | None = None,
    ):
        if invoker is None:
            # Imported lazily so constructing an ExecutionEngine with an
            # explicit test invoker never requires config/agent_commands.yaml
            # to exist or be parsed.
            from orchestrator.execution.invoker import SubprocessAgentInvoker

            invoker = SubprocessAgentInvoker()
        self._orchestrator = orchestrator
        self._invoker = invoker
        self._retry_policy = retry_policy or RetryPolicy()

    def execute(self, execution: AgentExecution) -> AgentExecution:
        """Route (if needed), invoke, retry, and record the outcome of
        ``execution``.

        If ``execution`` is PENDING it is routed first via
        ``Orchestrator.route()``; a routing failure (no suitable/available
        agent) is returned as-is (already FAILED by ``route()``) rather
        than raised, so callers can branch on ``execution.state`` uniformly
        regardless of whether routing or invocation failed.

        Raises:
            InvalidStateTransitionError: ``execution`` is in a state from
                which it cannot be executed (e.g. already COMPLETED).
        """
        if execution.state == ExecutionState.PENDING:
            try:
                execution = self._orchestrator.route(execution)
            except (NoSuitableAgentError, AgentUnavailableError):
                # route() already transitioned this execution to FAILED and
                # persisted it; return that recorded state instead of
                # raising, so callers can branch on execution.state
                # uniformly regardless of whether routing or invocation
                # failed.
                return self._orchestrator.track(execution.execution_id)

        if execution.state != ExecutionState.RUNNING:
            raise InvalidStateTransitionError(
                execution.execution_id,
                action="execute",
                expected_state=ExecutionState.RUNNING.value,
                actual_state=execution.state.value,
            )

        agent = execution.assigned_agent
        assert agent is not None, "RUNNING execution must have an assigned_agent"

        last_error_message = "unknown error"
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            delay = self._retry_policy.backoff_seconds(attempt)
            if delay:
                time.sleep(delay)

            try:
                result = self._invoker.invoke(agent, execution.task)
            except (AgentTimeoutError, AgentInvocationError) as exc:
                last_error_message = str(exc)
                logger.warning(
                    "Invocation attempt %d/%d failed for execution_id=%s: %s",
                    attempt,
                    self._retry_policy.max_attempts,
                    execution.execution_id,
                    exc,
                )
                continue

            if result.succeeded():
                return self._orchestrator.mark_awaiting_approval(
                    execution.execution_id, result=result.output
                )

            last_error_message = (
                f"agent exited with code {result.exit_code}: {result.output.strip()}"
            )
            logger.warning(
                "Invocation attempt %d/%d for execution_id=%s: %s",
                attempt,
                self._retry_policy.max_attempts,
                execution.execution_id,
                last_error_message,
            )

        exhausted = MaxRetriesExceededError(
            agent.name, self._retry_policy.max_attempts, last_error_message
        )
        return self._orchestrator.mark_failed(execution.execution_id, error=str(exhausted))
