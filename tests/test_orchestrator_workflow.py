"""Unit tests for the end-to-end Orchestrator workflow (submit -> route -> track)."""

from __future__ import annotations

import pytest

from orchestrator.core import Orchestrator
from orchestrator.exceptions import NoSuitableAgentError, UnknownExecutionError
from orchestrator.models import AgentTask, ExecutionState
from orchestrator.registry import AgentRegistry, DEFAULT_REGISTRY_PATH


@pytest.fixture()
def orchestrator() -> Orchestrator:
    registry = AgentRegistry(DEFAULT_REGISTRY_PATH)
    return Orchestrator(registry)


def test_submit_task_creates_pending_execution(orchestrator: Orchestrator):
    task = AgentTask(task_type="code_generation", description="Write a CLI tool")
    execution = orchestrator.submit_task(task)

    assert execution.state == ExecutionState.PENDING
    assert execution.assigned_agent is None
    assert execution.task is task


def test_full_happy_path_workflow(orchestrator: Orchestrator):
    task = AgentTask(task_type="testing", description="Add unit tests for the parser module")
    execution = orchestrator.submit_task(task)

    routed = orchestrator.route(execution)
    assert routed.state == ExecutionState.RUNNING
    assert routed.assigned_agent is not None
    assert routed.assigned_agent.supports_task("testing")

    completed_pending_review = orchestrator.mark_awaiting_approval(
        routed.execution_id, result="Generated 12 test cases, all passing."
    )
    assert completed_pending_review.state == ExecutionState.AWAITING_APPROVAL
    assert completed_pending_review.result == "Generated 12 test cases, all passing."

    approved = orchestrator.approve(routed.execution_id)
    assert approved.state == ExecutionState.COMPLETED


def test_route_unroutable_task_marks_execution_failed(orchestrator: Orchestrator):
    task = AgentTask(task_type="nonexistent_task_type", description="Cannot be routed")
    execution = orchestrator.submit_task(task)

    with pytest.raises(NoSuitableAgentError):
        orchestrator.route(execution)

    tracked = orchestrator.track(execution.execution_id)
    assert tracked.state == ExecutionState.FAILED
    assert tracked.error is not None


def test_track_unknown_execution_raises(orchestrator: Orchestrator):
    with pytest.raises(UnknownExecutionError):
        orchestrator.track("00000000-0000-0000-0000-000000000000")


def test_route_unknown_execution_raises(orchestrator: Orchestrator):
    fake_task = AgentTask(task_type="code_generation", description="Not submitted")
    from orchestrator.models import AgentExecution

    fake_execution = AgentExecution(task=fake_task)  # never submitted to this orchestrator

    with pytest.raises(UnknownExecutionError):
        orchestrator.route(fake_execution)


def test_list_executions_filters_by_state(orchestrator: Orchestrator):
    task_a = AgentTask(task_type="code_generation", description="Task A")
    task_b = AgentTask(task_type="nonexistent_task_type", description="Task B, will fail")

    exec_a = orchestrator.submit_task(task_a)
    exec_b = orchestrator.submit_task(task_b)

    orchestrator.route(exec_a)
    with pytest.raises(NoSuitableAgentError):
        orchestrator.route(exec_b)

    running = orchestrator.list_executions(state=ExecutionState.RUNNING)
    failed = orchestrator.list_executions(state=ExecutionState.FAILED)

    assert [e.execution_id for e in running] == [exec_a.execution_id]
    assert [e.execution_id for e in failed] == [exec_b.execution_id]

    all_executions = orchestrator.list_executions()
    assert len(all_executions) == 2


def test_multiple_tasks_get_independent_executions(orchestrator: Orchestrator):
    task1 = AgentTask(task_type="debugging", description="Bug 1")
    task2 = AgentTask(task_type="debugging", description="Bug 2")

    exec1 = orchestrator.submit_task(task1)
    exec2 = orchestrator.submit_task(task2)

    assert exec1.execution_id != exec2.execution_id
    assert exec1.task.task_id != exec2.task.task_id
