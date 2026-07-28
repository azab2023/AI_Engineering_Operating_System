"""Unit tests for orchestrator.plugins.models."""

from __future__ import annotations

import pytest

from orchestrator.plugins.models import (
    CURRENT_AEOS_VERSION,
    PluginExtensionType,
    PluginLifecycleState,
    PluginMetadata,
    PluginRecord,
    parse_version,
)


def _metadata(**overrides) -> PluginMetadata:
    defaults = dict(
        plugin_name="sample_plugin",
        version="1.0.0",
        description="A sample plugin.",
        enabled=True,
        extension_type=PluginExtensionType.TOOL,
        target_name="read_file",
        min_aeos_version="1.3.0",
        max_aeos_version=None,
    )
    defaults.update(overrides)
    return PluginMetadata(**defaults)


# --------------------------------------------------------------------- #
# parse_version
# --------------------------------------------------------------------- #


def test_parse_version_returns_int_tuple():
    assert parse_version("1.4.0") == (1, 4, 0)
    assert parse_version("10.20.30") == (10, 20, 30)


@pytest.mark.parametrize("value", ["1.4", "1.4.0.1", "v1.4.0", "1.4.x", "", "1.4.0-beta"])
def test_parse_version_rejects_malformed_strings(value):
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        parse_version(value)


def test_current_aeos_version_is_parseable():
    # CURRENT_AEOS_VERSION itself must always satisfy the same format
    # every plugin's min/max_aeos_version is validated against.
    assert parse_version(CURRENT_AEOS_VERSION) is not None


# --------------------------------------------------------------------- #
# PluginMetadata
# --------------------------------------------------------------------- #


def test_valid_metadata_constructs():
    metadata = _metadata()
    assert metadata.plugin_name == "sample_plugin"
    assert metadata.extension_type == PluginExtensionType.TOOL


def test_empty_plugin_name_raises():
    with pytest.raises(ValueError, match="plugin_name"):
        _metadata(plugin_name="")


def test_empty_description_raises():
    with pytest.raises(ValueError, match="description"):
        _metadata(description="   ")


def test_empty_target_name_raises():
    with pytest.raises(ValueError, match="target_name"):
        _metadata(target_name="")


def test_invalid_extension_type_raises():
    with pytest.raises(ValueError, match="extension_type"):
        PluginMetadata(
            plugin_name="bad",
            version="1.0.0",
            description="bad",
            enabled=True,
            extension_type="tool",  # not a PluginExtensionType instance
            target_name="read_file",
            min_aeos_version="1.3.0",
        )


def test_invalid_own_version_raises():
    with pytest.raises(ValueError, match="version"):
        _metadata(version="not-a-version")


def test_invalid_min_aeos_version_raises():
    with pytest.raises(ValueError, match="min_aeos_version"):
        _metadata(min_aeos_version="bogus")


def test_invalid_max_aeos_version_raises():
    with pytest.raises(ValueError, match="max_aeos_version"):
        _metadata(max_aeos_version="bogus")


def test_max_below_min_raises():
    with pytest.raises(ValueError, match="lower than min_aeos_version"):
        _metadata(min_aeos_version="1.5.0", max_aeos_version="1.0.0")


def test_max_equal_to_min_is_valid():
    metadata = _metadata(min_aeos_version="1.3.0", max_aeos_version="1.3.0")
    assert metadata.max_aeos_version == "1.3.0"


def test_provider_extension_type_is_valid():
    metadata = _metadata(extension_type=PluginExtensionType.PROVIDER, target_name="claude_code")
    assert metadata.extension_type == PluginExtensionType.PROVIDER


# --------------------------------------------------------------------- #
# PluginRecord
# --------------------------------------------------------------------- #


def test_plugin_record_defaults_to_discovered_state():
    record = PluginRecord(plugin_name="sample_plugin", metadata=_metadata())
    assert record.state == PluginLifecycleState.DISCOVERED


def test_plugin_record_touch_updates_timestamp():
    record = PluginRecord(plugin_name="sample_plugin", metadata=_metadata())
    original = record.updated_at
    record.touch()
    assert record.updated_at >= original
