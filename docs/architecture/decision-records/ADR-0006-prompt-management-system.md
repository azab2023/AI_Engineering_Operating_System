# ADR-0006: Prompt Management System (Phase-08)

- **Status:** Accepted
- **Date:** Phase-08
- **Deciders:** Lead AI Systems Architect

## Context

`PROJECT_ROADMAP.md` lists Phase-08 as "Prompt Management System", the
next planned phase after Phase-07's Model Provider Abstraction. Through
Phase-07, the text sent to an agent -- via either
`SubprocessAgentInvoker`'s `{task_description}` placeholder or
`HttpAgentInvoker`'s `provider.generate(prompt)` call -- is always
`AgentTask.description`: a free-form string with no templating,
variable substitution, versioning, or validation.

A `prompts/` scaffold has existed since Phase-01 (per `CLAUDE.md`'s
Phase-01 scope note: *"Empty/placeholder structure for `prompts/`,
`agents/`, `configs/`"*), containing `prompts/prompt_registry.yaml` (7
entries with `category` / `purpose` / `agents` / `priority` fields) and
three empty template files. None of this is read by any code in
`orchestrator/` -- it is inert scaffolding. `CLAUDE.md` §3 explicitly
anticipates this phase: *"Prompts are versioned artifacts... reviewed
engineering assets... following `prompts/templates/` ... conventions
once populated in later phases"*, and separately lists *"prompt
versioning scheme"* as an example of a decision requiring an ADR.

`orchestrator/exceptions.py`'s module docstring records a real incident:
*"the prompt_registry.yaml corruption discovered before this phase (a
duplicate top-level key was silently overridden by PyYAML instead of
raising)"* -- this is the direct motivation for the project's
fail-loudly philosophy, and Phase-08's registry loader must close this
specific gap, not merely inherit the general principle.

## Decision

### 1. New `orchestrator/prompts/` package, mirroring the Phase-07 `orchestrator/providers/` shape

`models.py` (`PromptVariable`, `PromptDefinition`, `RenderedPrompt` --
frozen dataclasses, no pydantic, matching every prior phase's data-model
convention), `template_renderer.py` (`PromptRenderer` Protocol +
`StringTemplateRenderer`), `prompt_registry.py` (`PromptRegistry`,
config loading/validation only), `prompt_manager.py` (`PromptManager`,
the Facade combining registry lookup + rendering). This is the same
four-way split Phase-07 used for `provider.py` / `*_provider.py` /
`provider_registry.py` / `provider_factory.py`.

### 2. `string.Template` (stdlib), not Jinja2 -- no new runtime dependency

`StringTemplateRenderer` uses `string.Template`'s `$variable` /
`${variable}` substitution syntax. No conditional or loop logic is
supported in this phase (see Alternatives and Follow-up). This keeps
Phase-08 dependency-free, unlike Phase-07 which justified adding
`httpx`; there is no equivalent justification here since substitution
alone satisfies every entry currently needed in `prompt_registry.yaml`.

### 3. `PromptRegistry`: configuration and lookup only, with a duplicate-key guard

Mirrors `ModelProviderRegistry` (ADR-0005 decision 3) exactly:
parse/validate `prompts/prompt_registry.yaml`, verify each entry's
`template_path` exists on disk at load time, and expose
`get(prompt_id) -> PromptDefinition`. It never renders a template and
never inspects `Agent`/`AgentTask`.

It additionally guards against the specific incident described in
`orchestrator/exceptions.py`: YAML is parsed with a `yaml.SafeLoader`
subclass whose `construct_mapping` is overridden to raise
`DuplicatePromptKeyError` on a repeated key, instead of relying on
`yaml.safe_load`'s default behavior of silently keeping the last value.
This is Phase-08's direct fix for a previously-documented failure mode,
not a generic hardening exercise.

### 4. `PromptManager`: the sole Facade used by invokers

`resolve(prompt_id, agent_name) -> PromptDefinition` (raises
`PromptNotAllowedForAgentError` if `agent_name` is not in the
definition's `agents` list) and `render(prompt_id, agent_name,
variables) -> RenderedPrompt`. This is the only entry point
`SubprocessAgentInvoker` / `HttpAgentInvoker` depend on; neither
invoker talks to `PromptRegistry` or `StringTemplateRenderer` directly.

### 5. Two new, optional, additive fields on `AgentTask`

```python
prompt_id: str | None = None
prompt_variables: dict[str, str] = field(default_factory=dict)
```

This is the **one deliberate exception** to every prior phase's
guarantee of zero changes to `orchestrator/models.py`. It is additive
only: any existing call site constructing `AgentTask(...)` without
these two keyword arguments is unaffected, and `prompt_id` defaults to
`None`. See decision 6 for why this was necessary rather than avoidable,
and Alternatives for the rejected fully-decoupled design.

### 6. Prompt resolution lives inside each `AgentInvoker`, immediately before invocation

Both `SubprocessAgentInvoker.invoke()` and `HttpAgentInvoker.invoke()`
gain one guard clause at the top:

```python
if task.prompt_id is not None:
    rendered = self._prompt_manager.render(task.prompt_id, agent.name, task.prompt_variables)
    prompt_text = rendered.text
else:
    prompt_text = task.description
```

`prompt_text` replaces every existing use of `task.description` further
down in each method (the `{task_description}` argv substitution in
`SubprocessAgentInvoker`; the `provider.generate(...)` argument in
`HttpAgentInvoker`). When `task.prompt_id is None`, behavior is
byte-for-byte identical to Phase-07 -- this is the fallback path that
keeps all 202 existing tests valid without modification.

This is the only place in the codebase that has both `agent` (already
selected) and `task` (already constructed) simultaneously, which is why
resolution cannot happen earlier (`Orchestrator.route()` selects an
agent but never sees invocation mechanics) or later (nothing exists
after `invoke()` that still has both).

### 7. `ExecutionEngine`, `Orchestrator`, `AgentRegistry`, `ModelProviderRegistry`: unchanged

- `ExecutionEngine.execute()` still calls `invoker.invoke(agent, task)`
  with the same signature and still only catches `AgentTimeoutError` /
  `AgentInvocationError` for its retry loop. Every new exception this
  phase introduces (§ below) is a configuration error, not a transient
  one, and is deliberately left uncaught here -- identical treatment to
  `ProviderConfigNotFoundError` / `ProviderDisabledError` today.
- `AgentRegistry` and `agent_registry.yaml`'s schema are untouched.
  `PromptManager.resolve()` checks `agent.name` (the already-selected
  `Agent`'s name, passed in by the invoker) against
  `PromptDefinition.agents` directly -- it does not query
  `AgentRegistry` a second time. The two files' agent-name sets are an
  operational invariant (both must use the same identifiers, e.g.
  `claude_code`, `codex`, `aider`, `gemini`), not a code dependency.
- `ModelProviderRegistry` is untouched and has no reference to
  `orchestrator.prompts` or vice versa; `HttpAgentInvoker` composes both
  as independent, unrelated dependencies (DIP).

### 8. Error mapping: every new exception is non-retryable

| Condition | Raised as | Retried by `ExecutionEngine`? |
|---|---|---|
| Duplicate top-level key in `prompt_registry.yaml` | `DuplicatePromptKeyError` | No -- fails at registry construction, before any execution |
| Missing required field / bad type in an entry | `PromptRegistryError` | No -- fails at registry construction |
| `template_path` does not exist on disk | `PromptTemplateFileMissingError` | No -- fails at registry construction |
| `prompt_id` not in registry | `PromptNotFoundError` | No -- propagates from `invoke()` |
| `agent.name` not in the prompt's `agents` list | `PromptNotAllowedForAgentError` | No -- propagates from `invoke()` |
| Required template variable missing from `prompt_variables` | `MissingRequiredVariableError` | No -- propagates from `invoke()` |
| Undeclared variable present in `prompt_variables` | `UnknownVariableError` | No -- propagates from `invoke()` |

All seven live under a new `PromptManagementError(OrchestratorError)`
base in `orchestrator/exceptions.py`, following the same
base-class-per-phase pattern as `ExecutionEngineError` (Phase-06) and
`ModelProviderError` (Phase-07).

## Architecture Diagram

```
 ┌────────────────────┐
 │   Orchestrator        │   orchestrator/core.py (UNCHANGED)
 │   select_agent/route()  │   selects `agent`; knows nothing about prompts
 └──────────┬────────────────┘
            │ agent, task (task may carry prompt_id + prompt_variables)
            ▼
 ┌────────────────────┐
 │  ExecutionEngine      │   orchestrator/execution/engine.py (UNCHANGED)
 │  (retry, state          │
 │   transitions)            │
 └──────────┬────────────────┘
            │ AgentInvoker.invoke(agent, task)
            ▼
 ┌───────────────────────────────┐
 │ SubprocessAgentInvoker /          │  orchestrator/execution/{invoker,http_invoker}.py
 │ HttpAgentInvoker (MODIFIED: one     │  (NEW: prompt-resolution guard clause,
 │  guard clause each)                   │   otherwise unchanged)
 └───────┬─────────────────────┬─────────┘
         │ if task.prompt_id set │ else
         ▼                       ▼
 ┌────────────────────┐      task.description
 │   PromptManager       │      (Phase-07 behavior,
 │   resolve() + render()  │       byte-for-byte)
 └──────────┬────────────────┘
            │
   ┌────────┴─────────┐
   ▼                   ▼
┌───────────────┐  ┌───────────────────┐
│ PromptRegistry   │  │ StringTemplateRenderer│   orchestrator/prompts/*.py (NEW)
│ - loads/validates  │  │ - string.Template        │
│   prompt_registry.yaml│  │   substitution only        │
│ - duplicate-key guard│  └───────────────────┘
└───────────────┘
```

## Alternatives Considered

- **Fully decoupled `PromptManager` with zero changes to `AgentTask`**
  (the design proposed during Task 8.1 planning, before the full
  lifecycle requirement -- Task -> Agent Selection -> Prompt Resolution
  -> ... -- was worked through in detail). Rejected on reflection:
  Prompt Resolution must happen *after* Agent Selection (a prompt can be
  restricted to specific agents), which means the caller constructing
  `AgentTask` cannot pre-render the prompt before an agent is even
  chosen. Keeping `AgentTask` prompt-free would have pushed resolution
  into `Orchestrator.route()` (which has never known about invocation
  mechanics -- rejected for the same reason ADR-0002/0004 kept selection
  and invocation separate) or introduced a third orchestration step
  outside `ExecutionEngine` (rejected as unnecessary structural
  complexity when two optional dataclass fields suffice).
- **Jinja2 for template rendering.** Rejected -- no current
  `prompt_registry.yaml` entry needs conditionals or loops; adding a
  templating engine dependency for unused expressiveness contradicts the
  project's minimal-dependency convention (see ADR-0005 decision 7's
  bar for justifying a new dependency, which this phase does not meet).
- **`PromptManager` calls `AgentRegistry` to re-validate the agent.**
  Rejected -- redundant, since `invoke()` is only ever called with an
  already-selected, already-validated `Agent` instance; re-querying the
  registry would be dead validation and an unnecessary coupling between
  `orchestrator.prompts` and `orchestrator.registry`.
- **Resolve prompts inside `ExecutionEngine` instead of each invoker.**
  Rejected -- would require `ExecutionEngine` to import
  `orchestrator.prompts` and know about `RenderedPrompt`, breaking its
  Phase-06 invariant of depending only on the `AgentInvoker` Protocol;
  also would not generalize if a third `AgentInvoker` implementation is
  added later with a different invocation shape.

## Consequences

- Prompts become versioned, validated engineering assets: each entry in
  `prompts/prompt_registry.yaml` has an explicit `version`, a real
  `template_path` that is verified to exist at load time, and a typed
  `variables` list that is enforced (missing-required / unknown-extra)
  at render time.
- `AgentTask` gains two optional fields; this is the only model change
  in this phase, and it is additive -- all 202 pre-Phase-08 tests remain
  valid unmodified, and any code omitting `prompt_id` reproduces
  Phase-07 behavior exactly.
- `ExecutionEngine`, `Orchestrator`, `orchestrator/registry.py`,
  `agent_registry.yaml`'s schema, the `AgentInvoker` Protocol, and
  `ModelProviderRegistry` are all unchanged by this phase.
- The duplicate-top-level-key failure mode that previously affected
  `prompt_registry.yaml` silently is now caught immediately and
  specifically at registry-construction time.
- The three previously-empty template files
  (`prompts/templates/{coding_prompt,debugging_prompt,review_prompt}.md`)
  are removed and replaced by seven populated templates under
  `prompts/templates/<category>/`, one per existing registry entry.

## Follow-up

- Conditional/loop template logic (Jinja2 or similar) is deferred until
  a concrete entry needs it; would be its own ADR given the new
  dependency.
- `prompts/workflows/` (multi-step prompt chaining) and `prompts/system/`
  remain unpopulated placeholders, unaffected by this phase.
- No config-driven default for `prompt_id` per task type exists yet --
  callers must set it explicitly on `AgentTask`. A convention or
  default-mapping mechanism is a reasonable future extension, not
  required here.
- Automatic `version` compatibility checking (e.g. rejecting a render
  against a template whose file changed since the registry entry's
  `version` was last bumped) is not implemented; `version` is
  documentation-only in this phase.
