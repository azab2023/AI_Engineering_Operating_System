"""Unit tests for orchestrator.execution.command_registry.AgentCommandRegistry."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator.exceptions import AgentCommandNotConfiguredError, AgentCommandRegistryError
from orchestrator.execution.command_registry import DEFAULT_COMMANDS_PATH, AgentCommandRegistry

# --------------------------------------------------------------------- #
# Against the real, shipped config/agent_commands.yaml
# --------------------------------------------------------------------- #


def test_real_commands_file_exists():
    assert DEFAULT_COMMANDS_PATH.exists(), f"Expected commands file at {DEFAULT_COMMANDS_PATH}"


def test_real_commands_cover_all_registry_agents():
    registry = AgentCommandRegistry(DEFAULT_COMMANDS_PATH)
    for expected_name in ("claude_code", "codex", "aider", "gemini"):
        assert expected_name in registry
        command = registry.get_command(expected_name)
        assert command.command
        assert command.timeout_seconds > 0
        assert "{task_description}" in command.command


# --------------------------------------------------------------------- #
# Validation, against temp files
# --------------------------------------------------------------------- #


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "agent_commands.yaml"
    path.write_text(textwrap.dedent(content))
    return path


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(AgentCommandRegistryError, match="not found"):
        AgentCommandRegistry(tmp_path / "does_not_exist.yaml")


def test_invalid_yaml_raises(tmp_path: Path):
    path = _write(tmp_path, "commands: [unclosed")
    with pytest.raises(AgentCommandRegistryError, match="not valid YAML"):
        AgentCommandRegistry(path)


def test_missing_top_level_key_raises(tmp_path: Path):
    path = _write(tmp_path, "not_commands: {}")
    with pytest.raises(AgentCommandRegistryError, match="top-level 'commands' key"):
        AgentCommandRegistry(path)


def test_empty_commands_raises(tmp_path: Path):
    path = _write(tmp_path, "commands: {}")
    with pytest.raises(AgentCommandRegistryError, match="non-empty mapping"):
        AgentCommandRegistry(path)


def test_missing_required_field_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
        commands:
          agent_a:
            command: ["echo", "{task_description}"]
        """,
    )
    with pytest.raises(AgentCommandRegistryError, match="missing required"):
        AgentCommandRegistry(path)


def test_missing_placeholder_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
        commands:
          agent_a:
            command: ["echo", "hello"]
            timeout_seconds: 30
        """,
    )
    with pytest.raises(AgentCommandRegistryError, match="task_description"):
        AgentCommandRegistry(path)


def test_non_positive_timeout_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
        commands:
          agent_a:
            command: ["echo", "{task_description}"]
            timeout_seconds: 0
        """,
    )
    with pytest.raises(AgentCommandRegistryError, match="positive number"):
        AgentCommandRegistry(path)


def test_valid_file_loads_and_get_command_works(tmp_path: Path):
    path = _write(
        tmp_path,
        """
        commands:
          agent_a:
            command: ["echo", "{task_description}"]
            timeout_seconds: 30
        """,
    )
    registry = AgentCommandRegistry(path)
    assert len(registry) == 1
    command = registry.get_command("agent_a")
    assert command.command == ("echo", "{task_description}")
    assert command.timeout_seconds == 30.0


def test_get_command_unknown_agent_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
        commands:
          agent_a:
            command: ["echo", "{task_description}"]
            timeout_seconds: 30
        """,
    )
    registry = AgentCommandRegistry(path)
    with pytest.raises(AgentCommandNotConfiguredError):
        registry.get_command("agent_b")
