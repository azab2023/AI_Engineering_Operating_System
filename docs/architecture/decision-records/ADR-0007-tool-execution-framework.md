# ADR-0007: Tool Execution Framework (Phase-09)

- **Status:** Accepted
- **Date:** Phase-09
- **Deciders:** Lead AI Systems Architect

## Context

`PROJECT_ROADMAP.md` lists Phase-09 as "Tool Execution Framework", the
next planned phase after Phase-08's Prompt Management System. Through
Phase-08, an `AgentTask` carries only a `description` (optionally
resolved from a versioned prompt template) that is sent to an agent for
it to act on -- there is no in-process concept of a discrete,
named, independently-invokable *tool* (e.g. reading a file, listing a
directory) that could be run outside of an agent's own CLI/API session.
No `tool`-related scope exists anywhere in the repository prior to this
phase: `orchestrator/execution/command_registry.py` configures how an
agent's own CLI is *invoked*, which is a different concern entirely
from a standalone tool an orchestration caller (eventually the Phase-11
Workflow Engine) could invoke directly.

Because the roadmap names this phase but does not specify its scope,
the concrete design was proposed and approved before implementation, per
this project's "docs before code" / ADR-first governance (see
`PROJECT_ROADMAP.md` § Development Workflow and every prior ADR's
"Deciders" line).

## Decision

### 1. New `orchestrator/tools/` package, mirroring the Phase-07 `orchestrator/providers/` shape

`models.py` (`ToolParameter`, `ToolDefinition`, `ToolResult` -- frozen
dataclasses, no pydantic, matching every prior phase's data-model
convention), `tool.py` (`Tool` Protocol), `tool_registry.py`
(`ToolRegistry`, config loading/validation only), `tool_factory.py`
(`ToolFactory`, `tool_type` string -> concrete `Tool` class),
`tool_executor.py` (`ToolExecutor`, the Facade combining registry
lookup + argument validation + execution), and `builtin/` (concrete
`Tool` implementations). This is the same package shape Phase-07 used
for `provider.py` / `*_provider.py` / `provider_registry.py` /
`provider_factory.py`, with `ToolExecutor` playing the role
`HttpAgentInvoker` played there: the single composition point that
depends on the `Tool` Protocol and never on a concrete implementation.

### 2. `ToolResult` mirrors `ProviderResponse`, not `ExecutionResult`

`Tool.execute()` either returns a `ToolResult` (`tool_name`, `output`,
`duration_seconds`) or raises `ToolExecutionError` -- there is no "ran
but failed" return value, matching `ModelProvider.generate()`'s
contract (ADR-0005) rather than `ExecutionResult`'s exit-code shape
(ADR-0004). A tool run is a single self-contained local operation, not
a subprocess with a distinct exit-code concept.

### 3. `ToolRegistry`: configuration, validation, and lookup only

Mirrors `ModelProviderRegistry` (ADR-0005 decision 3) exactly:
parse/validate `config/tools.yaml`, verify each entry's shape
(`tool_type`, `enabled`, `description`, `parameters`), and expose
`get_definition(tool_name) -> ToolDefinition`. It never runs a tool and
never instantiates a `Tool` implementation.

Each `parameters` entry is validated into a `ToolParameter` (`name`,
`type` restricted to `"string" | "number" | "boolean"`, `required`,
`description`), following the same fail-loudly philosophy as every
prior registry in this project (`AgentRegistry`,
`AgentCommandRegistry`, `ModelProviderRegistry`, `PromptRegistry`):
malformed or missing fields raise a specific `ToolRegistryError`
immediately at load time, not later at execution time.

### 4. `ToolFactory`: Open/Closed by construction, same pattern as `ProviderFactory`

A plain registration dict (`tool_type -> Tool implementation class`),
not an `if/elif` chain. Adding a new built-in tool requires one new
class under `orchestrator/tools/builtin/` and one new dict entry in
`ToolFactory._IMPLEMENTATIONS` -- zero changes to `ToolExecutor`,
`ToolRegistry`, or `config/tools.yaml`'s schema. This is the same
Open/Closed guarantee ADR-0005 decision 8 established for
`ProviderFactory`.

### 5. Two built-in tools only, both read-only, local-filesystem, non-recursive

`ReadFileTool` (`tool_type: read_file`) reads one file's full text
contents. `ListDirectoryTool` (`tool_type: list_directory`) lists one
directory's immediate entries. Neither performs a write, a recursive
walk, network I/O, or shell/subprocess execution of any kind. This
scope is deliberately minimal: the goal of Phase-09 is a working,
extensible *framework*, not a comprehensive tool library. See
Alternatives and Follow-up for what is explicitly deferred.

### 6. Nothing outside `orchestrator/tools/` changes in this phase

`AgentTask`, `Orchestrator`, `ExecutionEngine`,
`SubprocessAgentInvoker`, `HttpAgentInvoker`, `AgentRegistry`,
`ModelProviderRegistry`, and `PromptManager` are all untouched. Unlike
Phase-08 (which added `prompt_id` / `prompt_variables` to `AgentTask`
because prompt resolution had to happen *after* agent selection, inside
an invoker -- ADR-0006 decision 5), there is no equivalent forcing
requirement here: nothing in this phase's scope requires a tool to be
resolved in the context of an already-selected `Agent`. Wiring tool
invocation into the execution/agent-task lifecycle is left to whichever
future phase actually needs it (most likely Phase-11's Workflow
Engine, which is expected to be the first real caller of
`ToolExecutor`). Building that integration now, speculatively, without
a concrete consumer, would be exactly the kind of premature coupling
ADR-0002 and ADR-0004 already rejected once each for the
selection/invocation boundary.

### 7. `ToolExecutor`: the sole Facade, validates before it runs anything

`execute(tool_name, arguments) -> ToolResult` first resolves the
definition (`ToolNotFoundError` / `ToolDisabledError`), then validates
`arguments` against `ToolDefinition.parameters` --
`MissingRequiredArgumentError` for an absent required argument,
`UnknownArgumentError` for an undeclared one (mirroring
`PromptManager`'s `MissingRequiredVariableError` / `UnknownVariableError`,
ADR-0006), and `InvalidArgumentTypeError` for a value that does not
match its declared `type` -- before ever constructing a `Tool` instance
or calling `execute()` on it. Any exception a `Tool` implementation
raises other than `ToolExecutionError` is wrapped into
`ToolExecutionError` at this boundary, so a caller of `ToolExecutor`
only ever needs to handle the `ToolError` hierarchy.

### 8. Error hierarchy: new `ToolError(OrchestratorError)` base

All eight new exceptions (`ToolRegistryError`, `ToolNotFoundError`,
`ToolDisabledError`, `UnsupportedToolTypeError`,
`MissingRequiredArgumentError`, `UnknownArgumentError`,
`InvalidArgumentTypeError`, `ToolExecutionError`) live under `ToolError`
in `orchestrator/exceptions.py`, following the same
base-class-per-phase pattern as `ExecutionEngineError` (Phase-06),
`ModelProviderError` (Phase-07), and `PromptManagementError`
(Phase-08). Because nothing outside `orchestrator/tools/` calls
`ToolExecutor` yet (decision 6), none of this hierarchy needs to be
caught, retried, or mapped anywhere else in the codebase this phase --
unlike the Phase-06/07/08 error hierarchies, which all had to define an
explicit retry/propagation contract with `ExecutionEngine`.

## Architecture Diagram

```
 (No caller yet in this phase -- see decision 6.
  Expected future caller: Phase-11 Workflow Engine)
            │
            ▼
 ┌────────────────────┐
 │   ToolExecutor        │   orchestrator/tools/tool_executor.py (NEW)
 │   execute(name, args)   │   - resolves definition
 │                            │   - validates arguments
 └──────────┬────────────────┘   - wraps non-ToolExecutionError failures
            │
   ┌────────┴─────────┐
   ▼                   ▼
┌───────────────┐  ┌───────────────────┐
│  ToolRegistry    │  │   ToolFactory        │   orchestrator/tools/*.py (NEW)
│  - loads/validates │  │   tool_type -> class    │
│    config/tools.yaml│  └─────────┬─────────────┘
└───────────────┘            │
                              ▼
                   ┌─────────────────────────┐
                   │ Tool (Protocol)            │
                   ├─────────────┬───────────────┤
                   │ ReadFileTool  │ ListDirectoryTool │  orchestrator/tools/builtin/*.py
                   └─────────────┴───────────────┘
```

## Alternatives Considered

- **Wire `ToolExecutor` into `AgentTask` / `ExecutionEngine` now**
  (e.g. a `tool_calls` field on `AgentTask`, resolved inside each
  invoker, the same shape as Phase-08's `prompt_id`). Rejected for this
  phase -- there is no concrete requirement yet for *which* execution
  path should trigger a tool call (before invocation? after, on the
  result? multiple calls per task?), and Phase-11 (Workflow Engine) is
  explicitly the roadmap phase for multi-step orchestration logic like
  this. Building the integration now would mean guessing at a shape
  Phase-11 might have to redo anyway. See decision 6.
- **MCP (Model Context Protocol) integration for tool discovery.**
  Rejected for this phase -- out of scope per the approved Phase-09
  scope (no MCP integration). `Tool` is a plain in-process Protocol,
  not a network protocol client; MCP support, if ever added, would be
  a new `Tool` implementation (or a new invocation path entirely) behind
  the same Protocol, not a change to this phase's design.
- **General-purpose shell/subprocess execution tool.** Rejected for
  this phase -- out of scope per the approved Phase-09 scope (no
  general shell execution). Arbitrary command execution has security
  implications (sandboxing, permission scoping, credential exposure)
  that belong to Phase-12 (Security & Permissions), not this framework
  phase.
- **Pydantic (or another schema library) for argument validation.**
  Rejected -- no current tool needs more than a flat `name: type,
  required` shape; the same minimal-dependency bar ADR-0005 decision 7
  and ADR-0006 decision 2 already applied is not met here either.
  `ToolExecutor._validate_arguments()` is a handful of set-difference
  and `isinstance` checks, not a validation framework's worth of logic.
- **Path sandboxing / an allow-listed root directory for
  `ReadFileTool` / `ListDirectoryTool` in this phase.** Considered, but
  deferred to Phase-12 (Security & Permissions), which is the roadmap
  phase for permission scoping generally. Enforcing it piecemeal, once
  per built-in tool, ahead of a project-wide permissions model would
  likely have to be redone. Both tools remain read-only in the
  meantime, which bounds the blast radius of this deferral.

## Consequences

- A working, extensible tool framework exists:
  `ToolRegistry` / `ToolFactory` / `ToolExecutor` / `Tool`, plus two
  built-in tools, all under `orchestrator/tools/`.
- Adding a new built-in tool is a two-file change (a new `Tool`
  implementation under `builtin/`, plus one `ToolFactory` dict entry)
  and one new `config/tools.yaml` entry -- no changes to `ToolExecutor`
  or `ToolRegistry`. Same Open/Closed guarantee as `ProviderFactory`
  (ADR-0005 decision 8).
- `AgentTask`, `Orchestrator`, `ExecutionEngine`, both `AgentInvoker`
  implementations, `AgentRegistry`, `ModelProviderRegistry`, and
  `PromptManager` are all unchanged by this phase; all pre-Phase-09
  tests remain valid unmodified.
- `ToolExecutor` currently has no caller anywhere else in the codebase
  -- by design (decision 6). It is complete, tested, and ready for the
  Phase-11 Workflow Engine (or any earlier phase that turns out to need
  it) to depend on.
- Both built-in tools are read-only and unsandboxed: they can read any
  file/directory the process has OS-level permission to read. This is
  an accepted, explicit limitation of this phase, not an oversight --
  see Follow-up.

## Follow-up

- Path sandboxing / an allow-listed root directory (or similar
  permission scoping) for `ReadFileTool` / `ListDirectoryTool` belongs
  to Phase-12 (Security & Permissions) and is not implemented here.
- Write-capable tools (create/edit/delete a file), a shell/subprocess
  execution tool, and network-calling tools (HTTP fetch, web search)
  are all deliberately out of scope for Phase-09 and are not
  implemented here; each would need its own ADR given the added
  security surface.
- MCP (Model Context Protocol) integration, if pursued later, would be
  its own ADR: either a new `Tool` implementation that proxies to an
  MCP server, or a parallel invocation path -- not a change to the
  `Tool` Protocol itself.
- Wiring `ToolExecutor` into `AgentTask` / an `AgentInvoker` / the
  future Workflow Engine is intentionally left to the phase that
  actually needs it (decision 6, Alternatives).
