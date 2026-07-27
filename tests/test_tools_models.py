"""Unit tests for orchestrator.tools.models."""

from __future__ import annotations

import pytest

from orchestrator.tools.models import ToolDefinition, ToolParameter, ToolResult


def test_tool_parameter_valid():
    param = ToolParameter(name="path", type="string", required=True)
    assert param.name == "path"
    assert param.type == "string"
    assert param.required is True
    assert param.description == ""


def test_tool_parameter_empty_name_raises():
    with pytest.raises(ValueError, match="name"):
        ToolParameter(name="", type="string", required=True)


def test_tool_parameter_invalid_type_raises():
    with pytest.raises(ValueError, match="type"):
        ToolParameter(name="path", type="array", required=True)


def test_tool_definition_valid():
    definition = ToolDefinition(
        tool_name="read_file",
        tool_type="read_file",
        enabled=True,
        description="Read a file.",
        parameters=(ToolParameter(name="path", type="string", required=True),),
    )
    assert definition.required_argument_names() == frozenset({"path"})
    assert definition.declared_argument_names() == frozenset({"path"})
    assert definition.parameter("path").type == "string"


def test_tool_definition_defaults_to_no_parameters():
    definition = ToolDefinition(
        tool_name="noop", tool_type="noop", enabled=True, description="Does nothing."
    )
    assert definition.parameters == ()
    assert definition.required_argument_names() == frozenset()


def test_tool_definition_parameter_missing_raises_key_error():
    definition = ToolDefinition(
        tool_name="read_file", tool_type="read_file", enabled=True, description="Read a file."
    )
    with pytest.raises(KeyError):
        definition.parameter("path")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"tool_name": "", "tool_type": "read_file", "enabled": True, "description": "x"},
        {"tool_name": "x", "tool_type": "", "enabled": True, "description": "x"},
        {"tool_name": "x", "tool_type": "read_file", "enabled": True, "description": ""},
    ],
)
def test_tool_definition_rejects_empty_required_fields(kwargs):
    with pytest.raises(ValueError):
        ToolDefinition(**kwargs)


# --------------------------------------------------------------------- #
# Phase-12 (ADR-0010): sandboxed_parameters / access_mode
# --------------------------------------------------------------------- #


def test_tool_definition_defaults_no_sandboxed_parameters_and_read_access_mode():
    definition = ToolDefinition(
        tool_name="read_file", tool_type="read_file", enabled=True, description="Read a file."
    )
    assert definition.sandboxed_parameters == ()
    assert definition.access_mode == "read"


def test_tool_definition_accepts_declared_sandboxed_parameter():
    definition = ToolDefinition(
        tool_name="read_file",
        tool_type="read_file",
        enabled=True,
        description="Read a file.",
        parameters=(ToolParameter(name="path", type="string", required=True),),
        sandboxed_parameters=("path",),
    )
    assert definition.sandboxed_parameters == ("path",)


def test_tool_definition_undeclared_sandboxed_parameter_raises():
    with pytest.raises(ValueError, match="undeclared"):
        ToolDefinition(
            tool_name="read_file",
            tool_type="read_file",
            enabled=True,
            description="Read a file.",
            sandboxed_parameters=("path",),
        )


def test_tool_definition_access_mode_write_accepted():
    definition = ToolDefinition(
        tool_name="write_file",
        tool_type="write_file",
        enabled=True,
        description="Write a file.",
        access_mode="write",
    )
    assert definition.access_mode == "write"


def test_tool_definition_invalid_access_mode_raises():
    with pytest.raises(ValueError, match="access_mode"):
        ToolDefinition(
            tool_name="read_file",
            tool_type="read_file",
            enabled=True,
            description="Read a file.",
            access_mode="execute",
        )


def test_tool_result_valid():
    result = ToolResult(tool_name="read_file", output="contents", duration_seconds=0.01)
    assert result.output == "contents"


def test_tool_result_negative_duration_raises():
    with pytest.raises(ValueError, match="duration_seconds"):
        ToolResult(tool_name="read_file", output="x", duration_seconds=-1.0)


def test_tool_result_empty_tool_name_raises():
    with pytest.raises(ValueError, match="tool_name"):
        ToolResult(tool_name="", output="x", duration_seconds=0.0)
