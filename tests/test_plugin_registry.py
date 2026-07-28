"""Unit tests for orchestrator.plugins.plugin_registry.PluginRegistry."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator.exceptions import PluginDisabledError, PluginNotFoundError, PluginRegistryError
from orchestrator.plugins.models import PluginExtensionType
from orchestrator.plugins.plugin_registry import DEFAULT_PLUGINS_PATH, PluginRegistry


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "plugins.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def _valid_entry(**overrides) -> str:
    fields = dict(
        version='"1.0.0"',
        description='"Sample plugin."',
        enabled="true",
        extension_type="tool",
        target_name="read_file",
        min_aeos_version='"1.3.0"',
    )
    fields.update(overrides)
    lines = "\n".join(f"    {key}: {value}" for key, value in fields.items())
    return f"plugins:\n  sample_plugin:\n{lines}\n"


# --------------------------------------------------------------------- #
# Default file
# --------------------------------------------------------------------- #


def test_default_plugins_file_loads_successfully():
    registry = PluginRegistry(DEFAULT_PLUGINS_PATH)
    assert len(registry) > 0
    assert "read_file_plugin" in registry


def test_default_read_file_plugin_definition():
    registry = PluginRegistry(DEFAULT_PLUGINS_PATH)
    definition = registry.get_definition("read_file_plugin")
    assert definition.extension_type == PluginExtensionType.TOOL
    assert definition.target_name == "read_file"


# --------------------------------------------------------------------- #
# File-level errors
# --------------------------------------------------------------------- #


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(PluginRegistryError, match="not found"):
        PluginRegistry(tmp_path / "nonexistent.yaml")


def test_invalid_yaml_raises(tmp_path: Path):
    path = tmp_path / "plugins.yaml"
    path.write_text("plugins: [this: is not, valid", encoding="utf-8")
    with pytest.raises(PluginRegistryError, match="valid YAML"):
        PluginRegistry(path)


def test_missing_plugins_key_raises(tmp_path: Path):
    path = _write(tmp_path, "not_plugins:\n  foo: bar\n")
    with pytest.raises(PluginRegistryError, match="plugins"):
        PluginRegistry(path)


def test_empty_plugins_mapping_raises(tmp_path: Path):
    path = _write(tmp_path, "plugins: {}\n")
    with pytest.raises(PluginRegistryError, match="non-empty mapping"):
        PluginRegistry(path)


def test_non_mapping_entry_raises(tmp_path: Path):
    path = _write(tmp_path, 'plugins:\n  sample_plugin: "not a mapping"\n')
    with pytest.raises(PluginRegistryError, match="mapping"):
        PluginRegistry(path)


# --------------------------------------------------------------------- #
# Field-level errors
# --------------------------------------------------------------------- #


def test_missing_required_field_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        plugins:
          sample_plugin:
            version: "1.0.0"
            description: "Sample."
            enabled: true
        """,
    )
    with pytest.raises(PluginRegistryError, match="missing required field"):
        PluginRegistry(path)


def test_invalid_extension_type_raises(tmp_path: Path):
    path = _write(tmp_path, _valid_entry(extension_type='"database"'))
    with pytest.raises(PluginRegistryError, match="extension_type"):
        PluginRegistry(path)


def test_non_boolean_enabled_raises(tmp_path: Path):
    path = _write(tmp_path, _valid_entry(enabled='"yes"'))
    with pytest.raises(PluginRegistryError, match="enabled.*boolean"):
        PluginRegistry(path)


def test_empty_version_raises(tmp_path: Path):
    path = _write(tmp_path, _valid_entry(version='""'))
    with pytest.raises(PluginRegistryError, match="version"):
        PluginRegistry(path)


def test_malformed_version_raises_via_model_validation(tmp_path: Path):
    path = _write(tmp_path, _valid_entry(min_aeos_version='"not-a-version"'))
    with pytest.raises(PluginRegistryError, match="min_aeos_version"):
        PluginRegistry(path)


def test_unknown_field_raises(tmp_path: Path):
    path = _write(tmp_path, _valid_entry().rstrip() + "\n    mystery_field: 42\n")
    with pytest.raises(PluginRegistryError, match="unknown field"):
        PluginRegistry(path)


def test_null_max_aeos_version_is_valid(tmp_path: Path):
    path = _write(tmp_path, _valid_entry(max_aeos_version="null"))
    registry = PluginRegistry(path)
    assert registry.get_definition("sample_plugin").max_aeos_version is None


def test_explicit_max_aeos_version_is_valid(tmp_path: Path):
    path = _write(tmp_path, _valid_entry(max_aeos_version='"2.0.0"'))
    registry = PluginRegistry(path)
    assert registry.get_definition("sample_plugin").max_aeos_version == "2.0.0"


# --------------------------------------------------------------------- #
# get_definition / is_enabled / __len__ / __contains__
# --------------------------------------------------------------------- #


def test_get_definition_missing_plugin_raises(tmp_path: Path):
    path = _write(tmp_path, _valid_entry())
    registry = PluginRegistry(path)
    with pytest.raises(PluginNotFoundError):
        registry.get_definition("does_not_exist")


def test_get_definition_disabled_plugin_raises(tmp_path: Path):
    path = _write(tmp_path, _valid_entry(enabled="false"))
    registry = PluginRegistry(path)
    with pytest.raises(PluginDisabledError):
        registry.get_definition("sample_plugin")


def test_is_enabled_true_for_enabled_plugin(tmp_path: Path):
    path = _write(tmp_path, _valid_entry())
    registry = PluginRegistry(path)
    assert registry.is_enabled("sample_plugin") is True


def test_is_enabled_false_for_disabled_plugin(tmp_path: Path):
    path = _write(tmp_path, _valid_entry(enabled="false"))
    registry = PluginRegistry(path)
    assert registry.is_enabled("sample_plugin") is False


def test_is_enabled_false_for_unknown_plugin(tmp_path: Path):
    path = _write(tmp_path, _valid_entry())
    registry = PluginRegistry(path)
    assert registry.is_enabled("does_not_exist") is False


def test_len_and_contains(tmp_path: Path):
    path = _write(tmp_path, _valid_entry())
    registry = PluginRegistry(path)
    assert len(registry) == 1
    assert "sample_plugin" in registry
    assert "does_not_exist" not in registry
