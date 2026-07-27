# ADR-0010: Security & Permissions (Phase-12)

- **Status:** Accepted
- **Date:** Phase-12
- **Deciders:** Lead AI Systems Architect

## Context

`PROJECT_ROADMAP.md` lists Phase-12 as "Security & Permissions". Two
concrete deferrals already point at what this phase closes:

- ADR-0007 (Phase-09) Follow-up: "Path sandboxing / an allow-listed
  root directory (or similar permission scoping) for `ReadFileTool` /
  `ListDirectoryTool` belongs to Phase-12." Both tools remain read-only
  today but are otherwise unsandboxed — they can access any path the OS
  process can.
- A separate, older deferral (Phase-02-era, referenced in every
  `agents/*/README.md` since): a per-agent `config/permissions.yaml`
  describing "what this agent may read/write".

The project owner's first scope decision for this phase (recorded in
this ADR's initial draft) was the narrower item only — path sandboxing.
That decision was subsequently revised: the project owner approved the
full scope, combining both deferrals behind one reusable authorization
layer. This revision supersedes the initial draft; nothing from the
initial draft shipped as code, so there is no migration to describe,
only a design to finalize before any code is written.

Two constraints shape the design:

1. **Backward compatibility with Phase-11.** `tests/test_workflow_engine.py`
   exercises `tool_call` steps against a real, default-constructed
   `ToolExecutor()` using files under pytest's `tmp_path` (outside the
   project root), and `WorkflowStep`/`config/workflows.yaml` currently
   have no concept of "which agent" issued a `tool_call` step. Neither
   of these can be allowed to regress.
2. **No existing "calling agent" identity at the `ToolExecutor`
   boundary.** `ToolExecutor` was deliberately built agent-agnostic in
   Phase-09 (ADR-0007 decision 6), and Phase-11's `tool_call` steps
   were deliberately scoped without an `agent_name` (ADR-0009). Adding
   per-agent read/write enforcement requires threading an agent
   identity through both, which is new surface area on top of both
   phases — the minimum viable version of that surface area is used
   here, per "do not modify previous phase behavior except where
   required for security enforcement".

## Decision

### 1. New `orchestrator/security/` package: models, config loading, and a reusable authorizer

Three modules, mirroring the two-or-three-module shape every prior
phase's package uses (`tools/`, `providers/`, `workflow/`):

- `models.py` — `PathSandboxPolicy`, `AgentPermission`, `PermissionPolicy`
  (plain frozen dataclasses, no pydantic — same bar every prior ADR
  applied).
- `permission_registry.py` — `PermissionRegistry`, loading and
  validating `config/permissions.yaml` into a `PermissionPolicy`. Same
  fail-loud loading shape as `ToolRegistry`/`ModelProviderRegistry`/
  `WorkflowRegistry`.
- `authorizer.py` — `ToolAuthorizer`, the reusable, centralized
  authorization layer explicitly requested: one `authorize()` entry
  point combining both checks below. `ToolExecutor` calls this and
  does not itself contain permission logic.

### 2. `PathSandboxPolicy`: unchanged from the initial draft

```python
@dataclass(frozen=True)
class PathSandboxPolicy:
    allowed_roots: tuple[Path, ...]

    def is_allowed(self, path: Path) -> bool: ...
```

Non-empty, absolute, resolved roots (validated in `__post_init__`).
`is_allowed()` resolves the candidate (`Path.resolve()`) and checks
equality/descendance (`Path.is_relative_to()`) against any root.

### 3. `AgentPermission` + `PermissionPolicy`: the new per-agent axis

```python
@dataclass(frozen=True)
class AgentPermission:
    agent_name: str
    can_read: bool
    can_write: bool


@dataclass(frozen=True)
class PermissionPolicy:
    path_sandbox: PathSandboxPolicy
    agent_permissions: dict[str, AgentPermission] = field(default_factory=dict)
```

### 4. `config/permissions.yaml`: one file, two sections

```yaml
path_sandbox:
  allowed_roots:
    - "."
  include_system_temp_dir: true

agent_permissions:
  claude_code:
    read: true
    write: true
  codex:
    read: true
    write: true
  aider:
    read: true
    write: false
  gemini:
    read: true
    write: false
```

- `path_sandbox`: unchanged from the initial draft. `include_system_temp_dir:
  true` keeps `tempfile.gettempdir()` in the allow-list so
  `tests/test_workflow_engine.py`'s `tmp_path`-based fixtures keep
  passing against the default policy — see Context constraint 1.
- `agent_permissions`: one entry per `config/agents.yaml` /
  `config/agent_registry.yaml` agent name (`claude_code`, `codex`,
  `aider`, `gemini`), each with independent `read`/`write` booleans.
  All four are granted `read: true` (matches every tool that exists
  today being read-only) with `write` differentiated per agent as a
  concrete, working example of the axis — not a judgment about any
  agent's trustworthiness. An agent absent from this section is denied
  outright rather than defaulted permissively (see decision 7,
  fail-loud philosophy).

`PermissionRegistry._load()` fails loudly (`PermissionRegistryError`)
on: missing file, invalid YAML, a missing/malformed `path_sandbox` key,
or a malformed `agent_permissions` entry (non-boolean `read`/`write`,
non-mapping entry, etc.). A *missing* `agent_permissions` section as a
whole is tolerated (parses to `{}`) — a deployment that only cares
about path sandboxing does not have to author agent entries it doesn't
need yet; see decision 7 for what an empty/absent entry means at
authorization time.

### 5. `ToolDefinition` gains two new, optional fields

```python
sandboxed_parameters: tuple[str, ...] = field(default_factory=tuple)
access_mode: str = "read"  # "read" | "write"
```

Both default to values that make every existing `config/tools.yaml`
entry (and every hand-built `ToolDefinition` in existing tests)
unaffected: no sandboxed parameters, and `"read"` matches what
`ReadFileTool`/`ListDirectoryTool` already are. `ToolRegistry._parse_entry()`
parses both as optional fields, validating `access_mode` against
`{"read", "write"}` and each `sandboxed_parameters` name against the
tool's own declared `parameters` — both raise the existing
`ToolRegistryError`, since this is a `tools.yaml` schema concern, not a
`permissions.yaml` concern (same domain split as the initial draft).

### 6. `config/tools.yaml` updated additively

`read_file` and `list_directory` each gain `sandboxed_parameters: [path]`
and `access_mode: read` (explicit, even though `read` is the default —
security-relevant fields are stated, not implied). No other entry or
field changes.

### 7. `ToolAuthorizer.authorize()`: the single, reusable enforcement entry point

```python
def authorize(self, definition: ToolDefinition, arguments: dict, agent_name: str | None) -> None:
    self._authorize_agent(definition, agent_name)
    self._authorize_paths(definition, arguments)
```

- **Path check** (`_authorize_paths`): unchanged from the initial
  draft — for each name in `definition.sandboxed_parameters` present
  in `arguments`, the resolved path must satisfy
  `policy.path_sandbox.is_allowed()`, or `PathPermissionError`.
- **Agent check** (`_authorize_agent`):
  - `agent_name is None` → **no check performed**. This is the
    explicit, documented answer to Context constraint 2: every
    pre-Phase-12 call site (every existing test, and any future direct
    `ToolExecutor.execute()` call that doesn't pass `agent_name`)
    continues to run exactly as before. This is an additive
    capability, not a retroactively-enforced one — mirrors how
    `ToolExecutor` itself shipped in Phase-09 with no callers, and
    Phase-11 wired it in without changing its Facade contract.
  - `agent_name` given but absent from `policy.agent_permissions` →
    `UnknownAgentPermissionError` (deny by default; fail loud rather
    than silently allow an unrecognized caller).
  - `agent_name` given and known → the relevant flag
    (`can_write` if `definition.access_mode == "write"` else
    `can_read`) must be `True`, or `AgentPermissionError`.

### 8. `ToolExecutor`: one new constructor argument, one new optional call argument

```python
def __init__(self, registry=None, factory=ToolFactory, authorizer: ToolAuthorizer | None = None):
    self._authorizer = authorizer or ToolAuthorizer()


def execute(
    self, tool_name: str, arguments: dict | None = None, agent_name: str | None = None
) -> ToolResult:
    definition = self._registry.get_definition(tool_name)
    arguments = arguments or {}
    self._validate_arguments(definition, arguments)
    self._authorizer.authorize(definition, arguments, agent_name)
    tool = self._factory.create(definition)
    ...
```

`agent_name` is appended as a new, defaulted keyword/positional
argument — every existing two-argument call (`execute(tool_name,
arguments)`) is unaffected. `ToolExecutor` itself contains no
permission logic; it owns exactly what it owned before (resolve,
validate, run) plus one call out to the authorizer. Neither
`ReadFileTool` nor `ListDirectoryTool`'s `execute()` changes — only
their docstrings, to note enforcement happens upstream.

### 9. Minimum necessary Phase-11 touches, to let a `tool_call` step carry an agent identity

Per Context constraint 2, per-agent enforcement is meaningless unless
some caller can supply `agent_name`. The only current caller is
`WorkflowEngine`. Three small, additive changes:

- `WorkflowStep` (`orchestrator/workflow/models.py`) gains one new
  optional `TOOL_CALL` field: `agent_name: str | None = None`.
- `WorkflowRegistry._parse_step()` parses an optional `agent_name` key
  from a `tool_call` step entry in `config/workflows.yaml` (absent →
  `None`, same as every other optional field this registry already
  parses).
- `WorkflowEngine._run_tool_step()` passes `agent_name=step.agent_name`
  to `tool_executor.execute()`, and its `except ToolError` clause
  widens to `except (ToolError, SecurityError)`, so a denied
  authorization fails the workflow run the same way an existing
  `ToolError` already does (`WorkflowRunState.FAILED`, `run.error`
  set) rather than propagating an uncaught exception. `SecurityError`
  and `ToolError` are siblings under `OrchestratorError`, not a
  subtype relationship, so this widening is required, not cosmetic.

No other Phase-11 file, model, or test changes. Every existing
workflow/step without an `agent_name` behaves exactly as before
(decision 7's `agent_name is None` → no check).

### 10. New `SecurityError(OrchestratorError)` base, three concrete subclasses

```python
class SecurityError(OrchestratorError): ...


class PermissionRegistryError(SecurityError): ...  # config/permissions.yaml load/validation


class PathPermissionError(SecurityError): ...  # a checked path is outside the sandbox


class AgentPermissionError(SecurityError): ...  # a known agent lacks read/write for this tool


class UnknownAgentPermissionError(SecurityError): ...  # agent_name has no configured entry
```

Mirrors every prior phase's own `XError(OrchestratorError)` base plus
a config-loading subclass, extended here with two at-call-time
subclasses instead of one (path vs. agent are distinct failure modes,
each needs its own message/attributes, same reasoning `ToolError`
applied to have four distinct call-time subclasses rather than one
generic one).

## Alternatives Considered

- **Per-`Tool`-implementation enforcement.** Rejected — explicit
  project owner decision (unchanged from the initial draft).
- **Making `agent_name` a required `ToolExecutor.execute()` argument.**
  Rejected: breaks every existing call site
  (`tests/test_tool_executor.py`, `WorkflowEngine`'s own default
  construction), which the "fully backward compatible" requirement
  rules out. The optional-with-`None`-means-unchecked shape is the
  smallest change that adds the capability without breaking anything
  that predates it.
- **Treating an unknown `agent_name` as allowed (permissive default).**
  Rejected — inconsistent with the project's fail-loud philosophy
  applied everywhere else (`ToolNotFoundError`, `ProviderConfigNotFoundError`,
  etc. all deny/reject an unrecognized identifier rather than falling
  through).
- **Storing `agent_permissions` as a flat list of dataclasses instead
  of a `dict[str, AgentPermission]`.** Rejected for this phase — a
  dict gives O(1) lookup by `agent_name` (the only access pattern
  `ToolAuthorizer` needs) with less code than a list + linear search;
  every other keyed config in this project (`ToolRegistry`,
  `ModelProviderRegistry`) already resolves to a dict internally.
- **A strict, temp-dir-excluded default sandbox.** Rejected — same
  reasoning as the initial draft: breaks `test_workflow_engine.py`.

## Consequences

### Positive

- Both Phase-12 deferrals are closed: path sandboxing for the two
  filesystem tools, and a working per-agent read/write axis with a
  real, non-trivial default configuration (four agents, differentiated
  `write` access).
- One reusable, testable authorization layer (`ToolAuthorizer`)
  instead of logic embedded in `ToolExecutor` or scattered across
  tools — a future third permission axis (if ever needed) is a new
  method on `ToolAuthorizer`, not a new `ToolExecutor` change.
- Fully backward compatible: every new field/argument defaults to a
  value that reproduces pre-Phase-12 behavior exactly; the one
  Phase-11 behavior change (`except (ToolError, SecurityError)`) is
  additive (widens what is caught, changes no existing control flow).

### Negative

- The default `config/permissions.yaml` is a starting configuration,
  not a hardened production one; the project owner or an operator is
  expected to adjust `agent_permissions` per real deployment trust
  boundaries.
- `agent_name is None` → unchecked is a real gap: any caller that
  doesn't pass `agent_name` bypasses the agent-permission axis
  entirely (though not the path-sandbox axis, which is
  argument-based and always enforced regardless of caller identity).
  This is deliberate (see decision 7 / Alternatives) but worth stating
  plainly: this phase adds the mechanism and wires it into the one
  existing caller (`WorkflowEngine`); it does not retroactively
  guarantee every possible caller supplies an identity.

## Follow-up

- Any future `ToolExecutor.execute()` caller (direct, or a new
  `AgentInvoker`/`ExecutionEngine` integration) should pass
  `agent_name` if it has one, to get agent-permission coverage for
  free; nothing enforces that it does so today.
- Any future write-capable, shell, or network-calling tool (already
  named as out of scope in ADR-0007 Follow-up) should declare
  `sandboxed_parameters` and an accurate `access_mode` in its
  `config/tools.yaml` entry to inherit both axes of this phase's
  protection automatically.
- Tightening `config/permissions.yaml` for a specific deployment is a
  config edit, not a code change.
