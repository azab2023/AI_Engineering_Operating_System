"""Unit tests for orchestrator.tools.tool_factory.ToolFactory."""

from __future__ import annotations

import pytest

from orchestrator.exceptions import UnsupportedToolTypeError
from orchestrator.tools.builtin.list_directory_tool import ListDirectoryTool
from orchestrator.tools.builtin.read_file_tool import ReadFileTool
from orchestrator.tools.models import ToolDefinition
from orchestrator.tools.tool_factory import ToolFactory


def _definition(tool_type: str, tool_name: str = "some_tool") -> ToolDefinition:
    return ToolDefinition(tool_name=tool_name, tool_type=tool_type, enabled=True, description="x")


@pytest.mark.parametrize(
    "tool_type,expected_class",
    [
        ("read_file", ReadFileTool),
        ("list_directory", ListDirectoryTool),
    ],
)
def test_create_returns_correct_implementation(tool_type, expected_class):
    tool = ToolFactory.create(_definition(tool_type))
    assert isinstance(tool, expected_class)


def test_create_unknown_tool_type_raises():
    with pytest.raises(UnsupportedToolTypeError, match="shell_exec"):
        ToolFactory.create(_definition("shell_exec"))


def test_create_no_if_elif_chain_is_a_pure_lookup():
    """Adding a tool_type is meant to be a dict-entry addition, never a
    conditional branch -- assert the resolution mechanism really is a
    dict lookup, not incidentally correct behavior from branching logic.
    """
    assert isinstance(ToolFactory._IMPLEMENTATIONS, dict)  # noqa: SLF001
    assert set(ToolFactory._IMPLEMENTATIONS) == {"read_file", "list_directory"}  # noqa: SLF001
