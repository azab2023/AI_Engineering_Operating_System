"""Unit tests for orchestrator.tools.builtin.* Tool implementations,
called directly (bypassing ToolExecutor's argument validation)."""

from __future__ import annotations

import pytest

from orchestrator.exceptions import ToolExecutionError
from orchestrator.tools.builtin.list_directory_tool import ListDirectoryTool
from orchestrator.tools.builtin.read_file_tool import ReadFileTool
from orchestrator.tools.models import ToolDefinition, ToolResult


def _definition(tool_name: str, tool_type: str) -> ToolDefinition:
    return ToolDefinition(tool_name=tool_name, tool_type=tool_type, enabled=True, description="x")


def test_read_file_tool_returns_tool_result(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("line one\nline two")
    tool = ReadFileTool(_definition("read_file", "read_file"))

    result = tool.execute({"path": str(target)})

    assert isinstance(result, ToolResult)
    assert result.tool_name == "read_file"
    assert result.output == "line one\nline two"


def test_read_file_tool_missing_path_raises():
    tool = ReadFileTool(_definition("read_file", "read_file"))
    with pytest.raises(ToolExecutionError, match="does not exist"):
        tool.execute({"path": "/nonexistent/path/x.txt"})


def test_read_file_tool_directory_path_raises(tmp_path):
    tool = ReadFileTool(_definition("read_file", "read_file"))
    with pytest.raises(ToolExecutionError, match="not a file"):
        tool.execute({"path": str(tmp_path)})


def test_list_directory_tool_returns_sorted_entries(tmp_path):
    (tmp_path / "z.txt").write_text("")
    (tmp_path / "a.txt").write_text("")
    (tmp_path / "sub").mkdir()
    tool = ListDirectoryTool(_definition("list_directory", "list_directory"))

    result = tool.execute({"path": str(tmp_path)})

    assert result.output == "a.txt\nsub\nz.txt"


def test_list_directory_tool_missing_path_raises():
    tool = ListDirectoryTool(_definition("list_directory", "list_directory"))
    with pytest.raises(ToolExecutionError, match="does not exist"):
        tool.execute({"path": "/nonexistent/path"})


def test_list_directory_tool_file_path_raises(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("x")
    tool = ListDirectoryTool(_definition("list_directory", "list_directory"))
    with pytest.raises(ToolExecutionError, match="not a directory"):
        tool.execute({"path": str(target)})


def test_list_directory_tool_empty_directory_returns_empty_output(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    tool = ListDirectoryTool(_definition("list_directory", "list_directory"))

    result = tool.execute({"path": str(empty_dir)})

    assert result.output == ""
