"""Unit tests for orchestrator.registry.AgentRegistry."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator.exceptions import AgentRegistryError
from orchestrator.models import AgentStatus
from orchestrator.registry import AgentRegistry, DEFAULT_REGISTRY_PATH


# --------------------------------------------------------------------- #
# Against the real, shipped config/agent_registry.yaml
# --------------------------------------------------------------------- #


def test_real_registry_file_exists():
    assert DEFAULT_REGISTRY_PATH.exists(), (
        f"Expected registry file at {DEFAULT_REGISTRY_PATH}"
    )


def test_real_registry_loads_all_four_agents():
    registry = AgentRegistry(DEFAULT_REGISTRY_PATH)
    assert len(registry) == 4
    for expected_name in ("claude_code", "codex", "aider", "gemini"):
        assert expected_name in registry


def test_real_registry_agents_have_required_fields():
    registry = AgentRegistry(DEFAULT_REGISTRY_PATH)
    for agent in registry.list_agents():
        assert agent.name
        assert agent.provider
        assert agent.capabilities
        assert agent.supported_tasks
        assert agent.config_reference
        assert isinstance(agent.status, AgentStatus)


def test_real_registry_all_agents_active_by_default():
    registry = AgentRegistry(DEFAULT_REGISTRY_PATH)
    active = registry.list_agents(status=AgentStatus.ACTIVE)
    assert len(active) == 4


def test_find_by_capability_returns_matching_agents():
    registry = AgentRegistry(DEFAULT_REGISTRY_PATH)
    debuggers = registry.find_by_capability("debugging")
    names = {a.name for a in debuggers}
    assert names == {"codex", "aider"}


def test_find_by_task_returns_matching_agents():
    registry = AgentRegistry(DEFAULT_REGISTRY_PATH)
    doc_agents = registry.find_by_task("documentation")
    names = {a.name for a in doc_agents}
    assert names == {"claude_code", "gemini"}


def test_get_agent_unknown_name_raises():
    registry = AgentRegistry(DEFAULT_REGISTRY_PATH)
    with pytest.raises(AgentRegistryError):
        registry.get_agent("nonexistent_agent")


# --------------------------------------------------------------------- #
# Malformed-input rejection (fail loudly, not silently)
# --------------------------------------------------------------------- #


def _write_registry(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "agent_registry.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_missing_file_raises(tmp_path: Path):
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(AgentRegistryError):
        AgentRegistry(missing)


def test_invalid_yaml_raises(tmp_path: Path):
    path = _write_registry(
        tmp_path,
        """
        agents:
          - name: broken
          provider: mismatched_indent
        """,
    )
    with pytest.raises(AgentRegistryError):
        AgentRegistry(path)


def test_missing_top_level_agents_key_raises(tmp_path: Path):
    path = _write_registry(tmp_path, "not_agents: []\n")
    with pytest.raises(AgentRegistryError):
        AgentRegistry(path)


def test_empty_agents_list_raises(tmp_path: Path):
    path = _write_registry(tmp_path, "agents: []\n")
    with pytest.raises(AgentRegistryError):
        AgentRegistry(path)


def test_agent_missing_required_field_raises(tmp_path: Path):
    path = _write_registry(
        tmp_path,
        """
        agents:
          - name: incomplete_agent
            provider: test
            capabilities:
              - name: something
            supported_tasks:
              - some_task
            status: active
            # missing config_reference
        """,
    )
    with pytest.raises(AgentRegistryError):
        AgentRegistry(path)


def test_agent_invalid_status_raises(tmp_path: Path):
    path = _write_registry(
        tmp_path,
        """
        agents:
          - name: bad_status_agent
            provider: test
            capabilities:
              - name: something
            supported_tasks:
              - some_task
            config_reference: agents/bad/config
            status: definitely_not_a_status
        """,
    )
    with pytest.raises(AgentRegistryError):
        AgentRegistry(path)


def test_duplicate_agent_name_raises(tmp_path: Path):
    path = _write_registry(
        tmp_path,
        """
        agents:
          - name: dup_agent
            provider: test
            capabilities:
              - name: something
            supported_tasks:
              - some_task
            config_reference: agents/dup/config
            status: active
          - name: dup_agent
            provider: test
            capabilities:
              - name: something_else
            supported_tasks:
              - other_task
            config_reference: agents/dup/config
            status: active
        """,
    )
    with pytest.raises(AgentRegistryError):
        AgentRegistry(path)


def test_valid_minimal_custom_registry_loads(tmp_path: Path):
    path = _write_registry(
        tmp_path,
        """
        agents:
          - name: minimal_agent
            provider: test_provider
            capabilities:
              - name: minimal_capability
            supported_tasks:
              - minimal_task
            config_reference: agents/minimal/config
            status: planned
        """,
    )
    registry = AgentRegistry(path)
    assert len(registry) == 1
    agent = registry.get_agent("minimal_agent")
    assert agent.status == AgentStatus.PLANNED
    assert agent.has_capability("minimal_capability")
