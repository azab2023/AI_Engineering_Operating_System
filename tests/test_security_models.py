"""Unit tests for orchestrator.security.models."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.security.models import AgentPermission, PathSandboxPolicy, PermissionPolicy


def test_path_sandbox_policy_allows_root_itself(tmp_path: Path):
    policy = PathSandboxPolicy(allowed_roots=(tmp_path.resolve(),))
    assert policy.is_allowed(tmp_path) is True


def test_path_sandbox_policy_allows_descendant(tmp_path: Path):
    nested = tmp_path / "a" / "b.txt"
    policy = PathSandboxPolicy(allowed_roots=(tmp_path.resolve(),))
    assert policy.is_allowed(nested) is True


def test_path_sandbox_policy_rejects_outside_path(tmp_path: Path):
    outside = tmp_path.parent / "definitely-not-inside"
    policy = PathSandboxPolicy(allowed_roots=(tmp_path.resolve(),))
    assert policy.is_allowed(outside) is False


def test_path_sandbox_policy_rejects_sibling_directory(tmp_path: Path):
    root = tmp_path / "sandbox"
    root.mkdir()
    sibling = tmp_path / "sandbox-lookalike" / "file.txt"
    policy = PathSandboxPolicy(allowed_roots=(root.resolve(),))
    assert policy.is_allowed(sibling) is False


def test_path_sandbox_policy_empty_allowed_roots_raises():
    with pytest.raises(ValueError, match="allowed_roots"):
        PathSandboxPolicy(allowed_roots=())


def test_path_sandbox_policy_relative_root_raises():
    with pytest.raises(ValueError, match="absolute"):
        PathSandboxPolicy(allowed_roots=(Path("relative/root"),))


def test_agent_permission_valid():
    permission = AgentPermission(agent_name="claude_code", can_read=True, can_write=True)
    assert permission.agent_name == "claude_code"
    assert permission.can_read is True
    assert permission.can_write is True


def test_agent_permission_empty_name_raises():
    with pytest.raises(ValueError, match="agent_name"):
        AgentPermission(agent_name="", can_read=True, can_write=False)


def test_permission_policy_permission_for_known_agent(tmp_path: Path):
    permission = AgentPermission(agent_name="aider", can_read=True, can_write=False)
    policy = PermissionPolicy(
        path_sandbox=PathSandboxPolicy(allowed_roots=(tmp_path.resolve(),)),
        agent_permissions={"aider": permission},
    )
    assert policy.permission_for("aider") is permission


def test_permission_policy_permission_for_unknown_agent_returns_none(tmp_path: Path):
    policy = PermissionPolicy(
        path_sandbox=PathSandboxPolicy(allowed_roots=(tmp_path.resolve(),)),
    )
    assert policy.permission_for("nonexistent_agent") is None


def test_permission_policy_defaults_to_no_agent_permissions(tmp_path: Path):
    policy = PermissionPolicy(
        path_sandbox=PathSandboxPolicy(allowed_roots=(tmp_path.resolve(),)),
    )
    assert policy.agent_permissions == {}
