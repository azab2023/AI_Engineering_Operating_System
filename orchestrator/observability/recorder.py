"""
orchestrator.observability.recorder
=======================================

``ObservabilityRecorder``: the Port every integrated component's new
``observer`` parameter (``Orchestrator``, ``ExecutionEngine``,
``ToolExecutor``, ``WorkflowEngine`` -- ADR-0011 decision 5) is typed
against. Deliberately minimal: two methods, matching exactly the two
things a component needs to do. Not a context manager, not a generic
``emit()`` -- each call site already knows whether it has an event or
a metric to record.

Depending on this Protocol rather than ``InMemoryRecorder`` directly is
what lets a future persistent recorder (ADR-0011 Follow-up) become a
drop-in replacement with zero changes to any integrated component.

``InMemoryRecorder`` is the sole Phase-13 implementation -- explicit
Storage decision: in-memory only, no SQLite reuse this phase.
"""

from __future__ import annotations

from typing import Protocol

from orchestrator.exceptions import InvalidMetricTypeError
from orchestrator.observability.models import MetricPoint, ObservabilityConfig, ObservabilityEvent

_VALID_METRIC_TYPES = {"counter", "timer"}


class ObservabilityRecorder(Protocol):
    """Port: anything that can record a structured event or a metric."""

    def record_event(self, event: ObservabilityEvent) -> None:
        """Record a structured event. Implementations must be safe to
        call unconditionally -- a disabled/no-op configuration is
        expressed by silently discarding the event, not by raising."""
        ...

    def record_metric(self, metric: MetricPoint) -> None:
        """Record a counter or timer measurement.

        Raises:
            InvalidMetricTypeError: ``metric.metric_type`` is not
                ``"counter"`` or ``"timer"``.
        """
        ...


class InMemoryRecorder:
    """In-memory ``ObservabilityRecorder``: appends to two in-process
    lists, filtered by an ``ObservabilityConfig``.

    Config gating lives here (not in each calling component), so
    ``enabled`` / ``record_events`` / ``record_metrics`` behave
    identically no matter which component recorded the data -- a
    component never needs to know or check the config itself.

    Args:
        config: governs whether recording actually happens. Defaults
            to ``ObservabilityConfig()`` (everything enabled) when not
            given.
    """

    def __init__(self, config: ObservabilityConfig | None = None):
        self._config = config or ObservabilityConfig()
        self._events: list[ObservabilityEvent] = []
        self._metrics: list[MetricPoint] = []

    def record_event(self, event: ObservabilityEvent) -> None:
        if not (self._config.enabled and self._config.record_events):
            return
        self._events.append(event)

    def record_metric(self, metric: MetricPoint) -> None:
        if not (self._config.enabled and self._config.record_metrics):
            return
        if metric.metric_type not in _VALID_METRIC_TYPES:
            raise InvalidMetricTypeError(metric.name, metric.metric_type)
        self._metrics.append(metric)

    def events(
        self, component: str | None = None, event_type: str | None = None
    ) -> list[ObservabilityEvent]:
        """Return recorded events, most-recent-last, optionally filtered
        by ``component`` and/or ``event_type``."""
        results = self._events
        if component is not None:
            results = [e for e in results if e.component == component]
        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        return list(results)

    def metrics(self, name: str | None = None, metric_type: str | None = None) -> list[MetricPoint]:
        """Return recorded metrics, most-recent-last, optionally
        filtered by ``name`` and/or ``metric_type``."""
        results = self._metrics
        if name is not None:
            results = [m for m in results if m.name == name]
        if metric_type is not None:
            results = [m for m in results if m.metric_type == metric_type]
        return list(results)

    def reset(self) -> None:
        """Discard all recorded events and metrics."""
        self._events.clear()
        self._metrics.clear()
