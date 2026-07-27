"""Unit tests for orchestrator.observability.manager.ObservabilityManager."""

from __future__ import annotations

from orchestrator.observability.manager import ObservabilityManager
from orchestrator.observability.models import ObservabilityConfig
from orchestrator.observability.recorder import InMemoryRecorder


def test_default_manager_loads_default_config_and_records():
    manager = ObservabilityManager()

    manager.record_event("tool_executor", "tool_executed", attributes={"tool_name": "read_file"})
    manager.record_metric("tool_executor.calls_total", 1, "counter", tags={"outcome": "success"})

    events = manager.get_events()
    metrics = manager.get_metrics()
    assert len(events) == 1
    assert events[0].component == "tool_executor"
    assert events[0].attributes == {"tool_name": "read_file"}
    assert len(metrics) == 1
    assert metrics[0].name == "tool_executor.calls_total"


def test_record_event_with_duration():
    manager = ObservabilityManager(recorder=InMemoryRecorder())

    manager.record_event("tool_executor", "tool_executed", duration_seconds=0.05)

    assert manager.get_events()[0].duration_seconds == 0.05


def test_get_events_and_metrics_support_filters():
    manager = ObservabilityManager(recorder=InMemoryRecorder())
    manager.record_event("orchestrator", "task_routed")
    manager.record_event("tool_executor", "tool_executed")
    manager.record_metric("orchestrator.routes_total", 1, "counter")
    manager.record_metric("tool_executor.calls_total", 1, "counter")

    assert len(manager.get_events(component="orchestrator")) == 1
    assert len(manager.get_metrics(name="tool_executor.calls_total")) == 1


def test_reset_clears_recorded_data():
    manager = ObservabilityManager(recorder=InMemoryRecorder())
    manager.record_event("orchestrator", "task_routed")
    manager.record_metric("orchestrator.routes_total", 1, "counter")

    manager.reset()

    assert manager.get_events() == []
    assert manager.get_metrics() == []


def test_disabled_config_records_nothing():
    manager = ObservabilityManager(config=ObservabilityConfig(enabled=False))

    manager.record_event("orchestrator", "task_routed")
    manager.record_metric("orchestrator.routes_total", 1, "counter")

    assert manager.get_events() == []
    assert manager.get_metrics() == []


def test_timing_enabled_reflects_config():
    assert ObservabilityManager(config=ObservabilityConfig()).timing_enabled() is True
    assert (
        ObservabilityManager(config=ObservabilityConfig(timing_enabled=False)).timing_enabled()
        is False
    )
    assert ObservabilityManager(config=ObservabilityConfig(enabled=False)).timing_enabled() is False


def test_manager_record_methods_are_observer_compatible_call_shape():
    """ObservabilityManager.record_event/record_metric accept the same
    kind of arguments every integrated component's private
    ``_observe_event``/``_observe_metric`` helper passes along -- so an
    ``ObservabilityManager`` works as a drop-in ``observer`` for
    ``Orchestrator``/``ExecutionEngine``/``ToolExecutor``/``WorkflowEngine``
    even though its own public method signatures are a friendlier,
    keyword-based convenience API rather than the raw
    ``ObservabilityRecorder.record_event(event: ObservabilityEvent)``
    Protocol shape (that raw shape is implemented by
    ``InMemoryRecorder``, which every ``ObservabilityManager`` wraps)."""
    manager = ObservabilityManager(recorder=InMemoryRecorder())

    manager.record_event("execution_engine", "execution_succeeded", attributes={"attempt": "1"})
    manager.record_metric(
        "execution_engine.attempts_total", 1, "counter", tags={"outcome": "success"}
    )

    assert len(manager.get_events()) == 1
    assert len(manager.get_metrics()) == 1
