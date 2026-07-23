"""Unit tests for orchestrator.execution.engine.ExecutionEngine.

Uses a FakeAgentInvoker test double (implementing the AgentInvoker
protocol) so these tests never spawn real subprocesses -- see
test_execution_invoker.py for SubprocessAgentInvoker-specific coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from orchestrator.core import Orchestrator
from orchestrator.exceptions import AgentTimeoutError, InvalidStateTransitionError
from orchestrator.execution.engine import ExecutionEngine
from orchestrator.execution.models import ExecutionResult, RetryPolicy
from orchestrator.models import Agent, AgentTask, ExecutionState
from orchestrator.registry import DEFAULT_REGISTRY_PATH, AgentRegistry


@dataclass
class FakeAgentInvoker:
    """Test double for AgentInvoker: replays a scripted sequence of
    results/exceptions, one per call, and records every (agent, task) it
    was called with."""

    outcomes: list
    calls: list = field(default_factory=list)

    def invoke(self, agent: Agent, task: AgentTask) -> ExecutionResult:
        self.calls.append((agent, task))
        outcome = self.outcomes[len(self.calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


NO_DELAY = RetryPolicy(max_attempts=3, initial_backoff_seconds=0)


@pytest.fixture
def orchestrator() -> Orchestrator:
    return Orchestrator(AgentRegistry(DEFAULT_REGISTRY_PATH))


def test_execute_routes_pending_execution_and_succeeds(orchestrator: Orchestrator):
    task = AgentTask(task_type="testing", description="write unit tests")
    execution = orchestrator.submit_task(task)
    assert execution.state == ExecutionState.PENDING

    invoker = FakeAgentInvoker(
        [ExecutionResult(output="12 tests passed", exit_code=0, duration_seconds=0.1)]
    )
    engine = ExecutionEngine(orchestrator, invoker=invoker, retry_policy=NO_DELAY)

    result = engine.execute(execution)

    assert result.state == ExecutionState.AWAITING_APPROVAL
    assert result.result == "12 tests passed"
    assert len(invoker.calls) == 1


def test_execute_retries_transient_failure_then_succeeds(orchestrator: Orchestrator):
    task = AgentTask(task_type="testing", description="flaky task")
    execution = orchestrator.submit_task(task)

    invoker = FakeAgentInvoker(
        [
            ExecutionResult(output="error", exit_code=1, duration_seconds=0.1),
            ExecutionResult(output="ok", exit_code=0, duration_seconds=0.1),
        ]
    )
    engine = ExecutionEngine(orchestrator, invoker=invoker, retry_policy=NO_DELAY)

    result = engine.execute(execution)

    assert result.state == ExecutionState.AWAITING_APPROVAL
    assert result.result == "ok"
    assert len(invoker.calls) == 2


def test_execute_retries_on_timeout_then_succeeds(orchestrator: Orchestrator):
    task = AgentTask(task_type="testing", description="slow then fast")
    execution = orchestrator.submit_task(task)

    invoker = FakeAgentInvoker(
        [
            AgentTimeoutError("codex", 300.0),
            ExecutionResult(output="ok", exit_code=0, duration_seconds=0.1),
        ]
    )
    engine = ExecutionEngine(orchestrator, invoker=invoker, retry_policy=NO_DELAY)

    result = engine.execute(execution)

    assert result.state == ExecutionState.AWAITING_APPROVAL
    assert len(invoker.calls) == 2


def test_execute_exhausts_retries_and_marks_failed(orchestrator: Orchestrator):
    task = AgentTask(task_type="testing", description="always fails")
    execution = orchestrator.submit_task(task)

    invoker = FakeAgentInvoker(
        [ExecutionResult(output="nope", exit_code=1, duration_seconds=0.1) for _ in range(2)]
    )
    engine = ExecutionEngine(
        orchestrator,
        invoker=invoker,
        retry_policy=RetryPolicy(max_attempts=2, initial_backoff_seconds=0),
    )

    result = engine.execute(execution)

    assert result.state == ExecutionState.FAILED
    assert result.error is not None
    assert "2 attempt" in result.error
    assert len(invoker.calls) == 2


def test_execute_no_suitable_agent_returns_failed_without_raising(orchestrator: Orchestrator):
    task = AgentTask(task_type="no_such_task_type", description="nope")
    execution = orchestrator.submit_task(task)

    invoker = FakeAgentInvoker([])
    engine = ExecutionEngine(orchestrator, invoker=invoker, retry_policy=NO_DELAY)

    result = engine.execute(execution)

    assert result.state == ExecutionState.FAILED
    assert invoker.calls == []


def test_execute_already_completed_execution_raises(orchestrator: Orchestrator):
    task = AgentTask(task_type="testing", description="x")
    execution = orchestrator.submit_task(task)
    routed = orchestrator.route(execution)
    orchestrator.mark_awaiting_approval(routed.execution_id, result="done")
    completed = orchestrator.approve(routed.execution_id)
    assert completed.state == ExecutionState.COMPLETED

    invoker = FakeAgentInvoker([])
    engine = ExecutionEngine(orchestrator, invoker=invoker, retry_policy=NO_DELAY)

    with pytest.raises(InvalidStateTransitionError):
        engine.execute(completed)


def test_execute_uses_default_subprocess_invoker_when_none_given(orchestrator: Orchestrator):
    # No invoker passed -> must not raise at construction time, and must
    # lazily build a SubprocessAgentInvoker (which loads the real,
    # shipped config/agent_commands.yaml).
    engine = ExecutionEngine(orchestrator)
    from orchestrator.execution.invoker import SubprocessAgentInvoker

    assert isinstance(engine._invoker, SubprocessAgentInvoker)


def test_retry_policy_backoff_seconds_exponential():
    policy = RetryPolicy(max_attempts=4, initial_backoff_seconds=1.0, backoff_multiplier=2.0)
    assert policy.backoff_seconds(1) == 0.0
    assert policy.backoff_seconds(2) == 1.0
    assert policy.backoff_seconds(3) == 2.0
    assert policy.backoff_seconds(4) == 4.0


def test_retry_policy_rejects_invalid_values():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError):
        RetryPolicy(initial_backoff_seconds=-1)
    with pytest.raises(ValueError):
        RetryPolicy(backoff_multiplier=0.5)
