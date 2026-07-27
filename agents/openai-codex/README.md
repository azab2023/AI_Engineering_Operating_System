# Agent: OpenAI Codex

## Overview
OpenAI's code-focused agent/API, used for targeted code generation,
completion, and review tasks.

## Role in AEOS
- Best suited for scoped code generation and review, rather than broad
  autonomous repo-wide refactors.

## Folder Contents (Phase-01)
- `README.md` — this file.
- `config/` — reserved, empty until Phase-02.

## Planned Configuration (Phase-02+)
- `config/model-settings.yaml` — model/version, token limits.
- `config/prompts.yaml` — default prompts this agent should load.

## Permissions (Phase-12)
This agent's read/write permissions are no longer planned as a
per-agent file in this folder. They are implemented centrally, as of
Phase-12, in the project-root `config/permissions.yaml`'s
`agent_permissions.codex` entry (matching the `codex` name used in
`config/agents.yaml` / `config/agent_registry.yaml`), enforced by
`orchestrator.security.authorizer.ToolAuthorizer` via `ToolExecutor`.
See `docs/architecture/decision-records/ADR-0010-security-permissions.md`.

## Known Constraints
- Must never auto-merge or auto-publish; human approval required (see
  `docs/governance/contribution-guidelines.md`).
- Config in this folder must never contain API keys directly — reference
  environment variables only.
