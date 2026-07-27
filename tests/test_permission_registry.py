"""Unit tests for orchestrator.security.permission_registry.PermissionRegistry."""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest

from orchestrator.exceptions import PermissionRegistryError
from orchestrator.security.permission_registry import DEFAULT_PERMISSIONS_PATH, PermissionRegistry


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "permissions.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_default_permissions_file_loads_successfully():
    registry = PermissionRegistry(DEFAULT_PERMISSIONS_PATH)
    policy = registry.policy()
    assert len(policy.path_sandbox.allowed_roots) >= 1
    assert "claude_code" in policy.agent_permissions
    assert "codex" in policy.agent_permissions
    assert "aider" in policy.agent_permissions
    assert "gemini" in policy.agent_permissions


def test_default_permissions_include_system_temp_dir():
    registry = PermissionRegistry(DEFAULT_PERMISSIONS_PATH)
    policy = registry.policy()
    temp_dir = Path(tempfile.gettempdir()).resolve()
    assert temp_dir in policy.path_sandbox.allowed_roots


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(PermissionRegistryError, match="not found"):
        PermissionRegistry(tmp_path / "nonexistent.yaml")


def test_invalid_yaml_raises(tmp_path: Path):
    path = tmp_path / "permissions.yaml"
    path.write_text("path_sandbox: [this: is not, valid", encoding="utf-8")
    with pytest.raises(PermissionRegistryError, match="valid YAML"):
        PermissionRegistry(path)


def test_missing_path_sandbox_key_raises(tmp_path: Path):
    path = _write(tmp_path, "agent_permissions: {}")
    with pytest.raises(PermissionRegistryError, match="path_sandbox"):
        PermissionRegistry(path)


def test_path_sandbox_missing_allowed_roots_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        path_sandbox:
          include_system_temp_dir: false
        """,
    )
    with pytest.raises(PermissionRegistryError, match="allowed_roots"):
        PermissionRegistry(path)


def test_path_sandbox_allowed_roots_empty_list_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        path_sandbox:
          allowed_roots: []
        """,
    )
    with pytest.raises(PermissionRegistryError, match="non-empty"):
        PermissionRegistry(path)


def test_path_sandbox_relative_root_resolves_against_project_root(tmp_path: Path):
    from orchestrator.security.permission_registry import PROJECT_ROOT

    path = _write(
        tmp_path,
        """\
        path_sandbox:
          allowed_roots:
            - "."
        """,
    )
    policy = PermissionRegistry(path).policy()
    assert PROJECT_ROOT.resolve() in policy.path_sandbox.allowed_roots


def test_path_sandbox_include_system_temp_dir_false_by_default(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        path_sandbox:
          allowed_roots:
            - "."
        """,
    )
    policy = PermissionRegistry(path).policy()
    temp_dir = Path(tempfile.gettempdir()).resolve()
    assert temp_dir not in policy.path_sandbox.allowed_roots


def test_path_sandbox_include_system_temp_dir_non_boolean_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        path_sandbox:
          allowed_roots:
            - "."
          include_system_temp_dir: "yes"
        """,
    )
    with pytest.raises(PermissionRegistryError, match="include_system_temp_dir"):
        PermissionRegistry(path)


def test_agent_permissions_optional_defaults_to_empty(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        path_sandbox:
          allowed_roots:
            - "."
        """,
    )
    policy = PermissionRegistry(path).policy()
    assert policy.agent_permissions == {}


def test_agent_permissions_parses_valid_entries(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        path_sandbox:
          allowed_roots:
            - "."
        agent_permissions:
          claude_code:
            read: true
            write: true
          aider:
            read: true
            write: false
        """,
    )
    policy = PermissionRegistry(path).policy()
    assert policy.agent_permissions["claude_code"].can_write is True
    assert policy.agent_permissions["aider"].can_write is False


def test_agent_permissions_missing_field_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        path_sandbox:
          allowed_roots:
            - "."
        agent_permissions:
          claude_code:
            read: true
        """,
    )
    with pytest.raises(PermissionRegistryError, match="write"):
        PermissionRegistry(path)


def test_agent_permissions_non_boolean_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        path_sandbox:
          allowed_roots:
            - "."
        agent_permissions:
          claude_code:
            read: "yes"
            write: true
        """,
    )
    with pytest.raises(PermissionRegistryError, match="boolean"):
        PermissionRegistry(path)


def test_agent_permissions_entry_not_a_mapping_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        path_sandbox:
          allowed_roots:
            - "."
        agent_permissions:
          claude_code: "not a mapping"
        """,
    )
    with pytest.raises(PermissionRegistryError, match="mapping"):
        PermissionRegistry(path)
