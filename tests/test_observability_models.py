"""Unit tests for orchestrator.observability.models."""

from __future__ import annotations

from orchestrator.observability.models import MetricPoint, ObservabilityConfig, ObservabilityEvent


def test_observability_event_defaults():
    event = ObservabilityEvent(component="tool_executor", event_type="tool_executed")

    assert event.attributes == {}
    assert event.duration_seconds is None
    assert event.timestamp.tzinfo is not None


def test_observability_event_carries_attributes_and_duration():
    event = ObservabilityEvent(
        component="tool_executor",
        event_type="tool_executed",
        attributes={"tool_name": "read_file"},
        duration_seconds=0.02,
    )

    assert event.attributes == {"tool_name": "read_file"}
    assert event.duration_seconds == 0.02


def test_metric_point_defaults():
    metric = MetricPoint(name="tool_executor.calls_total", value=1, metric_type="counter")

    assert metric.tags == {}
    assert metric.timestamp.tzinfo is not None


def test_observability_config_defaults_all_true():
    config = ObservabilityConfig()

    assert config.enabled is True
    assert config.record_metrics is True
    assert config.record_events is True
    assert config.timing_enabled is True


def test_observability_config_is_frozen():
    config = ObservabilityConfig()
    try:
        config.enabled = False  # type: ignore[misc]
        raised = False
    except Exception:  # noqa: BLE001 - dataclasses.FrozenInstanceError
        raised = True
    assert raised
