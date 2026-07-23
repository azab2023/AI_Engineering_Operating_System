# ADR-0003: Persistence Layer (Phase-05)

- **Status:** Accepted
- **Date:** Phase-05
- **Deciders:** Lead AI Systems Architect

## Context

ADR-0002's Follow-up section explicitly flagged this as open work:
"Phase-05: persistence for `AgentExecution` state." At the end of
Phase-04, `Orchestrator` held all execution state in a plain
`dict[str, AgentExecution]` owned by the instance -- restarting the
process discarded every execution record, including ones sitting in
`AWAITING_APPROVAL` waiting on a human.

Separately, before this phase began, a repository audit found that
`PROJECT_ROADMAP.md` had been updated to mark Phase-05 as complete
(`v0.5.0`) despite no `orchestrator/persistence/` package, no SQLite
repository, no CI workflow, no `ADR-0003`, and no `pyproject.toml` /
`requirements-dev.txt` existing anywhere in the repository. That prior
"completion" was not real. This ADR and the code landing alongside it
are the actual Phase-05 implementation; `PROJECT_ROADMAP.md` is
corrected to match only once this work is done, not before.

## Decision

### 1. Repository Pattern via an `ExecutionRepository` interface

`orchestrator/persistence/repository.py` defines `ExecutionRepository`
as an `abc.ABC` with `add` / `update` / `get` / `list`.
`orchestrator.core.Orchestrator` depends only on this interface, never
on a concrete storage type. This keeps orchestration logic (selection,
state-machine guards) decoupled from storage, and keeps `core.py`
unit-testable without a real database.

### 2. Two implementations: `InMemoryExecutionRepository` (default) and `SqliteExecutionRepository`

`InMemoryExecutionRepository` reproduces Phase-04's exact dict-backed
behavior, now living behind the new interface. It remains the **default**
(`Orchestrator(registry)` with no `repository` argument) so every
Phase-04 call site keeps working unmodified -- this is what makes Phase-05
backward compatible rather than a breaking change dressed up as an
addition.

`SqliteExecutionRepository` (`orchestrator/persistence/sqlite_repository.py`)
is the new durable backend, opted into via
`Orchestrator(registry, repository=SqliteExecutionRepository(registry))`.

### 3. SQLite, stdlib `sqlite3`, no ORM

Chosen for the same reason `models.py` avoids pydantic/ORM libraries in
Phase-04: minimal dependencies, and the current scope (single AEOS
process, one execution store) does not justify a client/server database
or an ORM's abstraction cost. `requirements.txt` gains no new runtime
dependency because of this choice.

### 4. Scope: `AgentExecution` only, not `AgentRegistry`

Only execution records are persisted. `AgentRegistry` continues to load
from `config/agent_registry.yaml` on every process start, unchanged.
Migrating agent definitions into SQLite was not requested and would
conflict with ADR-0002 decision 2 (YAML as the canonical, human-edited
source for agent metadata).

### 5. `assigned_agent` stored by name, resolved via the registry on read

SQLite cannot (and should not) store a full `Agent` object -- `agent_
registry.yaml` is that object's source of truth. `executions.
assigned_agent_name` stores only the name; `orchestrator/persistence/
serializers.py` resolves it back into an `Agent` via `AgentRegistry.
get_agent()` when a row is read. If the name is no longer in the
registry, this is treated as data corruption relative to the *current*
registry and raises `ExecutionSerializationError` (fail loudly, per the
existing `orchestrator/exceptions.py` philosophy) rather than silently
returning an execution with a dropped assignment.

### 6. Explicit `update()` calls at every mutation site in `core.py`

Because `AgentExecution` is a mutable dataclass, Phase-04's dict-backed
store reflected mutations "for free" (same object reference). A SQLite
row does not update itself when the in-memory object it came from is
mutated. Rather than hide this behind repository magic, every method in
`Orchestrator` that changes execution state (`route`,
`mark_awaiting_approval`, `approve`, including the failure path in
`route`) now calls `self._repository.update(execution)` immediately
after mutating and `touch()`-ing the execution. This keeps persistence
timing explicit and auditable at each state transition, matching the
existing logging call placed right after each transition.

### 7. No migration framework

`orchestrator/persistence/schema.py` creates tables with
`CREATE TABLE IF NOT EXISTS` and records a `schema_version` in a
`schema_meta` table, but no migration runner is built. A single-table
schema does not yet justify one; `schema_meta` exists as the hook a
future migration tool would use, not as a promise one exists today.

### 8. CI workflow added in the same phase

`.github/workflows/ci.yml` runs `ruff check` and `pytest` on every push
and pull request. This was Planned-but-never-built since Phase-01's
roadmap (`docs/setup/getting-started.md` and `PROJECT_ROADMAP.md`'s
"CI must remain green" note both presuppose it exists); Phase-05 is the
first phase to actually introduce a persistence/storage surface worth
gating on tests, so it is built now rather than deferred again.

## Consequences

- Existing Phase-04 code and tests that construct `Orchestrator(registry)`
  with no second argument are unaffected -- verified by
  `tests/test_orchestrator_workflow.py`, which now runs the full
  submit → route → approve workflow against both repository
  implementations.
- Callers that want durable execution history must explicitly construct
  and pass a `SqliteExecutionRepository`; nothing is persisted by
  accident.
- `pyproject.toml` and `requirements-dev.txt` are introduced to support
  `ruff`/`pytest` in CI without bloating `requirements.txt` (a runtime
  manifest) with dev-only tooling.

## Follow-up

- Phase-06 (Agent Execution Engine) is expected to be the first real
  consumer of durable execution history -- e.g. resuming
  `AWAITING_APPROVAL` executions after a restart. No such resumption
  logic is implemented in Phase-05; only the storage it depends on is.
- `config/` vs `configs/` remains open (carried over from ADR-0001/
  ADR-0002), unaffected by this phase.
- If a second AEOS process ever needs to share one SQLite file
  concurrently, the "one connection per repository instance, no pooling"
  approach in `orchestrator/persistence/db.py` should be revisited.
