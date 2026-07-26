# ADR-0009: Workflow Engine (Phase-11)

- **Status:** Accepted
- **Date:** Phase-11
- **Deciders:** Lead AI Systems Architect

## Context

`PROJECT_ROADMAP.md` lists Phase-11 as "Workflow Engine", the next
planned phase after Phase-10's Memory Management. As with every prior
phase, the roadmap names the phase but does not specify its concrete
design, so this ADR proposes and records that design before any code
is written, per this project's "docs before code" / ADR-first
governance.

Two prior ADRs already anticipate this phase directly:

- ADR-0007 decision 6 built `ToolExecutor` with **no caller anywhere
  in the codebase**, explicitly naming "Phase-11's Workflow Engine" as
  its expected first consumer.
- ADR-0008 decision 7 did the same for `MemoryManager`, again naming
  Phase-11 as the expected future caller, "alongside `ToolExecutor`".

So, unlike Phase-09 or Phase-10, Phase-11 is not a self-contained,
no-caller-yet package — it is specifically the phase that is expected
to *compose* existing, already-tested components (`Orchestrator`,
`ExecutionEngine`, `ToolExecutor`) into multi-step sequences. This
changes the shape of the question this ADR has to answer: not "what
new subsystem do we add" but "what is the minimal composition layer
that lets a caller run several existing steps in sequence, without
touching any of the components being composed."

Reading `orchestrator/execution/engine.py` closely surfaces one
constraint that materially shapes this design: `ExecutionEngine.execute()`
resolves an agent task only as far as `AWAITING_APPROVAL`
(`Orchestrator.mark_awaiting_approval`) — reaching `COMPLETED` requires
a separate, human-driven `Orchestrator.approve()` call. This is not
incidental; it is `docs/architecture/overview.md` design principle 5
("Human approval stays in the loop") made structural in the
`ExecutionState` machine. A Workflow Engine that silently skipped or
bypassed this gate for the sake of a fully-automatic linear run would
violate that principle. A sequence that contains an `agent_task` step
must therefore be able to **pause** at that step and **resume** only
once the corresponding `AgentExecution` has actually been approved —
it cannot be a single uninterrupted function call.

`orchestrator/tools/`'s `ToolExecutor.execute()` has no equivalent gate
(Phase-09 scope, ADR-0007): a tool either returns a `ToolResult`
immediately or raises. Tool-call steps can therefore run inline,
without pausing the run.

`README.md` / `CLAUDE.md` also reserve a `prompts/workflows/` folder,
described as holding "multi-step workflow *prompts*". That is a
narrower, pre-existing concern (prompt template content, resolved via
`PromptRegistry`/`PromptManager`) and is explicitly **not** what this
ADR defines — a Workflow Engine step sequence is a new orchestration
concept, not a prompt-template concept. A workflow step that is an
`agent_task` can still reference a prompt via the existing `prompt_id`
field (unchanged, see Decision 3); no new integration is required for
that to work.

## Decision

### 1. New `orchestrator/workflow/` package, mirroring the Phase-07/09 package shape

`models.py` (`StepType`, `WorkflowStep`, `WorkflowDefinition`,
`WorkflowRunState`, `WorkflowRun` — frozen dataclasses for the
immutable definition types, a mutable dataclass for `WorkflowRun`,
matching the `AgentTask`/`AgentExecution` split in
`orchestrator/models.py`), `workflow_registry.py` (`WorkflowRegistry`,
config loading/validation only, mirroring `ToolRegistry`), `repository.py`
(`WorkflowRunRepository` Protocol + `InMemoryWorkflowRunRepository`,
mirroring `orchestrator/persistence/repository.py`'s
`ExecutionRepository` shape), and `workflow_engine.py`
(`WorkflowEngine`, the sole Facade). This is the same package shape
every prior phase used: one config-driven registry, one Facade, no
other entry points.

### 2. A `WorkflowDefinition` is a named, config-driven, ordered list of steps of exactly two kinds

`config/workflows.yaml` (new file, additive, following the exact
loading/validation contract `ToolRegistry` established for
`config/tools.yaml`): each top-level key under `workflows` is a
`workflow_id`, with a `description` and an ordered `steps` list. Each
step has a `step_id` (unique within the workflow) and a `step_type`,
restricted to exactly two values:

- `agent_task` — a step routed through the existing `Orchestrator` /
  `ExecutionEngine` path. Fields: `task_type`, `description`,
  `required_capabilities` (optional), `prompt_id` (optional),
  `prompt_variables` (optional) — the same fields `AgentTask` already
  has (Phase-04/08), because a workflow step's `agent_task` fields are
  used only to construct an `AgentTask`, not to reinvent one.
- `tool_call` — a step routed through the existing `ToolExecutor`.
  Fields: `tool_name`, `tool_arguments` (optional).

No other step kinds exist in this phase. This mirrors ADR-0007
decision 5's "two built-in tools only, deliberately minimal" posture:
the goal is a working, extensible *engine*, not a comprehensive step
vocabulary. See Alternatives for what is deliberately deferred
(conditional branching, parallel steps, a `memory` step kind, retries
across steps).

### 3. Nothing about `AgentTask`, `Orchestrator`, `ExecutionEngine`, `ToolExecutor`, or `MemoryManager` changes

`WorkflowEngine` is purely a caller of these four components' existing
public APIs:

- `agent_task` step → `orchestrator.submit_task(AgentTask(...))` then
  `execution_engine.execute(execution)`, exactly as any other caller
  would.
- `tool_call` step → `tool_executor.execute(tool_name, tool_arguments)`,
  exactly as any other caller would.

This closes the loop ADR-0007 decision 6 and ADR-0008 decision 7 both
left open ("no caller yet... expected future caller: Phase-11") without
requiring a single line of change to either of those phases' code —
the Open/Closed guarantee those ADRs described is exercised here for
the first time, not redefined. `MemoryManager` is **not** wired into
this phase's step vocabulary — see Alternatives; it is not needed to
satisfy the roadmap's Phase-11 scope, and adding a `memory` step kind
speculatively, without a concrete workflow that needs it yet, would
repeat the exact premature-coupling mistake ADR-0002/0004/0007 already
rejected once each.

### 4. `WorkflowRun` is a state machine that mirrors `AgentExecution`, and pauses for human approval exactly where `AgentExecution` does

`WorkflowRunState`: `PENDING -> RUNNING -> (AWAITING_APPROVAL ->
RUNNING)* -> (COMPLETED | FAILED)`. `WorkflowEngine.start(workflow_id)`
creates a `WorkflowRun` (`PENDING`), then immediately begins advancing
it (`RUNNING`). Advancing runs `tool_call` steps straight through
(store `ToolResult.output` into `WorkflowRun.context[step_id]`, move to
the next step). On an `agent_task` step, it submits and executes the
task exactly as described in Decision 3, then branches on the
resulting `AgentExecution.state`:

- `AWAITING_APPROVAL` — the expected, common case. The run itself
  transitions to `AWAITING_APPROVAL`, recording
  `pending_execution_id`, and **stops** at the current step. No
  further steps run until the run is explicitly resumed.
- `FAILED` — the run transitions to `FAILED`, copying
  `AgentExecution.error`, and stops. No later step runs (see Decision
  6 on why this phase does not attempt to skip or retry past a failed
  step).

`WorkflowEngine.resume(run_id)` is the only way an `AWAITING_APPROVAL`
run continues. It looks up the `AgentExecution` recorded as
`pending_execution_id` via the *existing, unmodified*
`Orchestrator.track()`:

- If that execution's state is not yet `COMPLETED` (i.e. a human has
  not called `Orchestrator.approve()` on it yet), `resume()` raises
  `WorkflowStepNotApprovedError` — it does not silently wait or poll.
- If it is `COMPLETED`, its `result` is copied into
  `WorkflowRun.context[step_id]`, the run moves to the next step index,
  state returns to `RUNNING`, and advancing continues (which may
  immediately hit another `agent_task` step and pause again, run
  `tool_call` steps through, or reach `COMPLETED` if that was the last
  step).

This means approving a paused workflow step is **the exact same
action** as approving any other execution — `Orchestrator.approve()` —
with no new approval API introduced. A human (or whatever future
interface calls `approve()`) does not need to know it is approving a
step of a workflow versus a standalone task.

### 5. `WorkflowRunRepository`: in-memory only this phase, same Repository Pattern shape as `ExecutionRepository`

An abstract `WorkflowRunRepository` (`add` / `update` / `get` / `list`,
identical shape to `ExecutionRepository`) plus
`InMemoryWorkflowRunRepository`, the default. No
`SqliteWorkflowRunRepository` is added in this phase — see Alternatives
for why this is deferred rather than built speculatively, matching how
Phase-04 shipped in-memory-only and Phase-05 added SQLite as its own,
later, dedicated phase.

### 6. No retry, no skip, no partial rollback across workflow steps

If a step fails (`ToolExecutionError` from a `tool_call` step, or a
`FAILED` `AgentExecution` from an `agent_task` step, exhausted per its
own `RetryPolicy` already inside `ExecutionEngine`), the run stops and
is marked `FAILED`. There is no workflow-level retry of a failed step,
no automatic skip-to-next-step, and no compensating rollback of
already-completed steps' side effects. Retrying an individual agent
invocation is already `ExecutionEngine`'s job (ADR-0004); adding a
second, workflow-level retry policy on top, with no concrete scope
requirement for it yet, would be exactly the kind of speculative
complexity this project's "avoid premature complexity" principle
(`docs/architecture/overview.md` § 2.4) rejects by default.

### 7. `WorkflowEngine`: the sole Facade, same composition-root role as `ToolExecutor` / `PromptManager`

Constructor takes an `Orchestrator`, an `ExecutionEngine`, a
`ToolExecutor`, a `WorkflowRegistry` (defaulting to one loaded from
`config/workflows.yaml`), and a `WorkflowRunRepository` (defaulting to
`InMemoryWorkflowRunRepository()`). Public methods: `start(workflow_id)
-> WorkflowRun`, `resume(run_id) -> WorkflowRun`, `get_run(run_id) ->
WorkflowRun`, `list_runs(state=None) -> list[WorkflowRun]`. No other
class is meant to be depended on directly by an external caller, the
same boundary ADR-0007 decision 1 and ADR-0006 established for
`ToolExecutor` / `PromptManager`.

### 8. Error hierarchy: new `WorkflowError(OrchestratorError)` base

`WorkflowRegistryError` (config load/validation failures, mirroring
`ToolRegistryError`), `WorkflowNotFoundError` (unknown `workflow_id`),
`UnknownWorkflowRunError` (unknown `run_id`, mirroring
`UnknownExecutionError`), `InvalidWorkflowStateTransitionError`
(mirroring `InvalidStateTransitionError` — e.g. calling `resume()` on a
run that is not `AWAITING_APPROVAL`), and
`WorkflowStepNotApprovedError` (Decision 4 — `resume()` called before
the pending `AgentExecution` reached `COMPLETED`). All live under
`WorkflowError` in `orchestrator/exceptions.py`, following the same
one-base-per-phase pattern as every prior phase.

## Architecture Diagram

```
 caller (e.g. future CLI/API surface, or a human/script driving
 approvals directly)
            │
            ▼
 ┌────────────────────────────┐
 │   WorkflowEngine              │   orchestrator/workflow/workflow_engine.py (NEW)
 │   start(workflow_id)            │   - looks up WorkflowDefinition
 │   resume(run_id)                  │   - advances steps, persists WorkflowRun
 └───────┬──────────┬─────────────┘   - pauses at AWAITING_APPROVAL agent_task steps
         │          │
         │          └────────────────────────────┐
         ▼                                        ▼
┌─────────────────────┐               ┌─────────────────────────┐
│  WorkflowRegistry      │               │  WorkflowRunRepository     │
│  loads config/workflows.yaml│         │  InMemoryWorkflowRunRepository│
└─────────────────────┘               └─────────────────────────┘

 per-step delegation (existing, UNMODIFIED components):

  step_type=agent_task            step_type=tool_call
         │                                │
         ▼                                ▼
 ┌───────────────────┐           ┌───────────────────┐
 │ Orchestrator          │           │  ToolExecutor          │
 │ + ExecutionEngine      │           │  execute(name, args)     │
 │ (ADR-0002/0004/0005)    │           │  (ADR-0007)                │
 └───────────────────┘           └───────────────────┘
```

## Alternatives Considered

- **A `memory` step kind wired to `MemoryManager` in this phase.**
  Rejected for now — no concrete workflow in this phase's approved
  scope needs to read/write Working or Persistent Memory between
  steps. `WorkflowRun.context` already gives steps access to prior
  steps' outputs within a single run, which covers this phase's needs.
  Because `StepType` is a plain enum with each value handled by one
  `if`/`match` arm inside `WorkflowEngine._advance()` (not yet a
  factory-dispatched, Open/Closed extension point — see Follow-up),
  adding a `memory` kind later is a contained, additive change, not a
  redesign.
- **Automatic, unattended completion of `agent_task` steps (bypass
  `AWAITING_APPROVAL`).** Rejected — this would violate
  `docs/architecture/overview.md` design principle 5 (human approval
  stays in the loop) for the sake of workflow convenience. See
  Context and Decision 4.
- **A workflow-level retry policy, distinct from `ExecutionEngine`'s
  per-invocation `RetryPolicy`.** Rejected for this phase — no
  concrete requirement yet for what "retry a workflow step" should
  mean (re-run just that step? from the start? does a `tool_call`
  step's side effect need to be idempotent first?). Deferred to
  whichever future phase actually needs it, matching the posture
  ADR-0007/0008 already used for their own out-of-scope items. See
  Decision 6.
- **Conditional branching / parallel step execution.** Rejected for
  this phase — `PROJECT_ROADMAP.md` names this phase "Workflow
  Engine" with no branching/parallelism requirement, and the user's
  own Phase-11 instructions for this delivery explicitly call for a
  "minimal, linear" implementation. A strictly ordered list of steps
  is the entire scope.
- **`SqliteWorkflowRunRepository` in this phase, reusing
  `orchestrator/persistence/db.py` the way `SQLiteMemoryStore` did in
  Phase-10.** Considered, and technically straightforward given the
  precedent — but rejected for this phase specifically because the
  user's Phase-11 instructions call for a minimal, linear delivery.
  `WorkflowRunRepository` is defined as an abstract interface now
  precisely so a SQLite implementation can be added later exactly the
  way ADR-0003 added `SqliteExecutionRepository` a full phase after
  `Orchestrator` first shipped in-memory-only, with zero changes to
  `WorkflowEngine`.
- **A generic `StepFactory` (`step_type -> handler`) instead of two
  hard-coded branches in `WorkflowEngine`.** Considered, mirroring
  `ToolFactory` / `ProviderFactory`'s Open/Closed dict-registration
  pattern. Deferred rather than rejected outright — with exactly two
  step kinds and no evidence yet of a third, near-term one, introducing
  a factory abstraction now would be speculative structure the same
  way ADR-0008 decision 6 rejected a `MemoryFactory` with only two
  `MemoryStore` implementations. If a third step kind is added later
  (see the `memory` step kind above), this should be revisited then,
  not now.

## Consequences

### Positive

- `ToolExecutor` and `MemoryManager`'s "no caller yet" status (ADR-0007
  decision 6, ADR-0008 decision 7) is finally exercised for
  `ToolExecutor`, with zero changes to either component.
- A working, minimal, linear Workflow Engine exists:
  `WorkflowRegistry` / `WorkflowRunRepository` / `WorkflowEngine`, all
  under `orchestrator/workflow/`, config-driven via
  `config/workflows.yaml`, following the same shape as every prior
  phase's registry + Facade.
- Human-in-the-loop approval is preserved structurally for every
  `agent_task` step inside a workflow, with no new approval mechanism
  — `Orchestrator.approve()` is reused unmodified.
- `AgentTask`, `AgentExecution`, `Orchestrator`, `ExecutionEngine`,
  both `AgentInvoker` implementations, `AgentRegistry`,
  `ModelProviderRegistry`, `PromptManager`, `ToolExecutor`, and
  `MemoryManager` are all unchanged by this phase; all pre-Phase-11
  tests remain valid unmodified.
- Adding a `SqliteWorkflowRunRepository` later, or a third step kind,
  are both additive changes against interfaces already defined here,
  not redesigns.

### Negative

- A workflow containing any `agent_task` step cannot complete in a
  single call — callers must be prepared to see `AWAITING_APPROVAL`
  and call `resume()` after the corresponding execution is approved
  elsewhere. This is an accepted consequence of Decision 4, not an
  oversight.
- `WorkflowRun` state is lost on process restart in this phase
  (`InMemoryWorkflowRunRepository` only) — a run left `AWAITING_APPROVAL`
  when the process exits cannot be resumed after restart until a
  durable repository is added. Accepted per Decision 5 / Alternatives.
- A failed step cannot be retried or skipped without starting a new
  run from `config/workflows.yaml` — accepted per Decision 6.

## Follow-up

- `SqliteWorkflowRunRepository`, reusing `orchestrator/persistence/db.py`
  the way Phase-10's `SQLiteMemoryStore` did, is deferred to a future
  phase or patch release once a concrete durability requirement exists.
- A `memory` step kind wiring `WorkflowEngine` to `MemoryManager` is
  deferred until a concrete workflow needs cross-run or cross-step
  persistent context beyond what `WorkflowRun.context` already
  provides within a single run.
- Workflow-level retry, conditional branching, and parallel step
  execution are all deliberately out of scope for Phase-11 and are not
  implemented here; each would need its own ADR given the added
  control-flow and failure-semantics surface.
- A `StepFactory`-style Open/Closed extension point for `step_type` is
  left for whichever future phase adds a third step kind (see
  Alternatives) — not introduced speculatively here.
