"""Unit tests for orchestrator.tools.tool_executor.ToolExecutor."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator.exceptions import (
    AgentPermissionError,
    InvalidArgumentTypeError,
    MissingRequiredArgumentError,
    PathPermissionError,
    ToolDisabledError,
    ToolExecutionError,
    ToolNotFoundError,
    UnknownAgentPermissionError,
    UnknownArgumentError,
)
from orchestrator.security.authorizer import ToolAuthorizer
from orchestrator.security.models import AgentPermission, PathSandboxPolicy, PermissionPolicy
from orchestrator.tools.tool_executor import ToolExecutor
from orchestrator.tools.tool_registry import ToolRegistry


def _registry(tmp_path: Path, content: str) -> ToolRegistry:
    path = tmp_path / "tools.yaml"
    path.write_text(textwrap.dedent(content))
    return ToolRegistry(path)


def _tools_yaml() -> str:
    return """\
        tools:
          read_file:
            tool_type: read_file
            enabled: true
            description: "Read a file."
            parameters:
              - name: path
                type: string
                required: true

          list_directory:
            tool_type: list_directory
            enabled: true
            description: "List a directory."
            parameters:
              - name: path
                type: string
                required: true

          disabled_tool:
            tool_type: read_file
            enabled: false
            description: "Disabled."

          typed_tool:
            tool_type: read_file
            enabled: true
            description: "Has a required + optional argument."
            parameters:
              - name: path
                type: string
                required: true
              - name: verbose
                type: boolean
                required: false
        """


# --------------------------------------------------------------------- #
# Happy path -- real built-in tools against a real tmp_path fixture
# --------------------------------------------------------------------- #


def test_execute_read_file_returns_contents(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hello world")
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))

    result = executor.execute("read_file", {"path": str(target)})

    assert result.tool_name == "read_file"
    assert result.output == "hello world"
    assert result.duration_seconds >= 0


def test_execute_list_directory_returns_sorted_entries(tmp_path):
    (tmp_path / "b.txt").write_text("")
    (tmp_path / "a.txt").write_text("")
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))

    result = executor.execute("list_directory", {"path": str(tmp_path)})

    assert result.output == "a.txt\nb.txt\ntools.yaml"


# --------------------------------------------------------------------- #
# Registry-level errors propagate unchanged
# --------------------------------------------------------------------- #


def test_execute_unknown_tool_raises(tmp_path):
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))
    with pytest.raises(ToolNotFoundError):
        executor.execute("nonexistent", {})


def test_execute_disabled_tool_raises(tmp_path):
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))
    with pytest.raises(ToolDisabledError):
        executor.execute("disabled_tool", {})


# --------------------------------------------------------------------- #
# Argument validation
# --------------------------------------------------------------------- #


def test_execute_missing_required_argument_raises(tmp_path):
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))
    with pytest.raises(MissingRequiredArgumentError, match="path"):
        executor.execute("read_file", {})


def test_execute_unknown_argument_raises(tmp_path):
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))
    with pytest.raises(UnknownArgumentError, match="bogus"):
        executor.execute("read_file", {"path": str(tmp_path), "bogus": "value"})


def test_execute_invalid_argument_type_raises(tmp_path):
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))
    with pytest.raises(InvalidArgumentTypeError, match="path"):
        executor.execute("read_file", {"path": 123})


def test_execute_bool_rejected_for_number_type(tmp_path):
    """bool is a subclass of int in Python -- a 'number' argument must
    not silently accept True/False."""
    registry = _registry(
        tmp_path,
        """\
        tools:
          numeric_tool:
            tool_type: read_file
            enabled: true
            description: "x"
            parameters:
              - name: count
                type: number
                required: true
        """,
    )
    executor = ToolExecutor(registry=registry)
    with pytest.raises(InvalidArgumentTypeError, match="count"):
        executor.execute("numeric_tool", {"count": True})


def test_execute_optional_argument_may_be_omitted(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hi")
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))

    result = executor.execute("typed_tool", {"path": str(target)})

    assert result.output == "hi"


# --------------------------------------------------------------------- #
# Tool-level execution failures
# --------------------------------------------------------------------- #


def test_execute_nonexistent_file_raises_tool_execution_error(tmp_path):
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))
    missing = tmp_path / "does_not_exist.txt"
    with pytest.raises(ToolExecutionError, match="does not exist"):
        executor.execute("read_file", {"path": str(missing)})


def test_execute_directory_as_file_raises_tool_execution_error(tmp_path):
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))
    with pytest.raises(ToolExecutionError, match="not a file"):
        executor.execute("read_file", {"path": str(tmp_path)})


def test_execute_file_as_directory_raises_tool_execution_error(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hi")
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))
    with pytest.raises(ToolExecutionError, match="not a directory"):
        executor.execute("list_directory", {"path": str(target)})


# --------------------------------------------------------------------- #
# Phase-12 (ADR-0010): authorization -- path sandbox + agent permissions
# --------------------------------------------------------------------- #


def _sandboxed_tools_yaml() -> str:
    return """\
        tools:
          read_file:
            tool_type: read_file
            enabled: true
            description: "Read a file."
            parameters:
              - name: path
                type: string
                required: true
            sandboxed_parameters: [path]
            access_mode: read

          write_file:
            tool_type: read_file
            enabled: true
            description: "Pretend write tool (reuses read_file behavior for the test)."
            parameters:
              - name: path
                type: string
                required: true
            sandboxed_parameters: [path]
            access_mode: write
        """


def _authorizer(sandbox_root: Path, agent_permissions=None) -> ToolAuthorizer:
    policy = PermissionPolicy(
        path_sandbox=PathSandboxPolicy(allowed_roots=(sandbox_root.resolve(),)),
        agent_permissions=agent_permissions or {},
    )
    return ToolAuthorizer(policy=policy)


def test_execute_default_agent_name_is_none_and_unchecked(tmp_path):
    """No agent_name supplied -- pre-Phase-12 call shape -- must behave
    exactly as before, even against a tool with a restrictive
    access_mode and no configured agent_permissions at all."""
    target = tmp_path / "hello.txt"
    target.write_text("hello world")
    executor = ToolExecutor(
        registry=_registry(tmp_path, _sandboxed_tools_yaml()),
        authorizer=_authorizer(tmp_path),
    )

    result = executor.execute("write_file", {"path": str(target)})

    assert result.output == "hello world"


def test_execute_path_outside_sandbox_raises(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    executor = ToolExecutor(
        registry=_registry(tmp_path, _sandboxed_tools_yaml()),
        authorizer=_authorizer(tmp_path),
    )

    with pytest.raises(PathPermissionError):
        executor.execute("read_file", {"path": str(outside)})


def test_execute_path_inside_sandbox_allowed(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hi")
    executor = ToolExecutor(
        registry=_registry(tmp_path, _sandboxed_tools_yaml()),
        authorizer=_authorizer(tmp_path),
    )

    result = executor.execute("read_file", {"path": str(target)})

    assert result.output == "hi"


def test_execute_unknown_agent_name_raises(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hi")
    executor = ToolExecutor(
        registry=_registry(tmp_path, _sandboxed_tools_yaml()),
        authorizer=_authorizer(tmp_path),
    )

    with pytest.raises(UnknownAgentPermissionError):
        executor.execute("read_file", {"path": str(target)}, agent_name="ghost_agent")


def test_execute_agent_without_write_permission_raises(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hi")
    permissions = {"aider": AgentPermission(agent_name="aider", can_read=True, can_write=False)}
    executor = ToolExecutor(
        registry=_registry(tmp_path, _sandboxed_tools_yaml()),
        authorizer=_authorizer(tmp_path, permissions),
    )

    with pytest.raises(AgentPermissionError):
        executor.execute("write_file", {"path": str(target)}, agent_name="aider")


def test_execute_agent_with_write_permission_allowed(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hi")
    permissions = {
        "claude_code": AgentPermission(agent_name="claude_code", can_read=True, can_write=True)
    }
    executor = ToolExecutor(
        registry=_registry(tmp_path, _sandboxed_tools_yaml()),
        authorizer=_authorizer(tmp_path, permissions),
    )

    result = executor.execute("write_file", {"path": str(target)}, agent_name="claude_code")

    assert result.output == "hi"


def test_execute_default_authorizer_loads_real_permissions_file(tmp_path):
    """No authorizer passed -- ToolExecutor must load the real,
    default config/permissions.yaml, not raise on construction."""
    target = tmp_path / "hello.txt"
    target.write_text("hello world")
    executor = ToolExecutor(registry=_registry(tmp_path, _tools_yaml()))

    result = executor.execute("read_file", {"path": str(target)})

    assert result.output == "hello world"
