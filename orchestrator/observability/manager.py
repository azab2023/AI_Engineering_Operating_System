"""
orchestrator.observability.manager
======================================

``ObservabilityManager``: a facade over ``InMemoryRecorder`` +
``ObservabilityConfig``, mirroring how
``orchestrator.memory.memory_manager.MemoryManager`` (Phase-10) is a
facade over a ``MemoryStore`` with higher-level operations added on
top.

Note: unlike ``MemoryManager`` (which *is* a drop-in caller of the
``MemoryStore`` Protocol it wraps), ``ObservabilityManager`` exposes a
friendlier, keyword-based convenience API rather than the raw
``ObservabilityRecorder`` Protocol shape (``record_event(event:
ObservabilityEvent)``) -- so it is *not* interchangeable with
``ObservabilityRecorder`` and cannot itself be passed as the
``observer`` argument of ``Orchestrator``/``ExecutionEngine``/
``ToolExecutor``/``WorkflowEngine``. Those are typed against
``ObservabilityRecorder`` directly and satisfied by ``InMemoryRecorder``.
``ObservabilityManager`` is the facade an external caller (tests, or a
future reporting surface) uses to record and query data through.
"""

from __future__ import annotations

from orchestrator.observability.models import MetricPoint, ObservabilityConfig, ObservabilityEvent
from orchestrator.observability.observability_registry import ObservabilityRegistry
from orchestrator.observability.recorder import InMemoryRecorder


class ObservabilityManager:
    """Facade for recording and querying structured events and metrics.

    Args:
        config: governs whether recording happens at all. Defaults to
            an ``ObservabilityRegistry()`` loaded from the default
            ``config/observability.yaml`` path.
        recorder: the storage backend. Defaults to
            ``InMemoryRecorder(config)`` -- Phase-13's only supported
            backend (see ADR-0011 Storage decision). Pass a different
            ``InMemoryRecorder`` instance to share recorded data across
            multiple ``ObservabilityManager`` facades if ever needed.
    """

    def __init__(
        self,
        config: ObservabilityConfig | None = None,
        recorder: InMemoryRecorder | None = None,
    ):
        self._config = config or ObservabilityRegistry().config()
        self._recorder = recorder or InMemoryRecorder(self._config)

    def record_event(
        self,
        component: str,
        event_type: str,
        attributes: dict[str, str] | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        self._recorder.record_event(
            ObservabilityEvent(
                component=component,
                event_type=event_type,
                attributes=attributes or {},
                duration_seconds=duration_seconds,
            )
        )

    def record_metric(
        self,
        name: str,
        value: float,
        metric_type: str = "counter",
        tags: dict[str, str] | None = None,
    ) -> None:
        self._recorder.record_metric(
            MetricPoint(name=name, value=value, metric_type=metric_type, tags=tags or {})
        )

    def timing_enabled(self) -> bool:
        """Whether integrated components should measure/attach
        durations at all (``enabled`` and ``timing_enabled`` both
        ``True``)."""
        return self._config.enabled and self._config.timing_enabled

    def get_events(
        self, component: str | None = None, event_type: str | None = None
    ) -> list[ObservabilityEvent]:
        return self._recorder.events(component, event_type)

    def get_metrics(
        self, name: str | None = None, metric_type: str | None = None
    ) -> list[MetricPoint]:
        return self._recorder.metrics(name, metric_type)

    def reset(self) -> None:
        """Discard all recorded events and metrics."""
        self._recorder.reset()
