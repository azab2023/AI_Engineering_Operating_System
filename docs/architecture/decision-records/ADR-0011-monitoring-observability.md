# ADR-0011: Monitoring & Observability (Phase-13)

- **Status:** Accepted
- **Date:** Phase-13
- **Deciders:** Lead AI Systems Architect

## Context

`PROJECT_ROADMAP.md` lists Phase-13 as "Monitoring & Observability"
with no prior deferral pointing at a concrete scope (unlike Phase-12,
which closed two named ADR-0007/Phase-02 deferrals). The scope was
therefore proposed by this ADR's author and explicitly approved by the
project owner before any code was written:

**In scope:**
- Structured events (discrete, typed occurrences: a task was routed,
  a tool ran, a workflow step failed, ...).
- Metrics (counters and timers).
- Timing / duration measurements for the operations that already do
  meaningful work (agent invocation, tool execution, workflow runs).

**Explicitly out of scope** (deferred, not designed against here):
health-check endpoints, Prometheus, OpenTelemetry, external exporters,
dashboards, HTTP monitoring APIs. This phase is internal observability
only — a way for AEOS itself, and its tests, to see what happened
inside a process. Nothing here talks to the network.

Two things already exist that this phase must not duplicate or
conflict with:

1. **`orchestrator/logging_setup.py`** — the single centralized
   `get_logger()` used by every module today for free-text log lines.
   Observability here is a distinct, structured, queryable concern
   (events/metrics as data, not log strings) and does not replace or
   wrap logging; both continue to exist side by side, exactly as
   `ExecutionEngine.execute()` already calls `logger.warning(...)` and
   will continue to.
2. **The "optional-parameter-defaulting-to-unchanged-behavior" shape**
   every prior phase's integration has used: Phase-12's
   `agent_name: str | None = None` on `ToolExecutor.execute()` and
   `WorkflowStep.agent_name`, Phase-07's `HttpAgentInvoker` as an
   *alternative* `AgentInvoker` rather than a replacement. Phase-13
   reuses this exact shape rather than inventing a new integration
   style.

## Decision

### 1. New `orchestrator/observability/` package, mirroring the `security/`/`memory/` shape

```
orchestrator/observability/
├── __init__.py
├── models.py                   # ObservabilityEvent, MetricPoint, ObservabilityConfig
├── recorder.py                  # ObservabilityRecorder Protocol (Port) + InMemoryRecorder
├── observability_registry.py     # loads config/observability.yaml -> ObservabilityConfig
└── manager.py                     # ObservabilityManager facade
```

Four modules instead of three (`security/`'s count) because, unlike
`PermissionPolicy` (one config object, one enforcement class),
observability needs a Port (`ObservabilityRecorder`) that other
packages' components type their new parameter against, kept separate
from the Facade (`ObservabilityManager`) that owns config + a default
recorder + convenience/query methods — see decision 3 for why these
are two different types.

### 2. `models.py`: three plain frozen dataclasses, no pydantic

```python
@dataclass(frozen=True)
class ObservabilityEvent:
    component: str
    event_type: str
    attributes: dict[str, str] = field(default_factory=dict)
    duration_seconds: float | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class MetricPoint:
    name: str
    value: float
    metric_type: str  # "counter" | "timer"
    tags: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ObservabilityConfig:
    enabled: bool = True
    record_metrics: bool = True
    record_events: bool = True
    timing_enabled: bool = True
```

Same bar as every prior phase's `models.py` (`PathSandboxPolicy`,
`MemoryEntry`, `ToolResult`, ...): plain dataclasses, no external
validation library. `MetricPoint.metric_type` is deliberately a plain
`str`, not an enum — validated once, at the single place a metric is
actually recorded (`InMemoryRecorder.record_metric`, decision 4), the
same "validate at the boundary, not in the model" split ADR-0010 used
for `ToolDefinition.access_mode`.

### 3. `recorder.py`: `ObservabilityRecorder` Protocol (the type every other component's new parameter is typed against) + `InMemoryRecorder`

```python
class ObservabilityRecorder(Protocol):
    def record_event(self, event: ObservabilityEvent) -> None: ...
    def record_metric(self, metric: MetricPoint) -> None: ...
```

Deliberately minimal — two methods, matching exactly the two things
components need to do (decision 5). Not a context manager, not a
generic `emit()`; each call site already knows whether it has an
event or a metric to record. This is the Port every existing
component's new `observer` parameter (decision 5) is typed against —
by design, `Orchestrator`/`ExecutionEngine`/`ToolExecutor`/
`WorkflowEngine` depend only on this Protocol, never on
`InMemoryRecorder` or `ObservabilityManager` directly, so a future
persistent recorder (Follow-up) is a drop-in replacement with zero
changes to any of those four files.

`InMemoryRecorder` is the sole Phase-13 implementation — Storage
decision (approved): in-memory only, no SQLite reuse.

```python
class InMemoryRecorder:
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

    def events(self, component=None, event_type=None) -> list[ObservabilityEvent]: ...
    def metrics(self, name=None, metric_type=None) -> list[MetricPoint]: ...
    def reset(self) -> None: ...
```

Config gating lives in the recorder (not in each calling component),
so `enabled` / `record_events` / `record_metrics` behave identically
no matter which component recorded the data — a component never needs
to know or check the config itself; it only ever needs to know
"do I have an observer or not" (decision 5).

### 4. `observability_registry.py`: `ObservabilityRegistry`, same fail-loud config-loading shape as `PermissionRegistry`/`ToolRegistry`

```python
class ObservabilityRegistry:
    def __init__(self, registry_path=DEFAULT_OBSERVABILITY_PATH):
        self._config = self._load()

    def config(self) -> ObservabilityConfig: ...
```

`config/observability.yaml`:

```yaml
enabled: true
record_metrics: true
record_events: true
timing_enabled: true
```

All four keys are optional (a config file with only `enabled: false`
is valid — the other three default to `True`, matching
`ObservabilityConfig`'s dataclass defaults); this is the one
deliberate deviation from `PermissionRegistry`'s all-required-fields
posture, because every key here is an independent boolean toggle with
an obvious, safe default, not a structural field like
`path_sandbox.allowed_roots` whose absence has no sane default.
`ObservabilityRegistryError` is still raised loudly for: missing file,
invalid YAML, a non-mapping document, or any present key whose value
is not a boolean — silently coercing a malformed value is exactly the
class of bug this project's fail-loud philosophy exists to prevent.

### 5. `manager.py`: `ObservabilityManager` facade + the Observer-pattern integration into four existing components

```python
class ObservabilityManager:
    def __init__(
        self,
        config: ObservabilityConfig | None = None,
        recorder: InMemoryRecorder | None = None,
    ):
        self._config = config or ObservabilityRegistry().config()
        self._recorder = recorder or InMemoryRecorder(self._config)

    def record_event(
        self, component, event_type, attributes=None, duration_seconds=None
    ) -> None: ...
    def record_metric(self, name, value, metric_type="counter", tags=None) -> None: ...
    def get_events(self, component=None, event_type=None) -> list[ObservabilityEvent]: ...
    def get_metrics(self, name=None, metric_type=None) -> list[MetricPoint]: ...
    def reset(self) -> None: ...
```

`ObservabilityManager` wraps an `InMemoryRecorder` and exposes a
friendlier, keyword-based convenience API (`record_event(component,
event_type, attributes=None, duration_seconds=None)`) rather than the
raw `ObservabilityRecorder.record_event(event: ObservabilityEvent)`
Protocol shape — the two are **not** interchangeable at the type level;
an `ObservabilityManager` cannot be passed as the `observer` argument
of `Orchestrator`/`ExecutionEngine`/`ToolExecutor`/`WorkflowEngine`
(those expect the raw Protocol, satisfied by `InMemoryRecorder`
itself). `ObservabilityManager` is instead the facade an external
caller (a test, or a future reporting/CLI surface) uses to record and
query data through, mirroring exactly how `MemoryManager` (Phase-10)
is a facade over a `MemoryStore` with `remember`/`recall`/`forget`
added on top, not a `MemoryStore` implementation itself.

**Integration (Observer pattern, exactly as approved):** four existing
components each gain one new, optional, defaulted constructor
parameter and nothing else changes about their signatures:

| Component | New parameter | Events recorded | Metric(s) recorded |
|---|---|---|---|
| `Orchestrator` (`core.py`) | `observer: ObservabilityRecorder \| None = None` | `task_routed`, `route_failed`, `execution_awaiting_approval`, `execution_approved`, `execution_failed` | counter `orchestrator.routes_total` (tag `outcome`) |
| `ExecutionEngine` (`execution/engine.py`) | `observer: ObservabilityRecorder \| None = None` | `invocation_attempt_failed`, `execution_succeeded`, `execution_retries_exhausted` | counter `execution_engine.attempts_total` (tag `outcome`), timer `execution_engine.invocation_duration_seconds` |
| `ToolExecutor` (`tools/tool_executor.py`) | `observer: ObservabilityRecorder \| None = None` | `tool_executed`, `tool_execution_failed` | counter `tool_executor.calls_total` (tags `tool_name`, `outcome`), timer `tool_executor.execution_duration_seconds` (reuses the `ToolResult.duration_seconds` a `Tool` already computes — no new timing code) |
| `WorkflowEngine` (`workflow/workflow_engine.py`) | `observer: ObservabilityRecorder \| None = None` | `workflow_run_started`, `workflow_run_completed`, `workflow_run_failed` | counter `workflow_engine.runs_total` (tag `outcome`), timer `workflow_engine.run_duration_seconds` |

These four were chosen as the minimum necessary set (same framing as
ADR-0010 decision 9's "minimum necessary Phase-11 touches"): they are
the components that already do the meaningful work this phase exists
to observe — task routing/state transitions, agent invocation
attempts/retries, tool runs, and workflow orchestration. Every other
existing class (`AgentRegistry`, `ModelProvider` adapters,
`PromptManager`, `MemoryManager`, `ToolAuthorizer`, ...) is left
untouched this phase; see Follow-up.

Each integration follows the same shape, e.g. `ExecutionEngine`:

```python
def __init__(
    self,
    orchestrator: Orchestrator,
    invoker: AgentInvoker | None = None,
    retry_policy: RetryPolicy | None = None,
    observer: ObservabilityRecorder | None = None,
):
    ...
    self._observer = observer


def _observe_event(self, event_type: str, **attributes: str) -> None:
    if self._observer is None:
        return
    self._observer.record_event(
        ObservabilityEvent(
            component="execution_engine", event_type=event_type, attributes=attributes
        )
    )


def _observe_metric(self, name: str, value: float, metric_type: str, **tags: str) -> None:
    if self._observer is None:
        return
    self._observer.record_metric(
        MetricPoint(name=name, value=value, metric_type=metric_type, tags=tags)
    )
```

`observer is None` (the default) is checked once, at the top of each
private helper, and every call to the helper is itself unconditional
in the surrounding logic — no call site needs its own `if self._observer`
branch, and when `observer` is not supplied the two helpers are the
only new code that ever runs (two attribute reads and a return),
matching ADR-0010's "the smallest change that adds the capability
without breaking anything that predates it."

Timing is measured locally in each component with `time.perf_counter()`
around the operation being timed (`ExecutionEngine`/`WorkflowEngine`)
or reused from an already-computed value (`ToolExecutor` reusing
`ToolResult.duration_seconds`) — no shared timing-context-manager
abstraction is introduced in `ObservabilityRecorder` itself, keeping
the Port to the two methods in decision 3.

### 6. New `ObservabilityError(OrchestratorError)` base, two concrete subclasses

```python
class ObservabilityError(OrchestratorError): ...


class ObservabilityRegistryError(
    ObservabilityError
): ...  # config/observability.yaml load/validation


class InvalidMetricTypeError(
    ObservabilityError
): ...  # MetricPoint.metric_type not in {"counter", "timer"}
```

Mirrors every prior phase's own `XError(OrchestratorError)` base plus
a config-loading subclass (`ToolRegistryError`,
`ModelProviderRegistryError`, `PermissionRegistryError`, ...).
`InvalidMetricTypeError` is raised only by `InMemoryRecorder.record_metric()`,
never by application code paths a caller can reach through normal use
of the four integrated components (they only ever pass
`metric_type="counter"` or `"timer"`) — it exists to fail loudly on a
future coding mistake (a fifth component recording an unsupported
metric type), not on any input this phase's own call sites can
produce.

## Alternatives Considered

- **A single `ObservabilityManager` type used directly as the
  `observer` parameter everywhere**, instead of a separate
  `ObservabilityRecorder` Protocol. Rejected: this would couple every
  integrated component to `ObservabilityManager`'s config-loading and
  query surface, when all any of them actually needs is "record an
  event / record a metric." Mirrors why `MemoryManager` (Phase-10)
  depends on the `MemoryStore` Protocol rather than every future
  caller depending on `MemoryManager` for storage.
- **A shared `time_operation()` context manager on `ObservabilityRecorder`**
  (`with observer.time_operation("x"): ...`). Rejected for this phase
  — it enlarges the Port beyond the two methods every integration
  actually needs, and `ToolExecutor` already has a pre-computed
  duration (`ToolResult.duration_seconds`) it would have to route
  around such an abstraction rather than through it. Local
  `time.perf_counter()` timing in the two components that need it
  (`ExecutionEngine`, `WorkflowEngine`) is the smaller change.
- **Reusing `orchestrator/persistence` (SQLite) for metrics/event
  storage**, matching how Phase-10's `SQLiteMemoryStore` reused
  `persistence.db.connect()`. Rejected for this phase — explicit
  Storage decision: in-memory only; noted as a Follow-up instead.
- **Making `observer` a required constructor argument.** Rejected —
  breaks every existing call site across four files and all of their
  existing tests, which "fully backward compatible" rules out; same
  reasoning ADR-0010 applied to `agent_name`.
- **Wiring observability into `ModelProvider` adapters and both
  `AgentInvoker` implementations this phase**, for HTTP/CLI-level
  timing. Rejected for now to keep the touched surface to the four
  components that already sit at natural aggregation points
  (`ExecutionEngine` already wraps every invoker call in a retry loop;
  observing there captures invoker-level timing transitively without
  a fifth and sixth file changing). Left as Follow-up.

## Consequences

### Positive

- All three approved capabilities delivered: structured events,
  counter/timer metrics, and duration measurements, entirely in-process
  and in-memory, with zero network surface.
- Fully backward compatible: every new parameter defaults to `None`
  and reproduces pre-Phase-13 behavior exactly when omitted; the
  `orchestrator/observability/` package itself has no call sites
  outside itself creating implicit behavior — it is opt-in everywhere.
- Open/Closed for storage: components depend on the
  `ObservabilityRecorder` Protocol, not `InMemoryRecorder` — a future
  persistent recorder needs no change to `Orchestrator`,
  `ExecutionEngine`, `ToolExecutor`, or `WorkflowEngine`.
- `ObservabilityManager` gives a single, testable place to inspect
  what a test run recorded (`get_events()` / `get_metrics()`),
  supporting comprehensive unit tests without any component needing
  test-only instrumentation.

### Negative

- Four existing files gain new, additive surface area; a future
  reviewer needs to know the pattern (`observer is None -> no-op`) is
  intentional and repeated by design, not duplicated by accident.
- `ModelProvider` adapters and `AgentInvoker` implementations remain
  unobserved this phase — a slower provider call is only visible
  transitively through `ExecutionEngine`'s attempt-level timing, not
  as its own metric.
- In-memory-only storage means all recorded data is lost when the
  process exits; there is no cross-run observability yet.

## Follow-up

- A persistent recorder (e.g. reusing `orchestrator/persistence`) can
  be added as a second `ObservabilityRecorder` implementation in a
  future phase with no change to any of the four integrated
  components, exactly as `SQLiteMemoryStore` was added alongside
  `InMemoryStore` in Phase-10.
- Extending observation to `ModelProvider` adapters and both
  `AgentInvoker` implementations, if provider/CLI-level granularity is
  ever needed beyond `ExecutionEngine`'s attempt-level view.
- External exporters (Prometheus, OpenTelemetry), health-check
  endpoints, dashboards, or an HTTP monitoring API are all explicitly
  out of scope for this phase and would each be their own future ADR.
