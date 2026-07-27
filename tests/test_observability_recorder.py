"""Unit tests for orchestrator.observability.recorder.InMemoryRecorder."""

from __future__ import annotations

import pytest

from orchestrator.exceptions import InvalidMetricTypeError
from orchestrator.observability.models import MetricPoint, ObservabilityConfig, ObservabilityEvent
from orchestrator.observability.recorder import InMemoryRecorder


def _event(
    component: str = "tool_executor", event_type: str = "tool_executed"
) -> ObservabilityEvent:
    return ObservabilityEvent(component=component, event_type=event_type)


def _metric(name: str = "tool_executor.calls_total", metric_type: str = "counter") -> MetricPoint:
    return MetricPoint(name=name, value=1, metric_type=metric_type)


def test_default_config_records_everything():
    recorder = InMemoryRecorder()

    recorder.record_event(_event())
    recorder.record_metric(_metric())

    assert len(recorder.events()) == 1
    assert len(recorder.metrics()) == 1


def test_enabled_false_records_nothing_regardless_of_other_flags():
    config = ObservabilityConfig(enabled=False, record_events=True, record_metrics=True)
    recorder = InMemoryRecorder(config)

    recorder.record_event(_event())
    recorder.record_metric(_metric())

    assert recorder.events() == []
    assert recorder.metrics() == []


def test_record_events_false_suppresses_events_only():
    config = ObservabilityConfig(record_events=False)
    recorder = InMemoryRecorder(config)

    recorder.record_event(_event())
    recorder.record_metric(_metric())

    assert recorder.events() == []
    assert len(recorder.metrics()) == 1


def test_record_metrics_false_suppresses_metrics_only():
    config = ObservabilityConfig(record_metrics=False)
    recorder = InMemoryRecorder(config)

    recorder.record_event(_event())
    recorder.record_metric(_metric())

    assert len(recorder.events()) == 1
    assert recorder.metrics() == []


def test_invalid_metric_type_raises():
    recorder = InMemoryRecorder()

    with pytest.raises(InvalidMetricTypeError):
        recorder.record_metric(_metric(metric_type="gauge"))


def test_invalid_metric_type_not_recorded_when_disabled():
    """A disabled recorder never even reaches the metric_type check --
    recording is a pure no-op, not a validate-then-discard."""
    config = ObservabilityConfig(record_metrics=False)
    recorder = InMemoryRecorder(config)

    recorder.record_metric(_metric(metric_type="gauge"))  # must not raise

    assert recorder.metrics() == []


def test_events_filtered_by_component_and_event_type():
    recorder = InMemoryRecorder()
    recorder.record_event(_event(component="tool_executor", event_type="tool_executed"))
    recorder.record_event(_event(component="workflow_engine", event_type="workflow_run_started"))
    recorder.record_event(_event(component="tool_executor", event_type="tool_execution_failed"))

    assert len(recorder.events(component="tool_executor")) == 2
    assert len(recorder.events(event_type="tool_executed")) == 1
    assert len(recorder.events(component="tool_executor", event_type="tool_executed")) == 1


def test_metrics_filtered_by_name_and_type():
    recorder = InMemoryRecorder()
    recorder.record_metric(_metric(name="tool_executor.calls_total", metric_type="counter"))
    recorder.record_metric(
        _metric(name="tool_executor.execution_duration_seconds", metric_type="timer")
    )

    assert len(recorder.metrics(name="tool_executor.calls_total")) == 1
    assert len(recorder.metrics(metric_type="timer")) == 1


def test_reset_clears_both_events_and_metrics():
    recorder = InMemoryRecorder()
    recorder.record_event(_event())
    recorder.record_metric(_metric())

    recorder.reset()

    assert recorder.events() == []
    assert recorder.metrics() == []
