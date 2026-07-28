# Changelog

All notable changes to AEOS (AI Engineering Operating System) are
documented in this file, phase by phase. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
`PROJECT_ROADMAP.md` remains the authoritative source of truth for
phase status and objectives; this file is a human-readable restatement
of its "Completed Phases" table for release purposes.

## [1.5.0] - Phase-15 - Production Release

### Added
- `orchestrator/cli.py`: minimal `aeos` CLI entry point (`version`,
  `list-agents`, `help`), exposing existing functionality only — no new
  orchestration logic. See ADR-0013.
- `[project.scripts]` console-script registration (`aeos =
  orchestrator.cli:main`) in `pyproject.toml`.
- `LICENSE` (MIT).
- `CHANGELOG.md` (this file).
- ADR-0013: Production Release Packaging & CLI Entry Point.

### Changed
- Version bumped `1.4.0` → `1.5.0`.

## [1.4.0] - Phase-14 - Plugin & Extension System
- New `orchestrator/plugins/` package: `PluginMetadata`, `PluginRecord`,
  `PluginExtensionType`, `PluginLifecycleState` models; `PluginRegistry`
  loading `config/plugins.yaml`; `PluginManager` lifecycle facade
  (load → validate → initialize → unload); AEOS version-compatibility
  validation. See ADR-0012.

## [1.3.0] - Phase-13 - Monitoring & Observability
- `ObservabilityEvent` / `MetricPoint` / `ObservabilityConfig` models;
  `InMemoryRecorder`; `ObservabilityRegistry`; `ObservabilityManager`
  facade; Observer-pattern integration across `Orchestrator`,
  `ExecutionEngine`, `ToolExecutor`, and `WorkflowEngine`. See
  ADR-0011.

## [1.2.0] - Phase-12 - Security & Permissions
- `PathSandboxPolicy`, per-agent `AgentPermission`
  (`config/permissions.yaml`), and a centralized `ToolAuthorizer`;
  `agent_name`-aware `ToolExecutor` / `WorkflowStep`. See ADR-0010.

## [1.1.0] - Phase-11 - Workflow Engine
- `orchestrator/workflow/` package: `WorkflowRegistry`
  (`config/workflows.yaml`), `WorkflowRunRepository`, and
  `WorkflowEngine` facade composing the Orchestrator/ExecutionEngine
  and ToolExecutor into named, linear, human-approved step sequences.
  See ADR-0009.

## [1.0.0] - Phase-10 - Memory Management
- `MemoryStore` Protocol with `InMemoryStore` / `SQLiteMemoryStore`
  implementations; `MemoryManager` facade
  (`remember`/`recall`/`forget`/`list`); `MemoryEntry` model. See
  ADR-0008.

## [0.9.0] - Phase-09 - Tool Execution Framework
- `Tool` Protocol; `ToolRegistry` (`config/tools.yaml`); `ToolFactory`;
  `ToolExecutor` with fail-loudly argument validation; built-in
  `ReadFileTool` / `ListDirectoryTool`. See ADR-0007.

## [0.8.0] - Phase-08 - Prompt Management System
- `PromptRegistry` (`prompts/prompt_registry.yaml`); `PromptManager`;
  `StringTemplateRenderer`; `AgentTask.prompt_id` integration in both
  invokers. See ADR-0006.

## [0.7.0] - Phase-07 - Model Provider Abstraction
- `ModelProvider` Protocol; `AnthropicProvider` / `OpenAIProvider` /
  `GeminiProvider` adapters; `ModelProviderRegistry`
  (`config/model_providers.yaml`); `HttpAgentInvoker` as a direct-HTTP
  alternative to CLI subprocess invocation. See ADR-0005.

## [0.6.0] - Phase-06 - Agent Execution Engine
- `ExecutionEngine`; `SubprocessAgentInvoker`; `RetryPolicy` with
  exponential backoff; `ExecutionResult` model. See ADR-0004.

## [0.5.0] - Phase-05 - Persistence Layer
- `ExecutionRepository` Protocol with `InMemoryExecutionRepository` /
  `SqliteExecutionRepository`; SQLite schema; GitHub Actions CI
  (Ruff + Pytest). See ADR-0003.

## [0.4.1] - Phase-04 - Agent Orchestration Layer
- `orchestrator/` package foundation: `Agent` / `AgentTask` /
  `AgentExecution` models; `AgentRegistry`
  (`config/agent_registry.yaml`); `Orchestrator` selection/routing/state
  tracking. See ADR-0002.

## [0.3.x] - Phase-03 - Excel Template & Data Schema

## [0.2.x] - Phase-02 - Configuration System

## [0.1.x] - Phase-01 - Project Architecture
- Initial repository structure. See ADR-0001.
