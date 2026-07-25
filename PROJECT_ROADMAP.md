# AI Engineering Operating System (AEOS)
# Project Roadmap

**Project Status:** Active Development

Current Version: **v0.8.0**

Current Branch: **phase-08**

Last Completed Phase: **Phase-08 – Prompt Management System**

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

---

# Planned Phases

| Phase | Status | Description |
|--------|--------|-------------|
| Phase-09 | ⏳ | Tool Execution Framework |
| Phase-10 | ⏳ | Memory Management |
| Phase-11 | ⏳ | Workflow Engine |
| Phase-12 | ⏳ | Security & Permissions |
| Phase-13 | ⏳ | Monitoring & Observability |
| Phase-14 | ⏳ | Plugin & Extension System |
| Phase-15 | ⏳ | Production Release (v1.0) |

---

# Current Focus

**Phase-08 has been implemented and verified** (new `orchestrator/prompts/`
package — `PromptDefinition`/`PromptVariable`/`RenderedPrompt` models,
`PromptRenderer` Protocol + `StringTemplateRenderer`, `PromptRegistry`
with duplicate-top-level-key detection, `PromptManager` Facade; two new
optional fields on `AgentTask` (`prompt_id`, `prompt_variables`);
`SubprocessAgentInvoker` and `HttpAgentInvoker` both resolve/render a
prompt when `task.prompt_id` is set, falling back to `task.description`
unchanged otherwise; `prompts/prompt_registry.yaml` rewritten with a
validated schema and 7 populated templates under `prompts/templates/`;
ADR-0006; 250 tests passing, Ruff check + format clean, up from 202 at
Phase-07 close). Phase-09 has not started.

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

**Phase-09 – Tool Execution Framework** (next, pending approval)

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
| Memory | ⏳ |
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
Current Version: **v0.8.0**