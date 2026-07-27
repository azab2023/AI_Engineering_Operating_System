"""
orchestrator.observability.models
=====================================

Plain frozen dataclasses for the Phase-13 (ADR-0011) observability
package: no external validation library, matching every prior phase's
``models.py``.

``MetricPoint.metric_type`` is deliberately a plain ``str`` rather than
an enum -- it is validated once, at the single place a metric is
actually recorded (``orchestrator.observability.recorder.InMemoryRecorder
.record_metric``), the same "validate at the boundary, not in the
model" split ADR-0010 used for ``ToolDefinition.access_mode``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ObservabilityEvent:
    """A single, discrete, typed occurrence recorded by an integrated
    component (e.g. "a tool ran", "a workflow step failed").

    Args:
        component: the recording component's identifier (e.g.
            ``"orchestrator"``, ``"execution_engine"``, ``"tool_executor"``,
            ``"workflow_engine"``).
        event_type: what happened, in ``snake_case`` (e.g.
            ``"tool_executed"``).
        attributes: free-form string key/value context for this event
            (e.g. ``execution_id``, ``tool_name``, ``outcome``).
        duration_seconds: how long the observed operation took, if
            applicable and known. ``None`` when not timed.
        timestamp: when this event was recorded. Defaults to now (UTC).
    """

    component: str
    event_type: str
    attributes: dict[str, str] = field(default_factory=dict)
    duration_seconds: float | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class MetricPoint:
    """A single counter or timer measurement.

    Args:
        name: the metric's dotted name (e.g.
            ``"tool_executor.calls_total"``).
        value: the measurement -- an increment for a ``"counter"``, a
            duration in seconds for a ``"timer"``.
        metric_type: ``"counter"`` or ``"timer"``. Validated by
            ``InMemoryRecorder.record_metric``, not here -- see module
            docstring.
        tags: free-form string key/value dimensions for this
            measurement (e.g. ``tool_name``, ``outcome``).
        timestamp: when this metric was recorded. Defaults to now (UTC).
    """

    name: str
    value: float
    metric_type: str
    tags: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ObservabilityConfig:
    """Validated view of ``config/observability.yaml``.

    Every field is an independent boolean toggle with a safe default
    (``True``) -- unlike ``PermissionPolicy.path_sandbox``, no field
    here has a structural absence that would need rejecting outright.
    See ADR-0011 decision 4.

    Args:
        enabled: master switch. When ``False``, neither events nor
            metrics are recorded regardless of the other three fields.
        record_metrics: whether ``InMemoryRecorder.record_metric``
            actually stores metrics it is given.
        record_events: whether ``InMemoryRecorder.record_event``
            actually stores events it is given.
        timing_enabled: whether integrated components measure and
            attach ``duration_seconds`` / timer metrics at all. Read
            and honored by each integrated component itself (not by
            the recorder), since the recorder has no way to retroactively
            "un-measure" a duration a caller already computed.
    """

    enabled: bool = True
    record_metrics: bool = True
    record_events: bool = True
    timing_enabled: bool = True
