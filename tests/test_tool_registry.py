"""Unit tests for orchestrator.tools.tool_registry.ToolRegistry."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator.exceptions import ToolDisabledError, ToolNotFoundError, ToolRegistryError
from orchestrator.tools.tool_registry import DEFAULT_TOOLS_PATH, ToolRegistry

# --------------------------------------------------------------------- #
# Against the real, shipped config/tools.yaml
# --------------------------------------------------------------------- #


def test_real_tools_file_exists():
    assert DEFAULT_TOOLS_PATH.exists(), f"Expected tools file at {DEFAULT_TOOLS_PATH}"


def test_real_tools_cover_expected_builtins():
    registry = ToolRegistry(DEFAULT_TOOLS_PATH)
    for expected_name in ("read_file", "list_directory"):
        assert expected_name in registry


def test_real_tools_are_resolvable():
    registry = ToolRegistry(DEFAULT_TOOLS_PATH)
    for expected_name in ("read_file", "list_directory"):
        definition = registry.get_definition(expected_name)
        assert definition.tool_type
        assert definition.description
        assert definition.required_argument_names() == frozenset({"path"})


# --------------------------------------------------------------------- #
# Validation, against temp files
# --------------------------------------------------------------------- #


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "tools.yaml"
    path.write_text(textwrap.dedent(content))
    return path


def _valid_yaml() -> str:
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

          disabled_tool:
            tool_type: read_file
            enabled: false
            description: "Disabled."
        """


def test_load_valid_registry(tmp_path):
    registry = ToolRegistry(_write(tmp_path, _valid_yaml()))
    assert len(registry) == 2
    assert "read_file" in registry
    assert "missing" not in registry


def test_get_definition_returns_enabled_entry(tmp_path):
    registry = ToolRegistry(_write(tmp_path, _valid_yaml()))
    definition = registry.get_definition("read_file")
    assert definition.tool_type == "read_file"
    assert definition.parameters[0].name == "path"


def test_get_definition_unknown_tool_raises(tmp_path):
    registry = ToolRegistry(_write(tmp_path, _valid_yaml()))
    with pytest.raises(ToolNotFoundError):
        registry.get_definition("nonexistent")


def test_get_definition_disabled_tool_raises(tmp_path):
    registry = ToolRegistry(_write(tmp_path, _valid_yaml()))
    with pytest.raises(ToolDisabledError):
        registry.get_definition("disabled_tool")


def test_is_enabled_never_raises(tmp_path):
    registry = ToolRegistry(_write(tmp_path, _valid_yaml()))
    assert registry.is_enabled("read_file") is True
    assert registry.is_enabled("disabled_tool") is False
    assert registry.is_enabled("nonexistent") is False


def test_missing_file_raises(tmp_path):
    with pytest.raises(ToolRegistryError, match="not found"):
        ToolRegistry(tmp_path / "does_not_exist.yaml")


def test_invalid_yaml_raises(tmp_path):
    path = tmp_path / "tools.yaml"
    path.write_text("tools: [this is not a mapping")
    with pytest.raises(ToolRegistryError, match="not valid YAML"):
        ToolRegistry(path)


def test_missing_top_level_key_raises(tmp_path):
    path = _write(tmp_path, "not_tools: {}")
    with pytest.raises(ToolRegistryError, match="top-level 'tools' key"):
        ToolRegistry(path)


def test_empty_tools_mapping_raises(tmp_path):
    path = _write(tmp_path, "tools: {}")
    with pytest.raises(ToolRegistryError, match="non-empty mapping"):
        ToolRegistry(path)


def test_entry_missing_required_field_raises(tmp_path):
    path = _write(
        tmp_path,
        """\
        tools:
          broken:
            tool_type: read_file
            enabled: true
        """,
    )
    with pytest.raises(ToolRegistryError, match="missing required field"):
        ToolRegistry(path)


def test_entry_not_a_mapping_raises(tmp_path):
    path = _write(tmp_path, "tools:\n  broken: not_a_mapping\n")
    with pytest.raises(ToolRegistryError, match="must be a mapping"):
        ToolRegistry(path)


def test_entry_enabled_wrong_type_raises(tmp_path):
    path = _write(
        tmp_path,
        """\
        tools:
          broken:
            tool_type: read_file
            enabled: "yes"
            description: "x"
        """,
    )
    with pytest.raises(ToolRegistryError, match="'enabled' must be a boolean"):
        ToolRegistry(path)


def test_parameters_not_a_list_raises(tmp_path):
    path = _write(
        tmp_path,
        """\
        tools:
          broken:
            tool_type: read_file
            enabled: true
            description: "x"
            parameters: "not a list"
        """,
    )
    with pytest.raises(ToolRegistryError, match="'parameters' must be a list"):
        ToolRegistry(path)


def test_parameter_missing_required_field_raises(tmp_path):
    path = _write(
        tmp_path,
        """\
        tools:
          broken:
            tool_type: read_file
            enabled: true
            description: "x"
            parameters:
              - name: path
        """,
    )
    with pytest.raises(ToolRegistryError, match="missing required field"):
        ToolRegistry(path)


def test_parameter_invalid_type_raises(tmp_path):
    path = _write(
        tmp_path,
        """\
        tools:
          broken:
            tool_type: read_file
            enabled: true
            description: "x"
            parameters:
              - name: path
                type: array
                required: true
        """,
    )
    with pytest.raises(ToolRegistryError, match="path"):
        ToolRegistry(path)
