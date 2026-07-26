"""Unit tests for orchestrator.workflow.models."""

from __future__ import annotations

import pytest

from orchestrator.workflow.models import (
    StepType,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowRunState,
    WorkflowStep,
)

# --------------------------------------------------------------------- #
# WorkflowStep
# --------------------------------------------------------------------- #


def test_agent_task_step_requires_task_type():
    with pytest.raises(ValueError, match="task_type"):
        WorkflowStep(step_id="s1", step_type=StepType.AGENT_TASK, description="do it")


def test_agent_task_step_requires_description():
    with pytest.raises(ValueError, match="description"):
        WorkflowStep(step_id="s1", step_type=StepType.AGENT_TASK, task_type="testing")


def test_agent_task_step_valid_minimal():
    step = WorkflowStep(
        step_id="s1", step_type=StepType.AGENT_TASK, task_type="testing", description="do it"
    )
    assert step.step_id == "s1"
    assert step.required_capabilities == ()
    assert step.prompt_id is None


def test_tool_call_step_requires_tool_name():
    with pytest.raises(ValueError, match="tool_name"):
        WorkflowStep(step_id="s1", step_type=StepType.TOOL_CALL)


def test_tool_call_step_valid_minimal():
    step = WorkflowStep(step_id="s1", step_type=StepType.TOOL_CALL, tool_name="read_file")
    assert step.tool_name == "read_file"
    assert step.tool_arguments == {}


def test_step_id_must_be_non_empty():
    with pytest.raises(ValueError, match="step_id"):
        WorkflowStep(step_id="", step_type=StepType.TOOL_CALL, tool_name="read_file")


# --------------------------------------------------------------------- #
# WorkflowDefinition
# --------------------------------------------------------------------- #


def _tool_step(step_id: str = "s1") -> WorkflowStep:
    return WorkflowStep(step_id=step_id, step_type=StepType.TOOL_CALL, tool_name="read_file")


def test_workflow_definition_requires_at_least_one_step():
    with pytest.raises(ValueError, match="at least one step"):
        WorkflowDefinition(workflow_id="w1", steps=())


def test_workflow_definition_rejects_duplicate_step_ids():
    with pytest.raises(ValueError, match="duplicate step_id"):
        WorkflowDefinition(workflow_id="w1", steps=(_tool_step("dup"), _tool_step("dup")))


def test_workflow_definition_requires_non_empty_workflow_id():
    with pytest.raises(ValueError, match="workflow_id"):
        WorkflowDefinition(workflow_id="", steps=(_tool_step(),))


def test_workflow_definition_step_at_and_len():
    steps = (_tool_step("a"), _tool_step("b"))
    definition = WorkflowDefinition(workflow_id="w1", steps=steps)
    assert len(definition) == 2
    assert definition.step_at(0).step_id == "a"
    assert definition.step_at(1).step_id == "b"


# --------------------------------------------------------------------- #
# WorkflowRun
# --------------------------------------------------------------------- #


def test_workflow_run_defaults():
    run = WorkflowRun(workflow_id="w1")
    assert run.state == WorkflowRunState.PENDING
    assert run.current_step_index == 0
    assert run.context == {}
    assert run.pending_execution_id is None
    assert run.error is None
    assert run.run_id


def test_workflow_run_touch_updates_timestamp():
    run = WorkflowRun(workflow_id="w1")
    original = run.updated_at
    run.touch()
    assert run.updated_at >= original


def test_workflow_run_ids_are_unique():
    run_a = WorkflowRun(workflow_id="w1")
    run_b = WorkflowRun(workflow_id="w1")
    assert run_a.run_id != run_b.run_id
