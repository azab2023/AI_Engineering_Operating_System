"""Unit tests for orchestrator.observability.observability_registry.ObservabilityRegistry."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator.exceptions import ObservabilityRegistryError
from orchestrator.observability.observability_registry import (
    DEFAULT_OBSERVABILITY_PATH,
    ObservabilityRegistry,
)


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "observability.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_default_observability_file_loads_successfully():
    registry = ObservabilityRegistry(DEFAULT_OBSERVABILITY_PATH)
    config = registry.config()

    assert config.enabled is True
    assert config.record_metrics is True
    assert config.record_events is True
    assert config.timing_enabled is True


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(ObservabilityRegistryError, match="not found"):
        ObservabilityRegistry(tmp_path / "nonexistent.yaml")


def test_invalid_yaml_raises(tmp_path: Path):
    path = tmp_path / "observability.yaml"
    path.write_text("enabled: [this: is not, valid", encoding="utf-8")
    with pytest.raises(ObservabilityRegistryError, match="valid YAML"):
        ObservabilityRegistry(path)


def test_non_mapping_top_level_raises(tmp_path: Path):
    path = _write(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(ObservabilityRegistryError, match="mapping"):
        ObservabilityRegistry(path)


def test_empty_file_uses_all_defaults(tmp_path: Path):
    path = _write(tmp_path, "")
    config = ObservabilityRegistry(path).config()

    assert config.enabled is True
    assert config.record_metrics is True
    assert config.record_events is True
    assert config.timing_enabled is True


def test_partial_config_fills_remaining_defaults(tmp_path: Path):
    path = _write(tmp_path, "enabled: false\n")
    config = ObservabilityRegistry(path).config()

    assert config.enabled is False
    # untouched fields keep ObservabilityConfig's own defaults
    assert config.record_metrics is True
    assert config.record_events is True
    assert config.timing_enabled is True


def test_all_fields_explicit(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        enabled: true
        record_metrics: false
        record_events: true
        timing_enabled: false
        """,
    )
    config = ObservabilityRegistry(path).config()

    assert config.enabled is True
    assert config.record_metrics is False
    assert config.record_events is True
    assert config.timing_enabled is False


def test_non_boolean_field_raises(tmp_path: Path):
    path = _write(tmp_path, "enabled: 'yes'\n")
    with pytest.raises(ObservabilityRegistryError, match="enabled.*boolean"):
        ObservabilityRegistry(path)


def test_unknown_field_raises(tmp_path: Path):
    path = _write(tmp_path, "enabled: true\nexporter: prometheus\n")
    with pytest.raises(ObservabilityRegistryError, match="unknown"):
        ObservabilityRegistry(path)
