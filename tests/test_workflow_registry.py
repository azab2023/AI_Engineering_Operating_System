"""Unit tests for orchestrator.workflow.workflow_registry.WorkflowRegistry."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import WorkflowNotFoundError, WorkflowRegistryError
from orchestrator.workflow.models import StepType
from orchestrator.workflow.workflow_registry import DEFAULT_WORKFLOWS_PATH, WorkflowRegistry

# --------------------------------------------------------------------- #
# Against the real, shipped config/workflows.yaml
# --------------------------------------------------------------------- #


def test_real_workflows_file_exists():
    assert DEFAULT_WORKFLOWS_PATH.exists(), f"Expected workflows file at {DEFAULT_WORKFLOWS_PATH}"


def test_real_workflows_cover_expected_example():
    registry = WorkflowRegistry(DEFAULT_WORKFLOWS_PATH)
    assert "read_file_and_summarize" in registry


def test_real_workflow_definition_shape():
    registry = WorkflowRegistry(DEFAULT_WORKFLOWS_PATH)
    definition = registry.get_definition("read_file_and_summarize")
    assert len(definition) == 2
    assert definition.step_at(0).step_type == StepType.TOOL_CALL
    assert definition.step_at(0).tool_name == "read_file"
    assert definition.step_at(1).step_type == StepType.AGENT_TASK
    assert definition.step_at(1).task_type == "documentation"


# --------------------------------------------------------------------- #
# Validation, against temp files
# --------------------------------------------------------------------- #


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "workflows.yaml"
    # yaml.safe_dump, not an f-string: see project-wide learning that
    # f-string YAML interpolation breaks on shell/YAML metacharacters.
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(WorkflowRegistryError, match="not found"):
        WorkflowRegistry(tmp_path / "does_not_exist.yaml")


def test_not_valid_yaml_raises(tmp_path: Path):
    path = tmp_path / "workflows.yaml"
    path.write_text("workflows: [unterminated", encoding="utf-8")
    with pytest.raises(WorkflowRegistryError, match="not valid YAML"):
        WorkflowRegistry(path)


def test_missing_top_level_key_raises(tmp_path: Path):
    path = _write(tmp_path, {"not_workflows": {}})
    with pytest.raises(WorkflowRegistryError, match="workflows"):
        WorkflowRegistry(path)


def test_empty_workflows_mapping_raises(tmp_path: Path):
    path = _write(tmp_path, {"workflows": {}})
    with pytest.raises(WorkflowRegistryError, match="non-empty mapping"):
        WorkflowRegistry(path)


def test_workflow_entry_missing_steps_raises(tmp_path: Path):
    path = _write(tmp_path, {"workflows": {"w1": {"description": "no steps field"}}})
    with pytest.raises(WorkflowRegistryError, match="steps"):
        WorkflowRegistry(path)


def test_workflow_entry_empty_steps_list_raises(tmp_path: Path):
    path = _write(tmp_path, {"workflows": {"w1": {"steps": []}}})
    with pytest.raises(WorkflowRegistryError, match="non-empty list"):
        WorkflowRegistry(path)


def test_step_missing_required_field_raises(tmp_path: Path):
    path = _write(tmp_path, {"workflows": {"w1": {"steps": [{"step_id": "s1"}]}}})
    with pytest.raises(WorkflowRegistryError, match="step_type"):
        WorkflowRegistry(path)


def test_step_invalid_step_type_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        {"workflows": {"w1": {"steps": [{"step_id": "s1", "step_type": "not_a_type"}]}}},
    )
    with pytest.raises(WorkflowRegistryError, match="step_type"):
        WorkflowRegistry(path)


def test_agent_task_step_missing_task_type_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        {
            "workflows": {
                "w1": {
                    "steps": [{"step_id": "s1", "step_type": "agent_task", "description": "do it"}]
                }
            }
        },
    )
    with pytest.raises(WorkflowRegistryError, match="task_type"):
        WorkflowRegistry(path)


def test_tool_call_step_missing_tool_name_raises(tmp_path: Path):
    path = _write(
        tmp_path, {"workflows": {"w1": {"steps": [{"step_id": "s1", "step_type": "tool_call"}]}}}
    )
    with pytest.raises(WorkflowRegistryError, match="tool_name"):
        WorkflowRegistry(path)


def test_duplicate_step_id_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        {
            "workflows": {
                "w1": {
                    "steps": [
                        {"step_id": "s1", "step_type": "tool_call", "tool_name": "read_file"},
                        {"step_id": "s1", "step_type": "tool_call", "tool_name": "read_file"},
                    ]
                }
            }
        },
    )
    with pytest.raises(WorkflowRegistryError, match="duplicate step_id"):
        WorkflowRegistry(path)


def test_valid_multi_step_workflow_parses(tmp_path: Path):
    path = _write(
        tmp_path,
        {
            "workflows": {
                "example": {
                    "description": "A valid two-step workflow.",
                    "steps": [
                        {
                            "step_id": "read",
                            "step_type": "tool_call",
                            "tool_name": "read_file",
                            "tool_arguments": {"path": "README.md"},
                        },
                        {
                            "step_id": "act",
                            "step_type": "agent_task",
                            "task_type": "testing",
                            "description": "Write tests",
                            "required_capabilities": ["testing"],
                            "prompt_id": "some_prompt",
                            "prompt_variables": {"key": "value"},
                        },
                    ],
                }
            }
        },
    )
    registry = WorkflowRegistry(path)
    definition = registry.get_definition("example")
    assert definition.description == "A valid two-step workflow."
    assert len(definition) == 2
    assert definition.step_at(0).tool_arguments == {"path": "README.md"}
    assert definition.step_at(1).required_capabilities == ("testing",)
    assert definition.step_at(1).prompt_id == "some_prompt"


_SINGLE_TOOL_STEP = [{"step_id": "s1", "step_type": "tool_call", "tool_name": "read_file"}]


# --------------------------------------------------------------------- #
# Phase-12 (ADR-0010): tool_call step agent_name
# --------------------------------------------------------------------- #


def test_tool_call_step_agent_name_defaults_to_none(tmp_path: Path):
    path = _write(tmp_path, {"workflows": {"w1": {"steps": _SINGLE_TOOL_STEP}}})
    registry = WorkflowRegistry(path)
    assert registry.get_definition("w1").step_at(0).agent_name is None


def test_tool_call_step_agent_name_parsed(tmp_path: Path):
    path = _write(
        tmp_path,
        {
            "workflows": {
                "w1": {
                    "steps": [
                        {
                            "step_id": "s1",
                            "step_type": "tool_call",
                            "tool_name": "read_file",
                            "agent_name": "aider",
                        }
                    ]
                }
            }
        },
    )
    registry = WorkflowRegistry(path)
    assert registry.get_definition("w1").step_at(0).agent_name == "aider"


def test_tool_call_step_agent_name_non_string_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        {
            "workflows": {
                "w1": {
                    "steps": [
                        {
                            "step_id": "s1",
                            "step_type": "tool_call",
                            "tool_name": "read_file",
                            "agent_name": 123,
                        }
                    ]
                }
            }
        },
    )
    with pytest.raises(WorkflowRegistryError, match="agent_name"):
        WorkflowRegistry(path)


def test_get_definition_unknown_workflow_raises(tmp_path: Path):
    path = _write(tmp_path, {"workflows": {"w1": {"steps": _SINGLE_TOOL_STEP}}})
    registry = WorkflowRegistry(path)
    with pytest.raises(WorkflowNotFoundError):
        registry.get_definition("nonexistent")


def test_len_and_contains(tmp_path: Path):
    path = _write(tmp_path, {"workflows": {"w1": {"steps": _SINGLE_TOOL_STEP}}})
    registry = WorkflowRegistry(path)
    assert len(registry) == 1
    assert "w1" in registry
    assert "w2" not in registry
