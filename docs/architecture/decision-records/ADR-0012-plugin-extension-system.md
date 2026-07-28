# ADR-0012: Plugin & Extension System (Phase-14)

- **Status:** Accepted
- **Date:** Phase-14
- **Deciders:** Lead AI Systems Architect

## Context

`PROJECT_ROADMAP.md` lists Phase-14 as "Plugin & Extension System" with
no prior deferral pointing at a concrete scope (the same situation
ADR-0011 documented for Phase-13). Repository analysis found no other
mention of "plugin" anywhere in the codebase, config, or any prior ADR
— the scope was therefore explicitly proposed and approved by the
project owner before any code was written:

**In scope:**
- A metadata model describing one plugin: what it is, what existing
  extension point it activates, and which AEOS versions it is
  compatible with.
- A config-driven registry (`config/plugins.yaml`), mirroring every
  prior phase's registry.
- A lifecycle facade (`PluginManager`) with four explicit stages:
  **load -> validate -> initialize -> unload**.
- Version-compatibility validation against the running AEOS version.
- Discovery limited to project-managed entries in `config/plugins.yaml`
  — no external package installation, no `importlib`/`entry_points`
  scanning.

**Explicitly out of scope** (deferred, not designed against here):
loading or executing arbitrary plugin-supplied Python code, a
`PluginFactory` that instantiates new `Tool`/`ModelProvider`
implementations, pip-installable plugins, and persistent
(cross-restart) plugin state. This phase does not introduce a new
execution path of any kind — see decision 5.

Two things already exist that this phase must not duplicate,
conflict with, or bypass:

1. **`ToolFactory` / `ProviderFactory`** (Phase-09 / Phase-07) — the
   existing Open/Closed extension points. A "plugin" in this phase is
   not a competing mechanism for adding a new `Tool`/`ModelProvider`
   implementation; it is a thin metadata wrapper that activates or
   deactivates an *already-registered* `tool_name` (`config/tools.yaml`)
   or provider agent (`config/model_providers.yaml`). Extending
   `ToolFactory`/`ProviderFactory` themselves remains exactly as
   defined in ADR-0007 decision 4 / ADR-0005 decision 8 — unchanged by
   this phase.
2. **`ToolAuthorizer`** (Phase-12) and the Observer-pattern
   integration shape (Phase-13, ADR-0011 decision 5) — the plugin
   system must integrate with both without bypassing either.

## Decision

### 1. New `orchestrator/plugins/` package, mirroring the `observability/`/`security/` shape

```
orchestrator/plugins/
├── __init__.py
├── models.py            # PluginExtensionType, PluginLifecycleState, PluginMetadata, PluginRecord
├── plugin_registry.py    # loads config/plugins.yaml -> PluginMetadata
└── plugin_manager.py      # PluginManager facade: load/validate/initialize/unload
```

Three modules, not four: unlike Phase-13's split between a Port
(`ObservabilityRecorder`) and a Facade (`ObservabilityManager`), there
is no new Port here — a plugin never gets instantiated into a running
object the way a `Tool`/`ModelProvider` does (see Context, item 1), so
there is nothing for a Protocol to abstract over. `PluginManager` plays
the same role `ToolExecutor` (Phase-09) and `MemoryManager` (Phase-10)
play: the sole Facade a caller is expected to depend on.

### 2. `models.py`: two enums, two plain frozen/mutable dataclasses, no pydantic

```python
class PluginExtensionType(str, Enum):
    TOOL = "tool"
    PROVIDER = "provider"


class PluginLifecycleState(str, Enum):
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    INITIALIZED = "initialized"
    UNLOADED = "unloaded"


@dataclass(frozen=True)
class PluginMetadata:
    plugin_name: str
    version: str
    description: str
    enabled: bool
    extension_type: PluginExtensionType
    target_name: str
    min_aeos_version: str
    max_aeos_version: str | None = None


@dataclass
class PluginRecord:
    plugin_name: str
    metadata: PluginMetadata
    state: PluginLifecycleState = PluginLifecycleState.DISCOVERED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

Exactly two extension types this phase — `tool` and `provider` — the
two existing Open/Closed points documented in ADR-0007/ADR-0005.
`target_name` means "the `tool_name` in `config/tools.yaml`" when
`extension_type == TOOL`, or "the agent name in
`config/model_providers.yaml`" when `extension_type == PROVIDER`.
`PluginMetadata.__post_init__` validates non-empty strings and that
`min_aeos_version`/`max_aeos_version` (when present) match a strict
`MAJOR.MINOR.PATCH` shape — validated once, at the model boundary,
matching every prior phase's models.py convention.

`PluginRecord` is mutable, mirroring `WorkflowRun` (Phase-11): it is
the thing whose `state` field actually moves through the lifecycle;
`PluginMetadata` itself stays an immutable, config-derived value,
exactly like `WorkflowDefinition` stays immutable while `WorkflowRun`
tracks progress against it.

### 3. `plugin_registry.py`: `PluginRegistry`, same fail-loud config-loading shape as `ToolRegistry`

```python
class PluginRegistry:
    def __init__(self, registry_path=DEFAULT_PLUGINS_PATH):
        self._definitions: dict[str, PluginMetadata] = {}
        self._load()

    def get_definition(self, plugin_name: str) -> PluginMetadata: ...
    def is_enabled(self, plugin_name: str) -> bool: ...
```

`config/plugins.yaml`:

```yaml
plugins:
  read_file_plugin:
    version: "1.0.0"
    description: "Activates the built-in read_file tool as a managed plugin."
    enabled: true
    extension_type: tool
    target_name: read_file
    min_aeos_version: "1.3.0"
    max_aeos_version: null
```

Configuration loading, validation, and per-plugin lookup only —
identical responsibility boundary to `ToolRegistry`/`ModelProviderRegistry`
(ADR-0007 decision 3 / ADR-0005 decision 3): this module never checks
whether `target_name` actually exists elsewhere — that cross-registry
check is `PluginManager.validate()`'s job (decision 4), exactly as
resolving a `tool_type` to a concrete class was deliberately kept out
of `ToolRegistry` and left to `ToolFactory`.

### 4. `plugin_manager.py`: `PluginManager` facade — the four-stage lifecycle

```python
class PluginManager:
    def __init__(
        self,
        registry: PluginRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
        provider_registry: ModelProviderRegistry | None = None,
        observer: ObservabilityRecorder | None = None,
    ): ...

    def load(self, plugin_name: str) -> PluginRecord: ...
    def validate(self, plugin_name: str) -> PluginRecord: ...
    def initialize(self, plugin_name: str) -> PluginRecord: ...
    def unload(self, plugin_name: str) -> PluginRecord: ...

    def get(self, plugin_name: str) -> PluginRecord: ...
    def list_plugins(self) -> list[PluginRecord]: ...
    def is_active(self, plugin_name: str) -> bool: ...
```

Each stage is an explicit, one-way transition; calling a stage out of
order raises `InvalidPluginStateTransitionError`, mirroring
`InvalidWorkflowStateTransitionError` (Phase-11):

- **`load(plugin_name)`** — looks up `PluginMetadata` via
  `PluginRegistry.get_definition()` (raising `PluginNotFoundError` /
  `PluginDisabledError` exactly as `ToolRegistry.get_definition()`
  does), and creates a new `PluginRecord` in `DISCOVERED` state.
  Raises `PluginAlreadyLoadedError` if a record for `plugin_name`
  already exists — `load()` is not idempotent, matching
  `ExecutionAlreadyExistsError`'s (Phase-05) precedent for "adding
  something that already exists is a caller bug, not a no-op."
- **`validate(plugin_name)`** — requires `DISCOVERED`. Performs two
  checks, in order:
  1. **Version compatibility** (decision 6): the running
     `CURRENT_AEOS_VERSION` must satisfy
     `min_aeos_version <= CURRENT_AEOS_VERSION <= max_aeos_version`
     (or have no upper bound). Raises
     `PluginVersionIncompatibleError` otherwise.
  2. **Target existence** (Context item 1): for `extension_type ==
     TOOL`, `tool_registry.is_enabled(target_name)` must be `True`; for
     `PROVIDER`, `provider_registry.is_enabled(target_name)` must be
     `True`. Raises `PluginTargetNotFoundError` otherwise. This is the
     *only* interaction `PluginManager` ever has with `ToolRegistry` /
     `ModelProviderRegistry` — a read-only existence/enabled check,
     never an invocation.

  On success, transitions the record to `VALIDATED`.
- **`initialize(plugin_name)`** — requires `VALIDATED`. Transitions to
  `INITIALIZED`. This is the point a plugin becomes "active"
  (`is_active()` returns `True`). Initializing never calls
  `Tool.execute()`, `ToolFactory.create()`, or any `ModelProvider`
  adapter — see decision 5.
- **`unload(plugin_name)`** — requires `INITIALIZED`. Transitions to
  `UNLOADED`. A plugin may be `load()`-ed again afterward (a fresh
  `PluginRecord` replaces the unloaded one), matching how a workflow
  run's terminal state does not block starting a new run of the same
  `WorkflowDefinition`.

`load`/`validate`/`initialize`/`unload` never raise on a caller retry
of the *same* valid transition partway through a batch operation --
each is independently idempotent-checked via its own state guard, the
same "fail loudly and specifically" posture used everywhere else in
this codebase.

### 5. No new execution path — how this stays inside the Phase-12/Phase-13 pipelines

`PluginManager` never calls `Tool.execute()`, never calls
`ToolFactory.create()`, never calls a `ModelProvider` adapter, and
never imports plugin-supplied code. Activating a plugin only flips an
in-memory `PluginLifecycleState`; it does not create a second path to
run a tool or call a provider. Consequently:

- **Security (Phase-12):** every future invocation of a plugin's
  underlying tool still goes exclusively through
  `ToolExecutor.execute()`, which still runs `ToolAuthorizer`'s
  path-sandbox and per-agent checks exactly as before. There is no
  `PluginManager.run()`/`.execute()` method of any kind — this phase
  cannot bypass `ToolAuthorizer` because it has no code path that
  reaches a tool's `execute()` at all.
- **Observability (Phase-13):** `PluginManager` accepts the same
  optional, defaulted `observer: ObservabilityRecorder | None = None`
  parameter as `Orchestrator`/`ExecutionEngine`/`ToolExecutor`/
  `WorkflowEngine` (ADR-0011 decision 5) and records:

  | Event / Metric | When |
  |---|---|
  | `plugin_loaded` | after a successful `load()` |
  | `plugin_validated` | after a successful `validate()` |
  | `plugin_validation_failed` | `validate()` raises `PluginVersionIncompatibleError` / `PluginTargetNotFoundError` |
  | `plugin_initialized` | after a successful `initialize()` |
  | `plugin_unloaded` | after a successful `unload()` |
  | counter `plugin_manager.lifecycle_transitions_total` (tags `plugin_name`, `stage`, `outcome`) | every `load`/`validate`/`initialize`/`unload` call |

  Same `observer is None -> no-op` shape as every Phase-13 integration
  — omitting `observer` reproduces pre-Phase-14 behavior exactly
  (trivially true here, since `PluginManager` itself is new).

### 6. Version compatibility: a minimal, dependency-free comparator

```python
CURRENT_AEOS_VERSION = "1.4.0"  # bumped alongside pyproject.toml this phase

_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def _parse_version(value: str) -> tuple[int, int, int]: ...
def _is_version_compatible(current, minimum, maximum=None) -> bool: ...
```

No new dependency (`packaging` is not already a project dependency,
and pulling it in for a three-integer comparison would violate the
"keep dependencies minimal" posture `requirements.txt` documents for
Phase-04/05). `CURRENT_AEOS_VERSION` is defined locally in
`orchestrator/plugins/models.py` rather than reusing
`orchestrator.__init__.__version__` — that field has been `"0.1.1"`,
disconnected from `pyproject.toml`'s version, since Phase-04 and
reconciling it is a pre-existing inconsistency outside this phase's
scope (see Consequences).

### 7. New `PluginError(OrchestratorError)` base, seven concrete subclasses

```python
class PluginError(OrchestratorError): ...


class PluginRegistryError(PluginError): ...  # config/plugins.yaml load/validation


class PluginNotFoundError(PluginError): ...  # no config entry for plugin_name


class PluginDisabledError(PluginError): ...  # config entry has enabled: false


class PluginAlreadyLoadedError(PluginError): ...  # load() called twice


class UnknownPluginRecordError(PluginError): ...  # validate/initialize/unload/get before load()


class InvalidPluginStateTransitionError(PluginError): ...  # wrong-state lifecycle call


class PluginVersionIncompatibleError(
    PluginError
): ...  # outside [min_aeos_version, max_aeos_version]


class PluginTargetNotFoundError(PluginError): ...  # target_name not enabled in its registry
```

Mirrors every prior phase's `XError(OrchestratorError)` base plus a
config-loading subclass. `PluginNotFoundError`/`PluginDisabledError`
mirror `ToolNotFoundError`/`ToolDisabledError` (registry-level,
config-lookup failures); `UnknownPluginRecordError` mirrors
`UnknownWorkflowRunError` (Phase-11, manager-level, "no record tracked
under this key yet").

## Alternatives Considered

- **A `PluginFactory` that instantiates a new runnable object**,
  mirroring `ToolFactory`/`ProviderFactory`. Rejected for this phase —
  there is nothing for it to instantiate without either (a) importing
  plugin-supplied code (explicitly out of scope, see Context) or (b)
  duplicating `ToolFactory`/`ProviderFactory` themselves. A plugin
  activates an *existing* registered `tool_type`/`provider_type`;
  it does not add a new one. Left as Follow-up.
- **Filesystem/directory-scan discovery** (e.g. a `plugins/` folder
  Claude Code walks at startup) instead of `config/plugins.yaml`.
  Rejected per the approved scope (item 5): discovery is limited to
  project-managed, explicitly declared entries, matching every other
  registry in this codebase (`config/tools.yaml`,
  `config/model_providers.yaml`, ...).
- **Python `entry_points` / pip-installable plugins.** Rejected per
  the approved scope — explicitly out of scope this phase, and a much
  larger security surface (arbitrary installed-package code execution)
  that would need its own ADR.
- **A single `enabled: true/false` flag with no lifecycle**, matching
  `ToolDefinition`/`ProviderConfig`'s simpler shape. Rejected — the
  approved scope explicitly requires four distinct lifecycle stages
  (load/validate/initialize/unload), which a single boolean cannot
  represent (there would be no way to distinguish "declared but never
  validated" from "validated but not yet initialized").
- **Persisting `PluginRecord` state via `orchestrator/persistence`
  (SQLite)**, matching how `SQLiteMemoryStore` reused
  `persistence.db.connect()` in Phase-10. Rejected for this phase,
  matching ADR-0011's identical Storage decision for observability
  data: in-memory only; noted as a Follow-up instead.
- **Reconciling `orchestrator.__init__.__version__` with
  `pyproject.toml`'s version** as part of defining
  `CURRENT_AEOS_VERSION`. Rejected — out of scope for this phase (no
  completed-phase file may be redesigned outside its own scope); a
  local constant in `orchestrator/plugins/models.py` is a smaller,
  fully additive change.

## Consequences

### Positive

- Delivers all eight approved capabilities: metadata model, registry,
  manager/facade, `config/plugins.yaml`, project-managed-only
  discovery, four-stage lifecycle, version-compatibility validation,
  and comprehensive tests.
- Introduces zero new execution surface: `PluginManager` cannot bypass
  `ToolAuthorizer` because it has no path that reaches
  `Tool.execute()` — see decision 5.
- Fully backward compatible: `orchestrator/plugins/` is a new,
  self-contained, additive package with no call sites elsewhere in the
  codebase, exactly like Phase-09/Phase-10/Phase-11 on first
  introduction; every one of the 499 pre-Phase-14 tests remains valid
  unmodified.
- Open/Closed for the two existing extension points: a new
  `tool_type`/`provider_type` implementation still only requires
  changes to `ToolFactory`/`ProviderFactory` (ADR-0007 decision 4 /
  ADR-0005 decision 8), unchanged by this phase; a plugin entry simply
  references it by name once it exists.

### Negative

- A plugin cannot yet introduce a genuinely new `Tool`/`ModelProvider`
  implementation of its own — it can only activate/deactivate one that
  a developer has already registered in `ToolFactory`/`ProviderFactory`
  and configured in `config/tools.yaml`/`config/model_providers.yaml`.
  This keeps the phase safe but limits "plugin" to a metadata/lifecycle
  concept rather than a true code-extensibility mechanism.
- In-memory-only `PluginRecord` state means lifecycle progress is lost
  when the process exits; a plugin must be `load()`-ed and
  `validate()`-ed again on every restart.
- `CURRENT_AEOS_VERSION` is a second, manually-maintained version
  string alongside `pyproject.toml`'s `version` field (and the
  pre-existing, already-inconsistent `orchestrator.__init__.__version__`);
  a future phase should reconcile all three into one source of truth.

## Follow-up

- A `PluginFactory` (or equivalent) that lets a plugin register a
  genuinely new `Tool`/`ModelProvider` implementation, once a design
  for safely loading plugin-supplied code exists — its own future ADR,
  given the security implications noted in Context.
- Python `entry_points` / pip-installable plugin discovery, if
  distributing plugins outside this repository is ever needed.
- A persistent `PluginRecord` store (e.g. reusing
  `orchestrator/persistence`), matching `SQLiteMemoryStore`'s
  precedent, so lifecycle state survives a restart.
- A third `extension_type` (e.g. `workflow`, activating a
  `WorkflowDefinition`) if a concrete need arises; deliberately left
  out this phase to keep the two extension types tied 1:1 to the two
  existing Open/Closed factories.
- Reconciling `CURRENT_AEOS_VERSION`,
  `orchestrator.__init__.__version__`, and `pyproject.toml`'s
  `version` field into a single source of truth.
