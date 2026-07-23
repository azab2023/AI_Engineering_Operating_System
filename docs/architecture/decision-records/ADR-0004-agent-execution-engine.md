# ADR-0004: Agent Execution Engine (Phase-06)

- **Status:** Accepted
- **Date:** Phase-06
- **Deciders:** Lead AI Systems Architect

## Context

ADR-0002 flagged this explicitly: "Agent adapters (actual invocation of
each agent) are required before `route()`'s RUNNING state means anything
beyond 'assigned.'" Through Phase-05, `Orchestrator.route()` selects an
agent and persists a RUNNING execution, but nothing ever invokes that
agent -- an execution can sit in RUNNING forever with no CLI call ever
made, and there is no way to reach AWAITING_APPROVAL other than calling
`mark_awaiting_approval()` by hand.

Separately, `docs/architecture/agent-integration.md` records that every
configured agent (`claude_code`, `codex`, `aider`, `gemini`) is a CLI
tool invoked from the shell or an IDE integration, not a raw HTTP model
API. `requirements.txt` has no HTTP client library, which is consistent
with that: there was never a raw-API integration to build in the first
place.

## Decision

### 1. `ExecutionEngine` is the missing invocation step, not a second orchestrator

`orchestrator/execution/engine.py` adds `ExecutionEngine.execute(execution)`,
which: routes a PENDING execution via the existing `Orchestrator.route()`
if needed, invokes the assigned agent, retries transient failures, and
records the outcome via `Orchestrator.mark_awaiting_approval()` (success)
or the new `Orchestrator.mark_failed()` (retries exhausted). It holds no
state of its own and does not duplicate `Orchestrator`'s selection or
state-machine logic -- it is a thin driver on top of it, matching the
existing layering (`core.py` owns state; `persistence/` owns storage;
`execution/` now owns invocation).

### 2. `AgentInvoker` port + `SubprocessAgentInvoker` adapter

`orchestrator/execution/invoker.py` defines `AgentInvoker` as a
`typing.Protocol` with one method, `invoke(agent, task) -> ExecutionResult`.
`ExecutionEngine` depends only on this interface, the same Repository-
pattern choice ADR-0003 made for storage: it keeps `ExecutionEngine`'s
retry/state-transition logic unit-testable with a fake invoker, with no
subprocess spawned in those tests (see `tests/test_execution_engine.py`),
while `tests/test_execution_invoker.py` covers the real
`SubprocessAgentInvoker` separately against real (but harmless, inline
Python) subprocesses.

`SubprocessAgentInvoker` is the only implementation for this phase: it
shells out to each agent's configured CLI command via
`subprocess.run(argv, shell=False, ...)`. `shell=False` with an argv list
is deliberate -- a task description is arbitrary text that must never be
interpreted by a shell, so command injection via a task description is
not possible by construction (covered by
`test_task_description_is_not_shell_interpreted`).

### 3. New `config/agent_commands.yaml`, not a new field on `agent_registry.yaml`

Invocation commands are loaded from a separate file, via the new
`AgentCommandRegistry` (`orchestrator/execution/command_registry.py`),
rather than adding a `command` field to `Agent` / `agent_registry.yaml`.
`AgentRegistry` is selection metadata (capabilities, priority,
availability); giving it invocation knowledge would recreate the coupling
ADR-0002 already avoided once. This is also why Phase-06 needed zero
changes to `orchestrator/models.py`, `orchestrator/registry.py`, or the
existing `agent_registry.yaml` -- fully additive, fully backward
compatible.

`AgentCommandRegistry` validates the same way `AgentRegistry` does:
missing file, invalid YAML, missing `commands` key, missing required
per-agent fields (`command`, `timeout_seconds`), a `command` that isn't a
non-empty list of strings, a `command` missing the `{task_description}`
placeholder, and a non-positive `timeout_seconds` are all rejected at
load time with a specific `AgentCommandRegistryError`, rather than
failing confusingly at invocation time.

### 4. Retryable vs. non-retryable failures

Two invoker-side outcomes are treated as retryable by `ExecutionEngine`:
a CLI exit code other than 0 (`ExecutionResult.succeeded() is False`),
and `AgentTimeoutError` (the CLI ran past `timeout_seconds`).
`AgentInvocationError` (the executable could not even be started, e.g.
missing from `PATH`) is also retried rather than failed immediately --
a CLI briefly missing from `PATH` in a containerized/ephemeral runner is
indistinguishable from a permanently missing one without a second
attempt, and the cost of one extra attempt is low. `AgentCommandNotConfiguredError`
(an agent with no entry in `agent_commands.yaml`) is a configuration bug,
not a transient condition; it is not caught by the invoke loop and
propagates immediately.

### 5. `RetryPolicy`: exponential backoff, 3 attempts by default

`orchestrator/execution/models.py` adds `RetryPolicy(max_attempts=3,
initial_backoff_seconds=1.0, backoff_multiplier=2.0)` as a small frozen
dataclass, matching Phase-04's "plain dataclasses, no external validation
library" convention. `ExecutionEngine` accepts an injected `RetryPolicy`
so tests run with zero delay (`initial_backoff_seconds=0`) instead of
sleeping.

### 6. `Orchestrator.mark_failed()` added for RUNNING -> FAILED

Before this phase, `FAILED` was reachable only from `route()`'s own
selection-failure path; there was no way to fail an execution that was
already RUNNING. `mark_failed()` fills that gap with the same guard
pattern as every other transition method (`track()` then a state check
raising `InvalidStateTransitionError`, then mutate + `touch()` +
`self._repository.update()` + log), so a failed invocation is persisted
with the same rigor as a successful one instead of being left stuck in
RUNNING forever.

### 7. `route()` failures inside `ExecutionEngine.execute()` are not re-raised

If `execute()` is called with a PENDING execution and `Orchestrator.route()`
raises (`NoSuitableAgentError` / `AgentUnavailableError`), `route()` has
already transitioned and persisted that execution as FAILED.
`ExecutionEngine.execute()` catches those two exceptions specifically and
returns the now-FAILED execution instead of propagating, so callers can
branch on `result.state` uniformly regardless of whether routing or
invocation is what failed. Any other exception during routing is a
genuine bug and is not swallowed.

## Consequences

- RUNNING now means "an agent CLI is actually being invoked," closing the
  gap ADR-0002 flagged. `AWAITING_APPROVAL` executions produced by
  `ExecutionEngine` flow into the existing Phase-04 `approve()` /
  Phase-05 persistence path unchanged.
- No new runtime dependency: `SubprocessAgentInvoker` uses only the
  stdlib `subprocess` module. `requirements.txt` is unchanged.
- Operators must populate `config/agent_commands.yaml` with a real,
  installed CLI command for every agent in `agent_registry.yaml`, or
  `ExecutionEngine.execute()` for that agent will fail immediately with
  `AgentCommandNotConfiguredError` on first invocation.
- `ExecutionResult`/`AgentCommand` intentionally live in
  `orchestrator/execution/models.py`, not `orchestrator/models.py` --
  they are Phase-06-only concepts, so Phase-04's model module is
  untouched.

## Follow-up

- Phase-07 (Model Provider Abstraction, per `PROJECT_ROADMAP.md`) is the
  natural place to add a second `AgentInvoker` implementation for raw
  HTTP provider APIs, if a non-CLI agent is ever added. `ExecutionEngine`
  requires no changes for that -- only a new invoker.
- `ExecutionEngine` does not currently resume executions left in RUNNING
  by a prior process crash (a RUNNING row with no invocation in flight).
  ADR-0003's follow-up anticipated this; it remains open.
- Per-agent concurrency limits / rate limiting are not implemented --
  `ExecutionEngine.execute()` handles one execution at a time by design;
  any concurrency is the caller's responsibility.
