# AI Engineering Operating System (AEOS)
# Project Roadmap

**Project Status:** Active Development

Current Version: **v1.3.0**

Current Branch: **phase-13**

Last Completed Phase: **Phase-13 – Monitoring & Observability**

---

# Completed Phases

| Phase | Status | Version | Description |
|--------|--------|---------|-------------|
| Phase-01 | ✅ | v0.1.x | Project Architecture |
| Phase-02 | ✅ | v0.2.x | Configuration System |
| Phase-03 | ✅ | v0.3.x | Excel Template & Data Schema |
| Phase-04 | ✅ | v0.4.1 | Agent Orchestration Layer |
| Phase-05 | ✅ | v0.5.0 | Persistence Layer (SQLite + Repository Pattern + CI/CD) |
| Phase-06 | ✅ | v0.6.0 | Agent Execution Engine (Subprocess AgentInvoker + Retry Policy + ADR-0004) |
| Phase-07 | ✅ | v0.7.0 | Model Provider Abstraction (ModelProvider Protocol + Anthropic/OpenAI/Gemini adapters + HttpAgentInvoker + ADR-0005) |
| Phase-08 | ✅ | v0.8.0 | Prompt Management System (PromptRegistry + PromptManager + template rendering + AgentTask.prompt_id + ADR-0006) |
| Phase-09 | ✅ | v0.9.0 | Tool Execution Framework (Tool Protocol + ToolRegistry + ToolFactory + ToolExecutor + built-in read_file/list_directory tools + ADR-0007) |
| Phase-10 | ✅ | v1.0.0 | Memory Management (MemoryStore Protocol + InMemoryStore/SQLiteMemoryStore + MemoryManager facade + MemoryEntry model + ADR-0008) |
| Phase-11 | ✅ | v1.1.0 | Workflow Engine (WorkflowRegistry + WorkflowRunRepository + WorkflowEngine facade composing Orchestrator/ExecutionEngine + ToolExecutor + ADR-0009) |
| Phase-12 | ✅ | v1.2.0 | Security & Permissions (PathSandboxPolicy + AgentPermission + PermissionRegistry + ToolAuthorizer + agent_name-aware ToolExecutor/WorkflowStep + ADR-0010) |
| Phase-13 | ✅ | v1.3.0 | Monitoring & Observability (ObservabilityEvent/MetricPoint/ObservabilityConfig models + InMemoryRecorder + ObservabilityRegistry + ObservabilityManager facade + Observer pattern wired into Orchestrator/ExecutionEngine/ToolExecutor/WorkflowEngine + ADR-0011) |

---

# Planned Phases

| Phase | Status | Description |
|--------|--------|-------------|
| Phase-14 | ⏳ | Plugin & Extension System |
| Phase-15 | ⏳ | Production Release (v1.0) |

---

# Current Focus

**Phase-13 has been implemented and verified** (new
`orchestrator/observability/` package -- `ObservabilityEvent` /
`MetricPoint` / `ObservabilityConfig` models, `InMemoryRecorder`
implementing the new `ObservabilityRecorder` Protocol,
`ObservabilityRegistry` loading/validating the new
`config/observability.yaml`, and `ObservabilityManager` as a
query/record facade); three new exceptions under a new
`ObservabilityError` base in `orchestrator/exceptions.py`; ADR-0011.
`Orchestrator`, `ExecutionEngine`, `ToolExecutor`, and `WorkflowEngine`
each gain one new, optional, backward-compatible `observer:
ObservabilityRecorder | None = None` constructor parameter (the
Observer pattern) -- when omitted, behavior is byte-for-byte identical
to pre-Phase-13; when supplied, each component records the structured
events, counters, and timers documented in ADR-0011 decision 5's
table, with `ToolExecutor` reusing `ToolResult.duration_seconds`
rather than re-measuring it. Storage is in-memory only this phase, by
explicit decision -- no SQLite reuse, no exporters, no health-check
endpoints, no dashboards. `AgentTask`, `AgentRegistry`,
`ModelProviderRegistry`, `PromptManager`, `MemoryManager`, and
`ToolAuthorizer` are all unchanged by this phase; 499 tests passing
(42 new), Ruff check + format clean, up from 457 at Phase-12 close.
Phase-14 has not started.

**Phase-13 – Monitoring & Observability** objectives (all met):

- Structured events, counters/timers, and duration measurements,
  internal only -- no exporters, no health-check endpoints, no
  dashboards, no HTTP monitoring APIs. ✅ (`ObservabilityEvent`,
  `MetricPoint`; ADR-0011 Context/decision 2)
- Observer pattern integration with zero required changes to any
  existing call site. ✅ (`observer: ObservabilityRecorder | None =
  None` on `Orchestrator`/`ExecutionEngine`/`ToolExecutor`/
  `WorkflowEngine`; ADR-0011 decision 5)
- Open/Closed for storage: integrated components depend on the
  `ObservabilityRecorder` Protocol, not `InMemoryRecorder`. ✅
  (ADR-0011 decision 3, Follow-up)
- Config-driven enable/disable, matching the existing registry
  validation pattern. ✅ (`config/observability.yaml`,
  `ObservabilityRegistry`; ADR-0011 decision 4)
- Preserve backward compatibility. ✅ (every new parameter defaults to
  `None`; all 457 pre-Phase-13 tests remain valid unmodified;
  ADR-0011 Consequences)

**Phase-12 – Security & Permissions** objectives (all met):

- Close the ADR-0007 Follow-up path-sandboxing deferral for
  `ReadFileTool` / `ListDirectoryTool`. ✅ (`PathSandboxPolicy`,
  `sandboxed_parameters`, `ToolAuthorizer._authorize_paths()`;
  ADR-0010 decisions 2, 5, 7)
- Close the Phase-02-era per-agent `config/permissions.yaml`
  ("what this agent may read/write") deferral. ✅
  (`agent_permissions` section, `AgentPermission`, `access_mode`,
  `ToolAuthorizer._authorize_agent()`; ADR-0010 decisions 3, 4, 5, 7)
- One reusable, centralized authorization layer -- no permission logic
  duplicated in `ToolExecutor` or any individual `Tool`. ✅
  (`ToolAuthorizer.authorize()`; ADR-0010 decision 7)
- Open/Closed: a future filesystem-touching tool inherits both checks
  automatically via its `config/tools.yaml` entry, with zero
  `ToolExecutor` changes. ✅ (ADR-0010 decision 5 / Follow-up)
- Preserve backward compatibility. ✅ (`sandboxed_parameters`,
  `access_mode`, `ToolExecutor.execute()`'s `agent_name`, and
  `WorkflowStep.agent_name` are all optional and default to
  pre-Phase-12 behavior; every pre-Phase-12 test remains valid
  unmodified; ADR-0010 decision 8/9, Consequences)

**Phase-11 – Workflow Engine** objectives (all met):

- Compose existing components (`Orchestrator`/`ExecutionEngine`,
  `ToolExecutor`) into a named, ordered, linear sequence of steps. ✅
  (`orchestrator/workflow/` -- `WorkflowEngine.start()`/`resume()`,
  `WorkflowRegistry` loading `config/workflows.yaml`)
- Exactly two step kinds, config-driven, minimal scope. ✅
  (`StepType.AGENT_TASK` / `StepType.TOOL_CALL`; ADR-0009 decision 2)
- Preserve human-in-the-loop approval for every `agent_task` step,
  with no new approval mechanism. ✅ (`WorkflowRun` pauses at
  `AWAITING_APPROVAL`; `resume()` requires `Orchestrator.approve()` to
  have already been called; ADR-0009 decision 4)
- Close the "no caller yet" status ADR-0007 decision 6 left open for
  `ToolExecutor`. ✅ (`WorkflowEngine._run_tool_step()`)
- Preserve backward compatibility. ✅ (`AgentTask`, `Orchestrator`,
  `ExecutionEngine`, both `AgentInvoker` implementations,
  `AgentRegistry`, `ModelProviderRegistry`, `PromptManager`,
  `ToolExecutor`, and `MemoryManager` all unchanged; ADR-0009 decision 3)

**Phase-09 – Tool Execution Framework** objectives (all met):

- Discrete, named, config-driven tools, independent of any agent's
  CLI/API session. ✅ (`orchestrator/tools/` -- `Tool` Protocol,
  `ToolRegistry` loading `config/tools.yaml`)
- Open/Closed tool extensibility. ✅ (`ToolFactory` registration dict;
  ADR-0007 decision 4)
- Fail-loudly argument validation before any tool runs. ✅
  (`ToolExecutor._validate_arguments()`)
- Configurable enable/disable per tool. ✅ (`enabled: true|false` in
  `config/tools.yaml`)
- Minimal, safe built-in tools only. ✅ (`ReadFileTool`,
  `ListDirectoryTool`)
- Preserve backward compatibility. ✅ (see ADR-0007 decision 6)

**Phase-10 – Memory Management** objectives (all met):

- Working Memory (in-process, ephemeral) and Persistent Memory
  (durable across restarts) only -- no semantic memory, embeddings,
  vector databases, or similarity search. ✅ (`InMemoryStore`,
  `SQLiteMemoryStore`; ADR-0008 context)
- Open/Closed backend extensibility via a Port, not an `if/elif`
  chain. ✅ (`MemoryStore` Protocol; ADR-0008 decision 2)
- Reuse the existing persistence architecture (Repository Pattern,
  SQLite backend, InMemory implementation) rather than a new
  persistence framework. ✅ (`SQLiteMemoryStore` reuses
  `persistence.db.connect()`; ADR-0008 decision 4)
- A single Facade, matching `PromptManager`/`ToolExecutor`'s
  architectural style. ✅ (`MemoryManager.remember/recall/forget/list`;
  ADR-0008 decision 5)
- Preserve backward compatibility. ✅ (no changes to `AgentTask`,
  `Orchestrator`, `ExecutionEngine`, either `AgentInvoker`,
  `AgentRegistry`, `ModelProviderRegistry`, `PromptManager`,
  `ToolExecutor`, or `orchestrator/persistence/schema.py`; ADR-0008
  decision 7)

**Phase-06 – Agent Execution Engine** objectives (all met):

- Execute registered agents. ✅ (`ExecutionEngine.execute()`)
- Invoke external AI providers. ✅ (via each agent's CLI, per `docs/architecture/agent-integration.md`; see ADR-0004 for why CLI subprocess invocation was chosen over raw HTTP APIs for this phase)
- Manage execution lifecycle. ✅ (PENDING → RUNNING → AWAITING_APPROVAL / FAILED)
- Capture execution results. ✅ (`ExecutionResult`, recorded via `mark_awaiting_approval`)
- Support execution retries. ✅ (`RetryPolicy`, exponential backoff)
- Integrate with Persistence Layer. ✅ (all outcomes flow through `Orchestrator`, unchanged persistence path)
- Preserve backward compatibility. ✅ (no changes to `orchestrator/models.py`, `orchestrator/registry.py`, or `agent_registry.yaml`'s schema)

**Phase-07 – Model Provider Abstraction** objectives (all met):

- Invoke a model provider's HTTP API directly, as an alternative to CLI subprocess invocation. ✅ (`HttpAgentInvoker`, closing the ADR-0004 Phase-07 follow-up item)
- One adapter per provider, no generic branching client. ✅ (`AnthropicProvider`, `OpenAIProvider`, `GeminiProvider`, each behind the `ModelProvider` Protocol)
- Open/Closed provider extensibility. ✅ (`ProviderFactory` registration dict; ADR-0005 decision 8 — a new provider needs one new adapter + one new config entry, zero changes to `ExecutionEngine` or `HttpAgentInvoker`)
- Configurable enable/disable per provider. ✅ (`enabled: true|false` in `config/model_providers.yaml`, enforced by `ModelProviderRegistry`)
- Preserve backward compatibility. ✅ (no changes to `ExecutionEngine`, `Orchestrator`, `orchestrator/models.py`, `orchestrator/registry.py`, the `AgentInvoker` Protocol, or `agent_registry.yaml`'s schema)

**Phase-08 – Prompt Management System** objectives (all met):

- Versioned, validated prompt assets. ✅ (`PromptRegistry` loads/validates `prompts/prompt_registry.yaml`; each entry has `version`, a disk-verified `template_path`, and a typed `variables` list)
- Variable substitution with fail-loudly validation. ✅ (`StringTemplateRenderer`; `MissingRequiredVariableError` / `UnknownVariableError`)
- Fix for the previously-documented duplicate-YAML-key incident. ✅ (`DuplicatePromptKeyError`, raised at registry-load time instead of PyYAML silently keeping the last value)
- Integration with both invokers without touching `ExecutionEngine`. ✅ (ADR-0006 decision 6 — resolution happens inside `SubprocessAgentInvoker`/`HttpAgentInvoker`, immediately before invocation)
- Preserve backward compatibility. ✅ (`ExecutionEngine`, `Orchestrator`, `orchestrator/registry.py`, `agent_registry.yaml`'s schema, the `AgentInvoker` Protocol, and `ModelProviderRegistry` all unchanged; `AgentTask`'s two new fields are optional and additive, and all 202 pre-Phase-08 tests remain valid unmodified)

**Phase-09 – Tool Execution Framework** objectives (all met):

- Discrete, named, config-driven tools, independent of any agent's CLI/API session. ✅ (`orchestrator/tools/` -- `Tool` Protocol, `ToolRegistry` loading `config/tools.yaml`)
- Open/Closed tool extensibility. ✅ (`ToolFactory` registration dict; ADR-0007 decision 4 -- a new built-in tool needs one new implementation class + one new config entry, zero changes to `ToolExecutor` or `ToolRegistry`)
- Fail-loudly argument validation before any tool runs. ✅ (`ToolExecutor._validate_arguments()` -- `MissingRequiredArgumentError` / `UnknownArgumentError` / `InvalidArgumentTypeError`)
- Configurable enable/disable per tool. ✅ (`enabled: true|false` in `config/tools.yaml`, enforced by `ToolRegistry`)
- Minimal, safe built-in tools only -- no shell execution, no MCP integration. ✅ (`ReadFileTool`, `ListDirectoryTool`; both read-only, non-recursive, local-filesystem only)
- Preserve backward compatibility. ✅ (no changes to `AgentTask`, `Orchestrator`, `ExecutionEngine`, `SubprocessAgentInvoker`, `HttpAgentInvoker`, `orchestrator/registry.py`, `ModelProviderRegistry`, or `PromptManager`; see ADR-0007 decision 6)

---

# Milestones

| Milestone | Status |
|-----------|--------|
| Core Architecture | ✅ |
| Configuration | ✅ |
| Agent Registry | ✅ |
| Orchestrator | ✅ |
| Persistence | ✅ |
| Execution Engine | ✅ |
| Model Providers | ✅ |
| Prompt Management | ✅ |
| Tool Execution | ✅ |
| Memory | ✅ |
| Workflow Engine | ✅ |
| Security | ✅ |
| Observability | ✅ |
| Production Ready | ⏳ |

---

# Version History

| Version | Description |
|----------|-------------|
| v0.4.1 | Stable Phase-04 |
| v0.5.0 | Stable Phase-05 |
| v0.6.0 | Stable Phase-06 |
| v0.7.0 | Stable Phase-07 |
| v0.8.0 | Stable Phase-08 |
| v0.9.0 | Stable Phase-09 |
| v1.0.0 | Stable Phase-10 |
| v1.1.0 | Stable Phase-11 |
| v1.2.0 | Stable Phase-12 |
| v1.3.0 | Stable Phase-13 |

---

# Development Workflow

For every phase:

1. Create a feature branch.
2. Produce an implementation plan.
3. Review and approve the plan.
4. Implement the phase.
5. Run Ruff and Pytest.
6. Fix review findings.
7. Commit changes.
8. Push branch.
9. Create a version tag.
10. Update this roadmap.

---

# Notes

- One phase per branch.
- One version tag per completed phase.
- Documentation (ADR) before implementation.
- Maintain backward compatibility whenever possible.
- CI must remain green before merging.

---

Project: **AI Engineering Operating System (AEOS)**
Repository Status: **Active**
Current Version: **v1.3.0**