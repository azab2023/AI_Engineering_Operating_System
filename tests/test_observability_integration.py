"""Integration tests for the Phase-13 (ADR-0011) Observer pattern wired
into Orchestrator, ExecutionEngine, ToolExecutor, and WorkflowEngine.

Two concerns per component:
    1. ``observer=None`` (the default) reproduces pre-Phase-13 behavior
       exactly -- no new code path is exercised beyond a no-op check.
    2. Supplying an ``InMemoryRecorder`` actually records the documented
       events/metrics (ADR-0011 decision 5's table).
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from orchestrator.core import Orchestrator
from orchestrator.exceptions import AgentTimeoutError, NoSuitableAgentError
from orchestrator.execution.engine import ExecutionEngine
from orchestrator.execution.models import ExecutionResult, RetryPolicy
from orchestrator.models import Agent, AgentTask, ExecutionState
from orchestrator.observability.recorder import InMemoryRecorder
from orchestrator.registry import DEFAULT_REGISTRY_PATH, AgentRegistry
from orchestrator.tools.tool_executor import ToolExecutor
from orchestrator.tools.tool_registry import ToolRegistry
from orchestrator.workflow.repository import InMemoryWorkflowRunRepository
from orchestrator.workflow.workflow_engine import WorkflowEngine
from orchestrator.workflow.workflow_registry import WorkflowRegistry

NO_DELAY = RetryPolicy(max_attempts=3, initial_backoff_seconds=0)


@dataclass
class FakeAgentInvoker:
    """Same test double used by test_execution_engine.py /
    test_workflow_engine.py."""

    outcomes: list
    calls: list = field(default_factory=list)

    def invoke(self, agent: Agent, task: AgentTask) -> ExecutionResult:
        self.calls.append((agent, task))
        outcome = self.outcomes[len(self.calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def orchestrator() -> Orchestrator:
    return Orchestrator(AgentRegistry(DEFAULT_REGISTRY_PATH))


# --------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------- #


def test_orchestrator_observer_none_is_unchanged_behavior(orchestrator: Orchestrator):
    task = AgentTask(task_type="testing", description="write unit tests")
    execution = orchestrator.submit_task(task)

    routed = orchestrator.route(execution)

    assert routed.state == ExecutionState.RUNNING


def test_orchestrator_records_route_and_approval_events():
    recorder = InMemoryRecorder()
    orchestrator = Orchestrator(AgentRegistry(DEFAULT_REGISTRY_PATH), observer=recorder)
    task = AgentTask(task_type="testing", description="write unit tests")
    execution = orchestrator.submit_task(task)

    routed = orchestrator.route(execution)
    completed = orchestrator.mark_awaiting_approval(routed.execution_id, result="ok")
    orchestrator.approve(completed.execution_id)

    event_types = [e.event_type for e in recorder.events(component="orchestrator")]
    assert "task_routed" in event_types
    assert "execution_awaiting_approval" in event_types
    assert "execution_approved" in event_types
    assert len(recorder.metrics(name="orchestrator.routes_total")) == 1


def test_orchestrator_records_route_failed_event_and_metric():
    recorder = InMemoryRecorder()
    orchestrator = Orchestrator(AgentRegistry(DEFAULT_REGISTRY_PATH), observer=recorder)
    task = AgentTask(task_type="no_such_task_type", description="unroutable")
    execution = orchestrator.submit_task(task)

    with pytest.raises(NoSuitableAgentError):
        orchestrator.route(execution)

    event_types = [e.event_type for e in recorder.events(component="orchestrator")]
    assert "route_failed" in event_types
    metrics = recorder.metrics(name="orchestrator.routes_total")
    assert metrics[0].tags["outcome"] == "failed"


# --------------------------------------------------------------------- #
# ExecutionEngine
# --------------------------------------------------------------------- #


def test_execution_engine_observer_none_is_unchanged_behavior(orchestrator: Orchestrator):
    task = AgentTask(task_type="testing", description="write unit tests")
    execution = orchestrator.submit_task(task)
    invoker = FakeAgentInvoker([ExecutionResult(output="ok", exit_code=0, duration_seconds=0.01)])
    engine = ExecutionEngine(orchestrator, invoker=invoker, retry_policy=NO_DELAY)

    result = engine.execute(execution)

    assert result.state == ExecutionState.AWAITING_APPROVAL


def test_execution_engine_records_success_event_with_duration(orchestrator: Orchestrator):
    recorder = InMemoryRecorder()
    task = AgentTask(task_type="testing", description="write unit tests")
    execution = orchestrator.submit_task(task)
    invoker = FakeAgentInvoker([ExecutionResult(output="ok", exit_code=0, duration_seconds=0.01)])
    engine = ExecutionEngine(
        orchestrator, invoker=invoker, retry_policy=NO_DELAY, observer=recorder
    )

    engine.execute(execution)

    events = recorder.events(component="execution_engine", event_type="execution_succeeded")
    assert len(events) == 1
    assert events[0].duration_seconds is not None
    metrics = recorder.metrics(name="execution_engine.attempts_total")
    assert metrics[-1].tags["outcome"] == "success"
    assert len(recorder.metrics(name="execution_engine.invocation_duration_seconds")) == 1


def test_execution_engine_records_retry_and_exhaustion_events(orchestrator: Orchestrator):
    recorder = InMemoryRecorder()
    task = AgentTask(task_type="testing", description="always fails")
    execution = orchestrator.submit_task(task)
    invoker = FakeAgentInvoker(
        [AgentTimeoutError("claude_code", 30.0) for _ in range(NO_DELAY.max_attempts)]
    )
    engine = ExecutionEngine(
        orchestrator, invoker=invoker, retry_policy=NO_DELAY, observer=recorder
    )

    engine.execute(execution)

    failed_attempts = recorder.events(
        component="execution_engine", event_type="invocation_attempt_failed"
    )
    assert len(failed_attempts) == NO_DELAY.max_attempts
    exhausted = recorder.events(
        component="execution_engine", event_type="execution_retries_exhausted"
    )
    assert len(exhausted) == 1


# --------------------------------------------------------------------- #
# ToolExecutor
# --------------------------------------------------------------------- #


def _tool_registry(tmp_path: Path) -> ToolRegistry:
    path = tmp_path / "tools.yaml"
    path.write_text(
        textwrap.dedent(
            """\
            tools:
              read_file:
                tool_type: read_file
                enabled: true
                description: "Read a file."
                parameters:
                  - name: path
                    type: string
                    required: true
            """
        )
    )
    return ToolRegistry(path)


def test_tool_executor_observer_none_is_unchanged_behavior(tmp_path: Path):
    target = tmp_path / "hello.txt"
    target.write_text("hello world")
    executor = ToolExecutor(registry=_tool_registry(tmp_path))

    result = executor.execute("read_file", {"path": str(target)})

    assert result.output == "hello world"


def test_tool_executor_records_success_event_and_metrics(tmp_path: Path):
    recorder = InMemoryRecorder()
    target = tmp_path / "hello.txt"
    target.write_text("hello world")
    executor = ToolExecutor(registry=_tool_registry(tmp_path), observer=recorder)

    executor.execute("read_file", {"path": str(target)})

    events = recorder.events(component="tool_executor", event_type="tool_executed")
    assert len(events) == 1
    assert events[0].duration_seconds is not None
    assert events[0].attributes["tool_name"] == "read_file"
    metrics = recorder.metrics(name="tool_executor.calls_total")
    assert metrics[0].tags == {"tool_name": "read_file", "outcome": "success"}
    assert len(recorder.metrics(name="tool_executor.execution_duration_seconds")) == 1


def test_tool_executor_records_failure_event_and_metric(tmp_path: Path):
    recorder = InMemoryRecorder()
    missing = tmp_path / "does_not_exist.txt"
    executor = ToolExecutor(registry=_tool_registry(tmp_path), observer=recorder)

    with pytest.raises(Exception):  # noqa: B017 - ToolExecutionError, any reason
        executor.execute("read_file", {"path": str(missing)})

    events = recorder.events(component="tool_executor", event_type="tool_execution_failed")
    assert len(events) == 1
    metrics = recorder.metrics(name="tool_executor.calls_total")
    assert metrics[0].tags["outcome"] == "error"


# --------------------------------------------------------------------- #
# WorkflowEngine
# --------------------------------------------------------------------- #


def _write_workflows(tmp_path: Path, data: dict) -> Path:
    import yaml

    path = tmp_path / "workflows.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _workflow_engine(
    orchestrator: Orchestrator,
    workflows_path: Path,
    invoker_outcomes: list,
    observer=None,
) -> WorkflowEngine:
    invoker = FakeAgentInvoker(invoker_outcomes)
    execution_engine = ExecutionEngine(
        orchestrator, invoker=invoker, retry_policy=NO_DELAY, observer=observer
    )
    return WorkflowEngine(
        orchestrator,
        execution_engine,
        registry=WorkflowRegistry(workflows_path),
        repository=InMemoryWorkflowRunRepository(),
        observer=observer,
    )


def _single_agent_task_workflow() -> dict:
    return {
        "workflows": {
            "wf": {
                "steps": [
                    {
                        "step_id": "s1",
                        "step_type": "agent_task",
                        "task_type": "testing",
                        "description": "do the work",
                    }
                ]
            }
        }
    }


def test_workflow_engine_observer_none_is_unchanged_behavior(
    orchestrator: Orchestrator, tmp_path: Path
):
    workflows_path = _write_workflows(tmp_path, _single_agent_task_workflow())
    engine = _workflow_engine(
        orchestrator,
        workflows_path,
        [ExecutionResult(output="done", exit_code=0, duration_seconds=0.01)],
    )

    run = engine.start("wf")
    # the run pauses at AWAITING_APPROVAL for its single agent_task step
    from orchestrator.workflow.models import WorkflowRunState

    assert run.state == WorkflowRunState.AWAITING_APPROVAL


def test_workflow_engine_records_started_and_completed_events(
    orchestrator: Orchestrator, tmp_path: Path
):
    recorder = InMemoryRecorder()
    workflows_path = _write_workflows(tmp_path, _single_agent_task_workflow())
    engine = _workflow_engine(
        orchestrator,
        workflows_path,
        [ExecutionResult(output="done", exit_code=0, duration_seconds=0.01)],
        observer=recorder,
    )

    run = engine.start("wf")
    orchestrator.approve(run.pending_execution_id)
    completed = engine.resume(run.run_id)

    from orchestrator.workflow.models import WorkflowRunState

    assert completed.state == WorkflowRunState.COMPLETED
    started = recorder.events(component="workflow_engine", event_type="workflow_run_started")
    finished = recorder.events(component="workflow_engine", event_type="workflow_run_completed")
    assert len(started) == 1
    assert len(finished) == 1
    assert finished[0].duration_seconds is not None
    metrics = recorder.metrics(name="workflow_engine.runs_total")
    assert metrics[0].tags["outcome"] == "completed"
    assert len(recorder.metrics(name="workflow_engine.run_duration_seconds")) == 1


def test_workflow_engine_records_failed_event_for_tool_call_step(
    orchestrator: Orchestrator, tmp_path: Path
):
    recorder = InMemoryRecorder()
    workflows_path = _write_workflows(
        tmp_path,
        {
            "workflows": {
                "wf": {
                    "steps": [
                        {
                            "step_id": "s1",
                            "step_type": "tool_call",
                            "tool_name": "read_file",
                            "tool_arguments": {"path": str(tmp_path / "missing.txt")},
                        }
                    ]
                }
            }
        },
    )
    engine = _workflow_engine(orchestrator, workflows_path, [], observer=recorder)

    run = engine.start("wf")

    from orchestrator.workflow.models import WorkflowRunState

    assert run.state == WorkflowRunState.FAILED
    failed = recorder.events(component="workflow_engine", event_type="workflow_run_failed")
    assert len(failed) == 1
    metrics = recorder.metrics(name="workflow_engine.runs_total")
    assert metrics[0].tags["outcome"] == "failed"
