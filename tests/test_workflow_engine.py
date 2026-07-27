"""Unit tests for orchestrator.workflow.workflow_engine.WorkflowEngine.

Uses the same ``FakeAgentInvoker`` test double pattern as
``test_execution_engine.py`` so ``agent_task`` steps never spawn real
subprocesses, and real ``ToolExecutor``/``ToolRegistry`` (default
``config/tools.yaml``) for ``tool_call`` steps against files created
under ``tmp_path``, so these tests never depend on the current working
directory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

from orchestrator.core import Orchestrator
from orchestrator.exceptions import (
    InvalidWorkflowStateTransitionError,
    UnknownWorkflowRunError,
    WorkflowNotFoundError,
    WorkflowStepNotApprovedError,
)
from orchestrator.execution.engine import ExecutionEngine
from orchestrator.execution.models import ExecutionResult, RetryPolicy
from orchestrator.models import Agent, AgentTask
from orchestrator.registry import DEFAULT_REGISTRY_PATH, AgentRegistry
from orchestrator.tools.tool_executor import ToolExecutor
from orchestrator.workflow.models import WorkflowRunState
from orchestrator.workflow.repository import InMemoryWorkflowRunRepository
from orchestrator.workflow.workflow_engine import WorkflowEngine
from orchestrator.workflow.workflow_registry import WorkflowRegistry

NO_DELAY = RetryPolicy(max_attempts=1, initial_backoff_seconds=0)


@dataclass
class FakeAgentInvoker:
    """Same test double as test_execution_engine.py: replays a scripted
    sequence of results/exceptions, one per call."""

    outcomes: list
    calls: list = field(default_factory=list)

    def invoke(self, agent: Agent, task: AgentTask) -> ExecutionResult:
        self.calls.append((agent, task))
        outcome = self.outcomes[len(self.calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _write_workflows(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "workflows.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _tool_call_step(step_id: str, path: Path) -> dict:
    return {
        "step_id": step_id,
        "step_type": "tool_call",
        "tool_name": "read_file",
        "tool_arguments": {"path": str(path)},
    }


def _agent_task_step(step_id: str, task_type: str = "testing") -> dict:
    return {
        "step_id": step_id,
        "step_type": "agent_task",
        "task_type": task_type,
        "description": f"Do the work for {step_id}",
    }


@pytest.fixture
def orchestrator() -> Orchestrator:
    return Orchestrator(AgentRegistry(DEFAULT_REGISTRY_PATH))


def _engine(
    orchestrator: Orchestrator,
    workflows_path: Path,
    invoker_outcomes: list,
) -> WorkflowEngine:
    invoker = FakeAgentInvoker(invoker_outcomes)
    execution_engine = ExecutionEngine(orchestrator, invoker=invoker, retry_policy=NO_DELAY)
    return WorkflowEngine(
        orchestrator=orchestrator,
        execution_engine=execution_engine,
        tool_executor=ToolExecutor(),
        registry=WorkflowRegistry(workflows_path),
        repository=InMemoryWorkflowRunRepository(),
    )


# --------------------------------------------------------------------- #
# start(): unknown workflow
# --------------------------------------------------------------------- #


def test_start_unknown_workflow_raises(tmp_path: Path, orchestrator: Orchestrator):
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_agent_task_step("s1")]}}}
    )
    engine = _engine(orchestrator, workflows_path, [])

    with pytest.raises(WorkflowNotFoundError):
        engine.start("nonexistent_workflow")


# --------------------------------------------------------------------- #
# Pure tool_call workflows: run straight through to COMPLETED
# --------------------------------------------------------------------- #


def test_single_tool_call_workflow_completes_immediately(
    tmp_path: Path, orchestrator: Orchestrator
):
    source_file = tmp_path / "source.txt"
    source_file.write_text("hello workflow", encoding="utf-8")
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_tool_call_step("read", source_file)]}}}
    )
    engine = _engine(orchestrator, workflows_path, [])

    run = engine.start("w1")

    assert run.state == WorkflowRunState.COMPLETED
    assert run.context["read"] == "hello workflow"
    assert run.current_step_index == 1


def test_two_tool_call_steps_run_in_order(tmp_path: Path, orchestrator: Orchestrator):
    file_a = tmp_path / "a.txt"
    file_a.write_text("A", encoding="utf-8")
    file_b = tmp_path / "b.txt"
    file_b.write_text("B", encoding="utf-8")
    workflows_path = _write_workflows(
        tmp_path,
        {
            "workflows": {
                "w1": {
                    "steps": [_tool_call_step("read_a", file_a), _tool_call_step("read_b", file_b)]
                }
            }
        },
    )
    engine = _engine(orchestrator, workflows_path, [])

    run = engine.start("w1")

    assert run.state == WorkflowRunState.COMPLETED
    assert run.context == {"read_a": "A", "read_b": "B"}


def test_tool_call_step_failure_marks_run_failed(tmp_path: Path, orchestrator: Orchestrator):
    missing_file = tmp_path / "does_not_exist.txt"
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_tool_call_step("read", missing_file)]}}}
    )
    engine = _engine(orchestrator, workflows_path, [])

    run = engine.start("w1")

    assert run.state == WorkflowRunState.FAILED
    assert run.error is not None


# --------------------------------------------------------------------- #
# Phase-12 (ADR-0010): tool_call step agent_name / authorization
# --------------------------------------------------------------------- #


def test_tool_call_step_without_agent_name_unaffected_by_authorization(
    tmp_path: Path, orchestrator: Orchestrator
):
    """No agent_name on the step (every workflow defined before
    Phase-12) -- must complete exactly as before."""
    source_file = tmp_path / "source.txt"
    source_file.write_text("hello workflow", encoding="utf-8")
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_tool_call_step("read", source_file)]}}}
    )
    engine = _engine(orchestrator, workflows_path, [])

    run = engine.start("w1")

    assert run.state == WorkflowRunState.COMPLETED
    assert run.context["read"] == "hello workflow"


def test_tool_call_step_with_known_permitted_agent_completes(
    tmp_path: Path, orchestrator: Orchestrator
):
    source_file = tmp_path / "source.txt"
    source_file.write_text("hello workflow", encoding="utf-8")
    step = _tool_call_step("read", source_file)
    step["agent_name"] = "claude_code"  # config/permissions.yaml grants read: true
    workflows_path = _write_workflows(tmp_path, {"workflows": {"w1": {"steps": [step]}}})
    engine = _engine(orchestrator, workflows_path, [])

    run = engine.start("w1")

    assert run.state == WorkflowRunState.COMPLETED
    assert run.context["read"] == "hello workflow"


def test_tool_call_step_with_unknown_agent_name_marks_run_failed(
    tmp_path: Path, orchestrator: Orchestrator
):
    source_file = tmp_path / "source.txt"
    source_file.write_text("hello workflow", encoding="utf-8")
    step = _tool_call_step("read", source_file)
    step["agent_name"] = "ghost_agent"  # no entry in config/permissions.yaml
    workflows_path = _write_workflows(tmp_path, {"workflows": {"w1": {"steps": [step]}}})
    engine = _engine(orchestrator, workflows_path, [])

    run = engine.start("w1")

    assert run.state == WorkflowRunState.FAILED
    assert run.error is not None
    assert "ghost_agent" in run.error


def test_tool_call_step_path_outside_sandbox_marks_run_failed(
    tmp_path: Path, orchestrator: Orchestrator
):
    """A path clearly outside both the project root and the OS temp
    dir (the default sandbox) must fail the run via the same
    ``SecurityError`` handling path as an ``UnknownAgentPermissionError``."""
    outside = Path("/definitely/outside/any/sandbox/file.txt")
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_tool_call_step("read", outside)]}}}
    )
    engine = _engine(orchestrator, workflows_path, [])

    run = engine.start("w1")

    assert run.state == WorkflowRunState.FAILED
    assert run.error is not None
    assert "read" not in run.context


# --------------------------------------------------------------------- #
# agent_task workflows: pause at AWAITING_APPROVAL, resume via approve()
# --------------------------------------------------------------------- #


def test_single_agent_task_workflow_pauses_for_approval(tmp_path: Path, orchestrator: Orchestrator):
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_agent_task_step("act")]}}}
    )
    outcome = ExecutionResult(output="agent output", exit_code=0, duration_seconds=0.1)
    engine = _engine(orchestrator, workflows_path, [outcome])

    run = engine.start("w1")

    assert run.state == WorkflowRunState.AWAITING_APPROVAL
    assert run.pending_execution_id is not None
    assert run.current_step_index == 0  # has not advanced past the paused step yet
    assert "act" not in run.context


def test_resume_before_approval_raises(tmp_path: Path, orchestrator: Orchestrator):
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_agent_task_step("act")]}}}
    )
    outcome = ExecutionResult(output="agent output", exit_code=0, duration_seconds=0.1)
    engine = _engine(orchestrator, workflows_path, [outcome])

    run = engine.start("w1")
    assert run.state == WorkflowRunState.AWAITING_APPROVAL

    with pytest.raises(WorkflowStepNotApprovedError):
        engine.resume(run.run_id)


def test_resume_after_approval_completes(tmp_path: Path, orchestrator: Orchestrator):
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_agent_task_step("act")]}}}
    )
    outcome = ExecutionResult(output="agent output", exit_code=0, duration_seconds=0.1)
    engine = _engine(orchestrator, workflows_path, [outcome])

    run = engine.start("w1")
    orchestrator.approve(run.pending_execution_id)

    resumed = engine.resume(run.run_id)

    assert resumed.state == WorkflowRunState.COMPLETED
    assert resumed.context["act"] == "agent output"
    assert resumed.pending_execution_id is None
    assert resumed.current_step_index == 1


def test_mixed_workflow_tool_then_agent_task(tmp_path: Path, orchestrator: Orchestrator):
    source_file = tmp_path / "notes.txt"
    source_file.write_text("some notes", encoding="utf-8")
    workflows_path = _write_workflows(
        tmp_path,
        {
            "workflows": {
                "w1": {
                    "steps": [
                        _tool_call_step("read_notes", source_file),
                        _agent_task_step("summarize", task_type="documentation"),
                    ]
                }
            }
        },
    )
    outcome = ExecutionResult(output="a tidy summary", exit_code=0, duration_seconds=0.1)
    engine = _engine(orchestrator, workflows_path, [outcome])

    run = engine.start("w1")
    assert run.state == WorkflowRunState.AWAITING_APPROVAL
    assert run.context == {"read_notes": "some notes"}
    assert run.current_step_index == 1

    orchestrator.approve(run.pending_execution_id)
    resumed = engine.resume(run.run_id)

    assert resumed.state == WorkflowRunState.COMPLETED
    assert resumed.context == {"read_notes": "some notes", "summarize": "a tidy summary"}


def test_agent_task_step_routing_failure_marks_run_failed(
    tmp_path: Path, orchestrator: Orchestrator
):
    workflows_path = _write_workflows(
        tmp_path,
        {"workflows": {"w1": {"steps": [_agent_task_step("act", task_type="nonexistent_task")]}}},
    )
    engine = _engine(orchestrator, workflows_path, [])

    run = engine.start("w1")

    assert run.state == WorkflowRunState.FAILED
    assert run.error is not None


# --------------------------------------------------------------------- #
# Invalid state transitions / lookups
# --------------------------------------------------------------------- #


def test_resume_unknown_run_raises(tmp_path: Path, orchestrator: Orchestrator):
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_agent_task_step("act")]}}}
    )
    engine = _engine(orchestrator, workflows_path, [])

    with pytest.raises(UnknownWorkflowRunError):
        engine.resume("00000000-0000-0000-0000-000000000000")


def test_resume_completed_run_raises(tmp_path: Path, orchestrator: Orchestrator):
    source_file = tmp_path / "source.txt"
    source_file.write_text("hello", encoding="utf-8")
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_tool_call_step("read", source_file)]}}}
    )
    engine = _engine(orchestrator, workflows_path, [])

    run = engine.start("w1")
    assert run.state == WorkflowRunState.COMPLETED

    with pytest.raises(InvalidWorkflowStateTransitionError) as exc_info:
        engine.resume(run.run_id)
    assert exc_info.value.expected_state == WorkflowRunState.AWAITING_APPROVAL.value
    assert exc_info.value.actual_state == WorkflowRunState.COMPLETED.value


def test_resume_failed_run_raises(tmp_path: Path, orchestrator: Orchestrator):
    missing_file = tmp_path / "missing.txt"
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_tool_call_step("read", missing_file)]}}}
    )
    engine = _engine(orchestrator, workflows_path, [])

    run = engine.start("w1")
    assert run.state == WorkflowRunState.FAILED

    with pytest.raises(InvalidWorkflowStateTransitionError):
        engine.resume(run.run_id)


# --------------------------------------------------------------------- #
# get_run() / list_runs()
# --------------------------------------------------------------------- #


def test_get_run_returns_current_state(tmp_path: Path, orchestrator: Orchestrator):
    source_file = tmp_path / "source.txt"
    source_file.write_text("hi", encoding="utf-8")
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_tool_call_step("read", source_file)]}}}
    )
    engine = _engine(orchestrator, workflows_path, [])

    run = engine.start("w1")
    fetched = engine.get_run(run.run_id)

    assert fetched.run_id == run.run_id
    assert fetched.state == WorkflowRunState.COMPLETED


def test_get_run_unknown_raises(tmp_path: Path, orchestrator: Orchestrator):
    workflows_path = _write_workflows(
        tmp_path, {"workflows": {"w1": {"steps": [_agent_task_step("act")]}}}
    )
    engine = _engine(orchestrator, workflows_path, [])

    with pytest.raises(UnknownWorkflowRunError):
        engine.get_run("00000000-0000-0000-0000-000000000000")


def test_list_runs_filters_by_state(tmp_path: Path, orchestrator: Orchestrator):
    good_file = tmp_path / "good.txt"
    good_file.write_text("ok", encoding="utf-8")
    missing_file = tmp_path / "missing.txt"
    workflows_path = _write_workflows(
        tmp_path,
        {
            "workflows": {
                "completes": {"steps": [_tool_call_step("read", good_file)]},
                "fails": {"steps": [_tool_call_step("read", missing_file)]},
            }
        },
    )
    engine = _engine(orchestrator, workflows_path, [])

    completed_run = engine.start("completes")
    failed_run = engine.start("fails")

    completed_runs = engine.list_runs(WorkflowRunState.COMPLETED)
    failed_runs = engine.list_runs(WorkflowRunState.FAILED)

    assert [r.run_id for r in completed_runs] == [completed_run.run_id]
    assert [r.run_id for r in failed_runs] == [failed_run.run_id]
    assert len(engine.list_runs()) == 2


# --------------------------------------------------------------------- #
# Default construction (real config/tools.yaml, config/workflows.yaml)
# --------------------------------------------------------------------- #


def test_default_construction_uses_real_shipped_config(orchestrator: Orchestrator):
    execution_engine = ExecutionEngine(
        orchestrator, invoker=FakeAgentInvoker([]), retry_policy=NO_DELAY
    )
    engine = WorkflowEngine(orchestrator=orchestrator, execution_engine=execution_engine)

    assert "read_file_and_summarize" in engine._registry  # noqa: SLF001
