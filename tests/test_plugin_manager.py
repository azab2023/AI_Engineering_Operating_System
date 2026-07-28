"""Unit and observability-integration tests for
orchestrator.plugins.plugin_manager.PluginManager.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator.exceptions import (
    InvalidPluginStateTransitionError,
    PluginAlreadyLoadedError,
    PluginDisabledError,
    PluginNotFoundError,
    PluginTargetNotFoundError,
    PluginVersionIncompatibleError,
    UnknownPluginRecordError,
)
from orchestrator.observability.recorder import InMemoryRecorder
from orchestrator.plugins.models import CURRENT_AEOS_VERSION, PluginLifecycleState
from orchestrator.plugins.plugin_manager import PluginManager
from orchestrator.plugins.plugin_registry import PluginRegistry
from orchestrator.providers.provider_registry import ModelProviderRegistry
from orchestrator.tools.tool_registry import ToolRegistry


def _plugin_registry(tmp_path: Path, content: str) -> PluginRegistry:
    path = tmp_path / "plugins.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return PluginRegistry(path)


def _tool_registry(tmp_path: Path) -> ToolRegistry:
    path = tmp_path / "tools.yaml"
    path.write_text(
        textwrap.dedent(
            """\
            tools:
              read_file:
                tool_type: read_file
                enabled: true
                description: "Read a file."
              disabled_tool:
                tool_type: read_file
                enabled: false
                description: "Disabled."
            """
        ),
        encoding="utf-8",
    )
    return ToolRegistry(path)


def _provider_registry(tmp_path: Path) -> ModelProviderRegistry:
    path = tmp_path / "model_providers.yaml"
    path.write_text(
        textwrap.dedent(
            """\
            providers:
              claude_code:
                provider_type: anthropic
                enabled: true
                base_url: https://api.anthropic.com/v1/messages
                model: claude-sonnet-4-6
                api_key_env_var: ANTHROPIC_API_KEY
                timeout_seconds: 300
              aider:
                provider_type: openai
                enabled: false
                base_url: https://api.openai.com/v1/chat/completions
                model: gpt-4.1
                api_key_env_var: OPENAI_API_KEY
                timeout_seconds: 300
            """
        ),
        encoding="utf-8",
    )
    return ModelProviderRegistry(path)


def _tool_plugin_entry(plugin_name: str = "sample_plugin", **overrides) -> str:
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
    return f"plugins:\n  {plugin_name}:\n{lines}\n"


@pytest.fixture
def manager(tmp_path: Path) -> PluginManager:
    return PluginManager(
        registry=_plugin_registry(tmp_path, _tool_plugin_entry()),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
    )


# --------------------------------------------------------------------- #
# load()
# --------------------------------------------------------------------- #


def test_load_creates_record_in_discovered_state(manager: PluginManager):
    record = manager.load("sample_plugin")
    assert record.state == PluginLifecycleState.DISCOVERED
    assert record.plugin_name == "sample_plugin"


def test_load_unknown_plugin_raises(manager: PluginManager):
    with pytest.raises(PluginNotFoundError):
        manager.load("does_not_exist")


def test_load_disabled_plugin_raises(tmp_path: Path):
    manager = PluginManager(
        registry=_plugin_registry(tmp_path, _tool_plugin_entry(enabled="false")),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
    )
    with pytest.raises(PluginDisabledError):
        manager.load("sample_plugin")


def test_load_twice_raises(manager: PluginManager):
    manager.load("sample_plugin")
    with pytest.raises(PluginAlreadyLoadedError):
        manager.load("sample_plugin")


# --------------------------------------------------------------------- #
# validate()
# --------------------------------------------------------------------- #


def test_validate_transitions_to_validated(manager: PluginManager):
    manager.load("sample_plugin")
    record = manager.validate("sample_plugin")
    assert record.state == PluginLifecycleState.VALIDATED


def test_validate_before_load_raises(manager: PluginManager):
    with pytest.raises(UnknownPluginRecordError):
        manager.validate("sample_plugin")


def test_validate_twice_raises_invalid_transition(manager: PluginManager):
    manager.load("sample_plugin")
    manager.validate("sample_plugin")
    with pytest.raises(InvalidPluginStateTransitionError):
        manager.validate("sample_plugin")


def test_validate_incompatible_min_version_raises(tmp_path: Path):
    manager = PluginManager(
        registry=_plugin_registry(tmp_path, _tool_plugin_entry(min_aeos_version='"99.0.0"')),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
    )
    manager.load("sample_plugin")
    with pytest.raises(PluginVersionIncompatibleError, match=CURRENT_AEOS_VERSION):
        manager.validate("sample_plugin")


def test_validate_incompatible_max_version_raises(tmp_path: Path):
    manager = PluginManager(
        registry=_plugin_registry(
            tmp_path,
            _tool_plugin_entry(min_aeos_version='"0.1.0"', max_aeos_version='"0.9.0"'),
        ),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
    )
    manager.load("sample_plugin")
    with pytest.raises(PluginVersionIncompatibleError):
        manager.validate("sample_plugin")


def test_validate_compatible_version_range_succeeds(tmp_path: Path):
    manager = PluginManager(
        registry=_plugin_registry(
            tmp_path,
            _tool_plugin_entry(min_aeos_version='"1.0.0"', max_aeos_version='"9.9.9"'),
        ),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
    )
    manager.load("sample_plugin")
    record = manager.validate("sample_plugin")
    assert record.state == PluginLifecycleState.VALIDATED


def test_validate_target_tool_not_found_raises(tmp_path: Path):
    manager = PluginManager(
        registry=_plugin_registry(tmp_path, _tool_plugin_entry(target_name='"nonexistent_tool"')),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
    )
    manager.load("sample_plugin")
    with pytest.raises(PluginTargetNotFoundError):
        manager.validate("sample_plugin")


def test_validate_target_disabled_tool_raises(tmp_path: Path):
    manager = PluginManager(
        registry=_plugin_registry(tmp_path, _tool_plugin_entry(target_name='"disabled_tool"')),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
    )
    manager.load("sample_plugin")
    with pytest.raises(PluginTargetNotFoundError):
        manager.validate("sample_plugin")


def test_validate_provider_extension_type_success(tmp_path: Path):
    manager = PluginManager(
        registry=_plugin_registry(
            tmp_path,
            _tool_plugin_entry(extension_type='"provider"', target_name='"claude_code"'),
        ),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
    )
    manager.load("sample_plugin")
    record = manager.validate("sample_plugin")
    assert record.state == PluginLifecycleState.VALIDATED


def test_validate_provider_extension_type_disabled_target_raises(tmp_path: Path):
    manager = PluginManager(
        registry=_plugin_registry(
            tmp_path,
            _tool_plugin_entry(extension_type='"provider"', target_name='"aider"'),
        ),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
    )
    manager.load("sample_plugin")
    with pytest.raises(PluginTargetNotFoundError):
        manager.validate("sample_plugin")


# --------------------------------------------------------------------- #
# initialize()
# --------------------------------------------------------------------- #


def test_initialize_transitions_to_initialized(manager: PluginManager):
    manager.load("sample_plugin")
    manager.validate("sample_plugin")
    record = manager.initialize("sample_plugin")
    assert record.state == PluginLifecycleState.INITIALIZED


def test_initialize_before_validate_raises(manager: PluginManager):
    manager.load("sample_plugin")
    with pytest.raises(InvalidPluginStateTransitionError):
        manager.initialize("sample_plugin")


def test_initialize_unknown_plugin_raises(manager: PluginManager):
    with pytest.raises(UnknownPluginRecordError):
        manager.initialize("sample_plugin")


# --------------------------------------------------------------------- #
# unload()
# --------------------------------------------------------------------- #


def test_unload_transitions_to_unloaded(manager: PluginManager):
    manager.load("sample_plugin")
    manager.validate("sample_plugin")
    manager.initialize("sample_plugin")
    record = manager.unload("sample_plugin")
    assert record.state == PluginLifecycleState.UNLOADED


def test_unload_before_initialize_raises(manager: PluginManager):
    manager.load("sample_plugin")
    manager.validate("sample_plugin")
    with pytest.raises(InvalidPluginStateTransitionError):
        manager.unload("sample_plugin")


def test_unload_unknown_plugin_raises(manager: PluginManager):
    with pytest.raises(UnknownPluginRecordError):
        manager.unload("sample_plugin")


# --------------------------------------------------------------------- #
# get() / list_plugins() / is_active()
# --------------------------------------------------------------------- #


def test_get_unknown_plugin_raises(manager: PluginManager):
    with pytest.raises(UnknownPluginRecordError):
        manager.get("sample_plugin")


def test_get_returns_tracked_record(manager: PluginManager):
    manager.load("sample_plugin")
    assert manager.get("sample_plugin").plugin_name == "sample_plugin"


def test_list_plugins_returns_all_loaded(manager: PluginManager):
    manager.load("sample_plugin")
    plugins = manager.list_plugins()
    assert len(plugins) == 1
    assert plugins[0].plugin_name == "sample_plugin"


def test_list_plugins_empty_when_none_loaded(manager: PluginManager):
    assert manager.list_plugins() == []


def test_is_active_false_before_load(manager: PluginManager):
    assert manager.is_active("sample_plugin") is False


def test_is_active_false_after_validate_only(manager: PluginManager):
    manager.load("sample_plugin")
    manager.validate("sample_plugin")
    assert manager.is_active("sample_plugin") is False


def test_is_active_true_after_initialize(manager: PluginManager):
    manager.load("sample_plugin")
    manager.validate("sample_plugin")
    manager.initialize("sample_plugin")
    assert manager.is_active("sample_plugin") is True


def test_is_active_false_after_unload(manager: PluginManager):
    manager.load("sample_plugin")
    manager.validate("sample_plugin")
    manager.initialize("sample_plugin")
    manager.unload("sample_plugin")
    assert manager.is_active("sample_plugin") is False


# --------------------------------------------------------------------- #
# End-to-end lifecycle
# --------------------------------------------------------------------- #


def test_full_lifecycle_end_to_end(manager: PluginManager):
    manager.load("sample_plugin")
    manager.validate("sample_plugin")
    manager.initialize("sample_plugin")
    record = manager.unload("sample_plugin")

    assert record.state == PluginLifecycleState.UNLOADED
    assert manager.is_active("sample_plugin") is False


# --------------------------------------------------------------------- #
# Observability integration (ADR-0011 Observer pattern, ADR-0012 decision 5)
# --------------------------------------------------------------------- #


def test_observer_none_by_default_is_a_no_op(manager: PluginManager):
    # No observer supplied -- exercising the full lifecycle must not
    # raise, matching every other component's "observer is None" shape.
    manager.load("sample_plugin")
    manager.validate("sample_plugin")
    manager.initialize("sample_plugin")
    manager.unload("sample_plugin")


def test_observer_records_lifecycle_events(tmp_path: Path):
    recorder = InMemoryRecorder()
    manager = PluginManager(
        registry=_plugin_registry(tmp_path, _tool_plugin_entry()),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
        observer=recorder,
    )

    manager.load("sample_plugin")
    manager.validate("sample_plugin")
    manager.initialize("sample_plugin")
    manager.unload("sample_plugin")

    event_types = [event.event_type for event in recorder.events(component="plugin_manager")]
    assert event_types == [
        "plugin_loaded",
        "plugin_validated",
        "plugin_initialized",
        "plugin_unloaded",
    ]


def test_observer_records_validation_failure_event(tmp_path: Path):
    recorder = InMemoryRecorder()
    manager = PluginManager(
        registry=_plugin_registry(tmp_path, _tool_plugin_entry(min_aeos_version='"99.0.0"')),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
        observer=recorder,
    )

    manager.load("sample_plugin")
    with pytest.raises(PluginVersionIncompatibleError):
        manager.validate("sample_plugin")

    event_types = [event.event_type for event in recorder.events(component="plugin_manager")]
    assert "plugin_validation_failed" in event_types


def test_observer_records_lifecycle_transition_metrics(tmp_path: Path):
    recorder = InMemoryRecorder()
    manager = PluginManager(
        registry=_plugin_registry(tmp_path, _tool_plugin_entry()),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
        observer=recorder,
    )

    manager.load("sample_plugin")

    metrics = recorder.metrics(name="plugin_manager.lifecycle_transitions_total")
    assert len(metrics) == 1
    assert metrics[0].tags == {
        "plugin_name": "sample_plugin",
        "stage": "load",
        "outcome": "success",
    }


def test_observer_records_error_outcome_on_invalid_transition(tmp_path: Path):
    recorder = InMemoryRecorder()
    manager = PluginManager(
        registry=_plugin_registry(tmp_path, _tool_plugin_entry()),
        tool_registry=_tool_registry(tmp_path),
        provider_registry=_provider_registry(tmp_path),
        observer=recorder,
    )

    manager.load("sample_plugin")
    with pytest.raises(InvalidPluginStateTransitionError):
        manager.initialize("sample_plugin")

    metrics = recorder.metrics(name="plugin_manager.lifecycle_transitions_total")
    outcomes = [m.tags["outcome"] for m in metrics if m.tags["stage"] == "initialize"]
    assert outcomes == ["error"]
