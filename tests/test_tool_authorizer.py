"""Unit tests for orchestrator.security.authorizer.ToolAuthorizer."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.exceptions import (
    AgentPermissionError,
    PathPermissionError,
    UnknownAgentPermissionError,
)
from orchestrator.security.authorizer import ToolAuthorizer
from orchestrator.security.models import AgentPermission, PathSandboxPolicy, PermissionPolicy
from orchestrator.tools.models import ToolDefinition, ToolParameter


def _definition(
    sandboxed_parameters: tuple[str, ...] = (), access_mode: str = "read"
) -> ToolDefinition:
    return ToolDefinition(
        tool_name="read_file",
        tool_type="read_file",
        enabled=True,
        description="Read a file.",
        parameters=(ToolParameter(name="path", type="string", required=True),),
        sandboxed_parameters=sandboxed_parameters,
        access_mode=access_mode,
    )


def _policy(tmp_path: Path, agent_permissions: dict[str, AgentPermission] | None = None):
    return PermissionPolicy(
        path_sandbox=PathSandboxPolicy(allowed_roots=(tmp_path.resolve(),)),
        agent_permissions=agent_permissions or {},
    )


# --------------------------------------------------------------------- #
# Path sandbox checks
# --------------------------------------------------------------------- #


def test_authorize_allows_path_inside_sandbox(tmp_path: Path):
    authorizer = ToolAuthorizer(policy=_policy(tmp_path))
    definition = _definition(sandboxed_parameters=("path",))
    inside = tmp_path / "file.txt"

    authorizer.authorize(definition, {"path": str(inside)}, agent_name=None)  # no raise


def test_authorize_rejects_path_outside_sandbox(tmp_path: Path):
    authorizer = ToolAuthorizer(policy=_policy(tmp_path))
    definition = _definition(sandboxed_parameters=("path",))
    outside = tmp_path.parent / "outside.txt"

    with pytest.raises(PathPermissionError):
        authorizer.authorize(definition, {"path": str(outside)}, agent_name=None)


def test_authorize_skips_path_check_when_parameter_not_sandboxed(tmp_path: Path):
    authorizer = ToolAuthorizer(policy=_policy(tmp_path))
    definition = _definition(sandboxed_parameters=())
    outside = tmp_path.parent / "outside.txt"

    authorizer.authorize(definition, {"path": str(outside)}, agent_name=None)  # no raise


def test_authorize_skips_path_check_when_argument_absent(tmp_path: Path):
    authorizer = ToolAuthorizer(policy=_policy(tmp_path))
    definition = _definition(sandboxed_parameters=("path",))

    authorizer.authorize(definition, {}, agent_name=None)  # no raise, argument absent


# --------------------------------------------------------------------- #
# Agent permission checks
# --------------------------------------------------------------------- #


def test_authorize_skips_agent_check_when_agent_name_none(tmp_path: Path):
    authorizer = ToolAuthorizer(policy=_policy(tmp_path))
    definition = _definition(access_mode="write")

    authorizer.authorize(definition, {"path": str(tmp_path)}, agent_name=None)  # no raise


def test_authorize_unknown_agent_raises(tmp_path: Path):
    authorizer = ToolAuthorizer(policy=_policy(tmp_path))
    definition = _definition()

    with pytest.raises(UnknownAgentPermissionError):
        authorizer.authorize(definition, {"path": str(tmp_path)}, agent_name="ghost_agent")


def test_authorize_agent_with_read_permission_allowed_for_read_tool(tmp_path: Path):
    permissions = {"aider": AgentPermission(agent_name="aider", can_read=True, can_write=False)}
    authorizer = ToolAuthorizer(policy=_policy(tmp_path, permissions))
    definition = _definition(access_mode="read")

    authorizer.authorize(definition, {"path": str(tmp_path)}, agent_name="aider")  # no raise


def test_authorize_agent_without_write_permission_rejected_for_write_tool(tmp_path: Path):
    permissions = {"aider": AgentPermission(agent_name="aider", can_read=True, can_write=False)}
    authorizer = ToolAuthorizer(policy=_policy(tmp_path, permissions))
    definition = _definition(access_mode="write")

    with pytest.raises(AgentPermissionError):
        authorizer.authorize(definition, {"path": str(tmp_path)}, agent_name="aider")


def test_authorize_agent_with_write_permission_allowed_for_write_tool(tmp_path: Path):
    permissions = {
        "claude_code": AgentPermission(agent_name="claude_code", can_read=True, can_write=True)
    }
    authorizer = ToolAuthorizer(policy=_policy(tmp_path, permissions))
    definition = _definition(access_mode="write")

    authorizer.authorize(definition, {"path": str(tmp_path)}, agent_name="claude_code")  # no raise


def test_authorize_agent_without_read_permission_rejected_for_read_tool(tmp_path: Path):
    permissions = {"aider": AgentPermission(agent_name="aider", can_read=False, can_write=False)}
    authorizer = ToolAuthorizer(policy=_policy(tmp_path, permissions))
    definition = _definition(access_mode="read")

    with pytest.raises(AgentPermissionError):
        authorizer.authorize(definition, {"path": str(tmp_path)}, agent_name="aider")


def test_authorize_checks_agent_before_path(tmp_path: Path):
    """Both checks matter, but the agent check should surface first when
    both would fail -- an unpermitted agent should never learn anything
    about path-sandbox internals."""
    authorizer = ToolAuthorizer(policy=_policy(tmp_path))
    definition = _definition(sandboxed_parameters=("path",))
    outside = tmp_path.parent / "outside.txt"

    with pytest.raises(UnknownAgentPermissionError):
        authorizer.authorize(definition, {"path": str(outside)}, agent_name="ghost_agent")
