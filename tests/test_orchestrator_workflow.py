"""Unit tests for the end-to-end Orchestrator workflow (submit -> route -> track).

Phase-05: this suite is parametrized over both ``ExecutionRepository``
backends (``InMemoryExecutionRepository`` and, with an in-memory SQLite
database, ``SqliteExecutionRepository``) so the entire Phase-04 workflow
is verified to behave identically regardless of which backend
``Orchestrator`` is constructed with. This is the primary backward-
compatibility regression check for Phase-05: everything that passed
against the dict-backed store in Phase-04 must still pass, unmodified,
against the SQLite-backed store.
"""

from __future__ import annotations

import pytest

from orchestrator.core import Orchestrator
from orchestrator.exceptions import (
    InvalidStateTransitionError,
    NoSuitableAgentError,
    UnknownExecutionError,
)
from orchestrator.models import AgentExecution, AgentTask, ExecutionState
from orchestrator.persistence import InMemoryExecutionRepository, SqliteExecutionRepository
from orchestrator.registry import DEFAULT_REGISTRY_PATH, AgentRegistry


@pytest.fixture(params=["in_memory", "sqlite"])
def orchestrator(request: pytest.FixtureRequest) -> Orchestrator:
    registry = AgentRegistry(DEFAULT_REGISTRY_PATH)
    if request.param == "sqlite":
        repository = SqliteExecutionRepository(registry, db_path=":memory:")
        request.addfinalizer(repository.close)
    else:
        repository = InMemoryExecutionRepository()
    return Orchestrator(registry, repository=repository)


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


# --------------------------------------------------------------------- #
# Illegal state transitions (Phase-04 patch release)
#
# Prior to this patch, approve() and mark_awaiting_approval() performed
# their transition unconditionally regardless of current state -- e.g.
# approve() could be called on a freshly-submitted (PENDING) execution,
# reaching COMPLETED with no agent ever assigned and no actual review
# result. Each test below drives an execution into a specific state and
# then asserts that every action NOT meant to follow from that state is
# rejected with InvalidStateTransitionError, and that the execution's
# state is left unchanged by the rejected call.
# --------------------------------------------------------------------- #


def _routable_task() -> AgentTask:
    return AgentTask(task_type="code_generation", description="Illegal-transition fixture task")


def test_approve_rejected_when_pending(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    assert execution.state == ExecutionState.PENDING

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        orchestrator.approve(execution.execution_id)

    assert exc_info.value.expected_state == ExecutionState.AWAITING_APPROVAL.value
    assert exc_info.value.actual_state == ExecutionState.PENDING.value
    assert orchestrator.track(execution.execution_id).state == ExecutionState.PENDING
    assert orchestrator.track(execution.execution_id).assigned_agent is None


def test_approve_rejected_when_running(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    orchestrator.route(execution)
    assert execution.state == ExecutionState.RUNNING

    with pytest.raises(InvalidStateTransitionError):
        orchestrator.approve(execution.execution_id)

    assert orchestrator.track(execution.execution_id).state == ExecutionState.RUNNING


def test_approve_rejected_when_already_completed(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    orchestrator.route(execution)
    orchestrator.mark_awaiting_approval(execution.execution_id, result="done")
    orchestrator.approve(execution.execution_id)
    # Read back via track() rather than asserting on the local `execution`
    # reference: mark_awaiting_approval()/approve() mutate the object
    # returned by an internal track() call, not necessarily the caller's
    # original reference. InMemoryExecutionRepository happens to return
    # the same object every time (so both would pass), but
    # SqliteExecutionRepository deserializes a fresh object on each read,
    # so only track() reflects the current, authoritative state
    # regardless of backend.
    assert orchestrator.track(execution.execution_id).state == ExecutionState.COMPLETED

    with pytest.raises(InvalidStateTransitionError):
        orchestrator.approve(execution.execution_id)  # double-approve

    assert orchestrator.track(execution.execution_id).state == ExecutionState.COMPLETED


def test_approve_rejected_when_failed(orchestrator: Orchestrator):
    task = AgentTask(task_type="nonexistent_task_type", description="Will fail to route")
    execution = orchestrator.submit_task(task)
    with pytest.raises(NoSuitableAgentError):
        orchestrator.route(execution)
    assert execution.state == ExecutionState.FAILED

    with pytest.raises(InvalidStateTransitionError):
        orchestrator.approve(execution.execution_id)

    assert orchestrator.track(execution.execution_id).state == ExecutionState.FAILED


def test_mark_awaiting_approval_rejected_when_pending(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    assert execution.state == ExecutionState.PENDING

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        orchestrator.mark_awaiting_approval(execution.execution_id, result="premature")

    assert exc_info.value.expected_state == ExecutionState.RUNNING.value
    assert exc_info.value.actual_state == ExecutionState.PENDING.value
    tracked = orchestrator.track(execution.execution_id)
    assert tracked.state == ExecutionState.PENDING
    assert tracked.result is None


def test_mark_awaiting_approval_rejected_when_already_awaiting_approval(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    orchestrator.route(execution)
    orchestrator.mark_awaiting_approval(execution.execution_id, result="first result")

    with pytest.raises(InvalidStateTransitionError):
        orchestrator.mark_awaiting_approval(execution.execution_id, result="second result")

    # Original result must be untouched by the rejected call.
    assert orchestrator.track(execution.execution_id).result == "first result"


def test_mark_awaiting_approval_rejected_when_completed(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    orchestrator.route(execution)
    orchestrator.mark_awaiting_approval(execution.execution_id, result="done")
    orchestrator.approve(execution.execution_id)

    with pytest.raises(InvalidStateTransitionError):
        orchestrator.mark_awaiting_approval(execution.execution_id, result="too late")

    assert orchestrator.track(execution.execution_id).state == ExecutionState.COMPLETED


def test_mark_awaiting_approval_rejected_when_failed(orchestrator: Orchestrator):
    task = AgentTask(task_type="nonexistent_task_type", description="Will fail to route")
    execution = orchestrator.submit_task(task)
    with pytest.raises(NoSuitableAgentError):
        orchestrator.route(execution)

    with pytest.raises(InvalidStateTransitionError):
        orchestrator.mark_awaiting_approval(execution.execution_id, result="irrelevant")

    assert orchestrator.track(execution.execution_id).state == ExecutionState.FAILED


def test_route_rejected_when_already_running(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    orchestrator.route(execution)
    assert execution.state == ExecutionState.RUNNING
    first_agent = execution.assigned_agent

    with pytest.raises(InvalidStateTransitionError):
        orchestrator.route(execution)

    # Re-routing must not silently reassign a different agent.
    assert orchestrator.track(execution.execution_id).assigned_agent is first_agent


def test_route_rejected_when_awaiting_approval(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    orchestrator.route(execution)
    orchestrator.mark_awaiting_approval(execution.execution_id, result="done")

    with pytest.raises(InvalidStateTransitionError):
        orchestrator.route(execution)

    assert orchestrator.track(execution.execution_id).state == ExecutionState.AWAITING_APPROVAL


def test_route_rejected_when_completed(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    orchestrator.route(execution)
    orchestrator.mark_awaiting_approval(execution.execution_id, result="done")
    orchestrator.approve(execution.execution_id)

    with pytest.raises(InvalidStateTransitionError):
        orchestrator.route(execution)

    assert orchestrator.track(execution.execution_id).state == ExecutionState.COMPLETED


def test_route_rejected_when_already_failed(orchestrator: Orchestrator):
    task = AgentTask(task_type="nonexistent_task_type", description="Will fail to route")
    execution = orchestrator.submit_task(task)
    with pytest.raises(NoSuitableAgentError):
        orchestrator.route(execution)
    assert execution.state == ExecutionState.FAILED

    # A second route() attempt on an already-FAILED execution must be
    # rejected as an illegal transition rather than silently retried.
    with pytest.raises(InvalidStateTransitionError):
        orchestrator.route(execution)


def test_full_lifecycle_cannot_skip_review_step(orchestrator: Orchestrator):
    """End-to-end guard: it must be impossible to reach COMPLETED without
    having actually been routed to an agent and passed through
    AWAITING_APPROVAL first."""
    execution = orchestrator.submit_task(_routable_task())

    # Attempting to jump straight to COMPLETED from PENDING must fail,
    # and must fail before any agent is ever assigned.
    with pytest.raises(InvalidStateTransitionError):
        orchestrator.approve(execution.execution_id)
    assert orchestrator.track(execution.execution_id).assigned_agent is None

    # Only the legal path succeeds.
    orchestrator.route(execution)
    orchestrator.mark_awaiting_approval(execution.execution_id, result="reviewed output")
    completed = orchestrator.approve(execution.execution_id)

    assert completed.state == ExecutionState.COMPLETED
    assert completed.assigned_agent is not None
    assert completed.result == "reviewed output"


# --------------------------------------------------------------------- #
# mark_failed() (Phase-06: used by ExecutionEngine once retries are
# exhausted, so a failed invocation is recorded with the same rigor as a
# successful one instead of being left stuck in RUNNING).
# --------------------------------------------------------------------- #


def test_mark_failed_from_running(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    routed = orchestrator.route(execution)
    assert routed.state == ExecutionState.RUNNING

    failed = orchestrator.mark_failed(routed.execution_id, error="agent CLI exited non-zero")

    assert failed.state == ExecutionState.FAILED
    assert failed.error == "agent CLI exited non-zero"


def test_mark_failed_rejected_when_pending(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    with pytest.raises(InvalidStateTransitionError):
        orchestrator.mark_failed(execution.execution_id, error="too early")


def test_mark_failed_rejected_when_already_completed(orchestrator: Orchestrator):
    execution = orchestrator.submit_task(_routable_task())
    routed = orchestrator.route(execution)
    orchestrator.mark_awaiting_approval(routed.execution_id, result="done")
    orchestrator.approve(routed.execution_id)

    with pytest.raises(InvalidStateTransitionError):
        orchestrator.mark_failed(routed.execution_id, error="too late")
