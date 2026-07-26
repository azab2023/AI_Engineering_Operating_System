# AI Engineering Operating System (AEOS)
# Project Roadmap

**Project Status:** Active Development

Current Version: **v1.0.0**

Current Branch: **phase-10**

Last Completed Phase: **Phase-10 – Memory Management**

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

---

# Planned Phases

| Phase | Status | Description |
|--------|--------|-------------|
| Phase-11 | ⏳ | Workflow Engine |
| Phase-12 | ⏳ | Security & Permissions |
| Phase-13 | ⏳ | Monitoring & Observability |
| Phase-14 | ⏳ | Plugin & Extension System |
| Phase-15 | ⏳ | Production Release (v1.0) |

---

# Current Focus

**Phase-10 has been implemented and verified** (new `orchestrator/memory/`
package -- `MemoryEntry` model, `MemoryStore` Protocol, `InMemoryStore`
(Working Memory) and `SQLiteMemoryStore` (Persistent Memory, reusing
`orchestrator/persistence/db.py`'s connection setup and adding its own
additive `memory_entries` table via `orchestrator/memory/schema.py`),
and `MemoryManager` Facade (`remember`/`recall`/`forget`/`list`,
upsert semantics on top of the store's `add`/`update`); three new
exceptions under a new `MemoryManagementError` base in
`orchestrator/exceptions.py`; ADR-0008; this phase is deliberately
self-contained -- `AgentTask`, `Orchestrator`, `ExecutionEngine`, both
`AgentInvoker` implementations, `AgentRegistry`, `ModelProviderRegistry`,
`PromptManager`, and `ToolExecutor` are all unchanged, and
`MemoryManager` has no caller yet (see ADR-0008 decision 7; expected to
be consumed by the future Phase-11 Workflow Engine, alongside
`ToolExecutor`); no semantic memory, embeddings, vector databases, or
similarity search were implemented (out of approved scope, see
ADR-0008); 338 tests passing, Ruff check + format clean, up from 303 at
Phase-09 close. Phase-11 has not started.

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
| Security | ⏳ |
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
Current Version: **v1.0.0**