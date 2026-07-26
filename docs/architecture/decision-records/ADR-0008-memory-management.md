# ADR-0008: Memory Management (Phase-10)

- **Status:** Accepted
- **Date:** Phase-10
- **Deciders:** Lead AI Systems Architect

## Context

`PROJECT_ROADMAP.md` lists Phase-10 as "Memory Management", the next
planned phase after Phase-09's Tool Execution Framework. As with
Phase-09 (ADR-0007), the roadmap names this phase but does not specify
its scope, so the concrete design was proposed and approved before
implementation, per this project's "docs before code" / ADR-first
governance.

Through Phase-09, nothing in the repository lets an agent, a tool, or
the orchestrator itself store and later retrieve a named piece of
information across calls. `AgentTask`/`AgentExecution` capture a single
execution's own state (Phase-04/05); `PromptManager` resolves and
renders a versioned template (Phase-08); `ToolExecutor` runs a
self-contained operation and returns a `ToolResult` (Phase-09). None of
these give a caller a place to write "remember this value under this
name" and read it back later, either within one process's lifetime or
across restarts.

The following scope was proposed and approved:

- Implement both **Working Memory** (in-process, ephemeral) and
  **Persistent Memory** (durable across restarts) only.
- Explicitly out of scope: semantic memory, embeddings, vector
  databases, retrieval ranking, similarity search. This phase is a
  named key/value store, not a retrieval system.
- Keep the Memory subsystem self-contained -- no integration with
  `ExecutionEngine`, `ToolExecutor`, providers, or `AgentTask` this
  phase.
- Reuse the existing persistence architecture (Repository Pattern,
  SQLite backend, InMemory implementation) rather than introducing a
  new persistence framework.

## Decision

### 1. New `orchestrator/memory/` package, same shape as `orchestrator/tools/` and `orchestrator/persistence/`

`models.py` (`MemoryEntry` -- a frozen dataclass, matching every prior
phase's data-model convention), `memory_store.py` (`MemoryStore`
Protocol -- the Port), `in_memory_store.py` (`InMemoryStore`),
`schema.py` + `serializers.py` (SQLite table definition and row
conversion, mirroring `orchestrator/persistence/schema.py` /
`serializers.py`), `sqlite_memory_store.py` (`SQLiteMemoryStore`), and
`memory_manager.py` (`MemoryManager`, the Facade).

### 2. `MemoryStore` is a `typing.Protocol`, not `abc.ABC`

Unlike `ExecutionRepository` (Phase-05, `abc.ABC`), `MemoryStore`
follows the `ModelProvider` (Phase-07) / `Tool` (Phase-09) convention
of a structural `typing.Protocol` Port. This was an explicit part of
the approved scope. The contract mirrors `ExecutionRepository`'s CRUD
shape (`add` / `update` / `get` / `list`), with `delete` added since
"forgetting" a value is a first-class Memory operation that has no
`ExecutionRepository` analogue:

```python
class MemoryStore(Protocol):
    def add(self, entry: MemoryEntry) -> None: ...
    def update(self, entry: MemoryEntry) -> None: ...
    def get(self, key: str, scope: str = "default") -> MemoryEntry: ...
    def delete(self, key: str, scope: str = "default") -> None: ...
    def list(self, scope: str | None = None) -> list[MemoryEntry]: ...
```

An entry is uniquely identified by its `(key, scope)` pair (`scope` is
a free-form namespace, e.g. an agent name or session id, defaulting to
`"default"`). `add()` raises `MemoryEntryAlreadyExistsError` for a
duplicate `(key, scope)`; `update()`/`get()`/`delete()` raise
`MemoryEntryNotFoundError` when the pair does not exist -- the same
fail-loudly posture `ExecutionRepository` established in Phase-05.

### 3. `MemoryEntry`: a frozen dataclass with an id distinct from its lookup key

```python
id: str  # internal identity, uuid4, default_factory
key: str  # lookup name within a scope
value: str  # the stored value
scope: str = "default"
created_at: datetime  # UTC, default_factory
updated_at: datetime  # UTC, default_factory
metadata: dict[str, str] = field(default_factory=dict)
```

`id` and `(key, scope)` serve different purposes: `id` is the record's
own identity (and SQLite primary key); `(key, scope)` is how a caller
looks a value up, matching how `AgentExecution.execution_id` (identity)
and `AgentTask.task_id` (a different concept) already coexist in
`orchestrator.models`. This mirrors `AgentTask`/`AgentExecution`'s
`uuid.uuid4()` / `datetime.now(UTC)` `default_factory` conventions
exactly (Phase-04).

### 4. `InMemoryStore` and `SQLiteMemoryStore`: Working Memory and Persistent Memory

`InMemoryStore` is a `dict[(scope, key), MemoryEntry]`-backed
implementation, the Memory-subsystem analogue of
`InMemoryExecutionRepository` (Phase-05) -- this **is** Working Memory:
ephemeral, process-lifetime-only, zero setup.

`SQLiteMemoryStore` is backed by a new `memory_entries` table in the
*same* SQLite database file `orchestrator/persistence/db.py` already
uses (`DEFAULT_SQLITE_PATH`, i.e. `data/aeos.db`), reusing
`persistence.db.connect()` for connection setup (row factory, foreign
keys, WAL mode) exactly as `SqliteExecutionRepository` does -- this
**is** Persistent Memory. Its own `orchestrator/memory/schema.py`
additively creates `memory_entries` (`UNIQUE(key, scope)`) and records
`memory_schema_version` in the pre-existing `schema_meta` table; it
does not modify `orchestrator/persistence/schema.py` or the
`executions` table in any way. No new persistence framework, ORM, or
connection-pooling layer is introduced -- this is the same
single-connection, WAL-mode, `IF NOT EXISTS`-idempotent approach
ADR-0003 already established, applied to one additional table.

### 5. `MemoryManager`: the sole Facade, same architectural style as `PromptManager` / `ToolExecutor`

`MemoryManager` composes a `MemoryStore` (constructor-injected,
defaulting to `InMemoryStore()` -- i.e. Working Memory is the default,
mirroring `ExecutionRepository`'s Phase-05 in-memory default) and adds
higher-level operations a raw store does not provide, the same way
`PromptManager` adds `resolve()`/`render()` on top of `PromptRegistry`
and `ToolExecutor` adds argument validation on top of `ToolRegistry`:

- `remember(key, value, scope="default", metadata=None) -> MemoryEntry`
  -- upsert: creates a new entry via `store.add()` if `(key, scope)` is
  new, or updates the existing one via `store.update()` (preserving
  `id`/`created_at`, refreshing `updated_at`) if it already exists.
  Callers never need to know in advance whether a key already has a
  value.
- `recall(key, scope="default") -> MemoryEntry` -- thin pass-through to
  `store.get()`.
- `forget(key, scope="default") -> None` -- thin pass-through to
  `store.delete()`.
- `list(scope=None) -> list[MemoryEntry]` -- thin pass-through to
  `store.list()`.

Constructing `MemoryManager(SQLiteMemoryStore())` gives Persistent
Memory; the default `MemoryManager()` gives Working Memory. Both are
the same Facade over the same Protocol -- there is no separate
"WorkingMemoryManager" / "PersistentMemoryManager" class, matching how
`Orchestrator` does not have separate classes per
`ExecutionRepository` implementation either.

### 6. No `MemoryFactory`, no `config/memory.yaml`

Every prior config-driven subsystem in this project (`AgentRegistry`,
`ModelProviderRegistry`, `PromptRegistry`, `ToolRegistry`) exists
because a caller needed to select *one of many named, declaratively
configured* things (an agent, a provider, a prompt, a tool) by a
string key from YAML. Memory has no such requirement in this phase's
approved scope: there are exactly two `MemoryStore` implementations,
selected once at construction time by the caller instantiating
`MemoryManager`, not resolved by name at call time. Introducing a
factory/registry/YAML-config layer here would be exactly the kind of
speculative structure ADR-0003 and ADR-0007 already avoided when no
concrete forcing requirement exists yet.

### 7. Nothing outside `orchestrator/memory/` changes in this phase

`AgentTask`, `Orchestrator`, `ExecutionEngine`, both `AgentInvoker`
implementations, `AgentRegistry`, `ModelProviderRegistry`,
`PromptManager`, and `ToolExecutor` are all untouched, per the approved
scope. `orchestrator/persistence/schema.py` and the `executions` table
are also untouched -- Phase-10 only *adds* a new table to the shared
database file. This is the same self-contained, no-caller-yet posture
ADR-0007 decision 6 established for `ToolExecutor`; wiring Memory into
the execution/agent-task lifecycle (e.g. so an `AgentTask` could read
prior Working Memory) is left to whichever future phase actually needs
it (most likely Phase-11's Workflow Engine, alongside `ToolExecutor`).

### 8. Error hierarchy: new `MemoryManagementError(OrchestratorError)` base

Named `MemoryManagementError` rather than `MemoryError` to avoid
shadowing the Python builtin `MemoryError`, and to match the existing
`PromptManagementError` naming convention (Phase-08) rather than the
shorter `ToolError` (Phase-09) / `ModelProviderError` (Phase-07) style,
specifically because of that name collision risk. Three subclasses:
`MemoryEntryNotFoundError`, `MemoryEntryAlreadyExistsError`, and
`MemorySerializationError` (raised by `SQLiteMemoryStore` on corrupt
stored data -- e.g. non-JSON `metadata` -- mirroring
`ExecutionSerializationError`, Phase-05). Because nothing outside
`orchestrator/memory/` calls `MemoryManager` yet (decision 7), none of
this hierarchy needs a retry/propagation contract with
`ExecutionEngine`, unlike the Phase-06/07/08 hierarchies.

## Architecture Diagram

```
 (No caller yet in this phase -- see decision 7.
  Expected future caller: Phase-11 Workflow Engine)
            │
            ▼
 ┌───────────────────────┐
 │   MemoryManager          │   orchestrator/memory/memory_manager.py (NEW)
 │   remember/recall/forget/  │   - upsert logic (add vs update)
 │   list                       │   - thin pass-through otherwise
 └──────────┬────────────────┘
            │  depends on the MemoryStore Protocol only
            ▼
 ┌───────────────────────┐
 │      MemoryStore          │   orchestrator/memory/memory_store.py (NEW)
 │      (Protocol / Port)      │
 └──────────┬────────────────┘
            │
   ┌────────┴─────────┐
   ▼                   ▼
┌────────────┐   ┌───────────────────┐
│ InMemoryStore │   │ SQLiteMemoryStore    │
│ (Working Memory)│   │ (Persistent Memory)    │
│ dict-backed      │   │ reuses persistence.db.  │
│                    │   │ connect() + new schema.py│
└────────────┘   └───────────────────┘
```

## Alternatives Considered

- **Single class handling both storage modes via an `is_persistent`
  flag.** Rejected: this is exactly the `if/elif` branching-client
  anti-pattern ADR-0005 (Model Providers) and ADR-0007 (Tools) already
  rejected in favor of the Protocol/Port pattern. Two small,
  single-purpose classes behind one Protocol is more consistent with
  the rest of this codebase.
- **Semantic/vector memory now.** Rejected per the approved scope: it
  would require a new external dependency (an embeddings client and/or
  a vector store) without an ADR-approved dependency addition, and no
  current caller needs similarity search. Left for a future phase if a
  concrete need emerges.
- **A `MemoryFactory` + `config/memory.yaml`, mirroring
  `ToolFactory`/`ToolRegistry`.** Rejected -- see decision 6. There is
  no set of *named* memory backends to select between by string key;
  there are exactly two concrete classes, chosen once at construction.

## Follow-up (explicitly deferred, not part of Phase-10)

- Wiring `MemoryManager` into `AgentTask`/`ExecutionEngine`/
  `ToolExecutor` so an agent's own execution can read/write memory
  (most likely Phase-11).
- Scope-based expiry/TTL for Working Memory entries.
- Semantic/embedding-based recall, if a concrete consumer emerges.
