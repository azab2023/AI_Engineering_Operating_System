# Agent: Aider

## Overview
Open-source, git-native CLI pair-programming agent. Works directly against
a local git repository, making focused, commit-oriented edits.

## Role in AEOS
- Best suited for fast, local, iterative edits where tight git integration
  matters (auto-commit per change, easy diff review).

## Folder Contents (Phase-01)
- `README.md` — this file.
- `config/` — reserved, empty until Phase-02.

## Planned Configuration (Phase-02+)
- `config/model-settings.yaml` — model provider/version, edit format.
- `config/prompts.yaml` — default prompts this agent should load.

## Permissions (Phase-12)
This agent's read/write permissions are no longer planned as a
per-agent file in this folder. They are implemented centrally, as of
Phase-12, in the project-root `config/permissions.yaml`'s
`agent_permissions.aider` entry, enforced by
`orchestrator.security.authorizer.ToolAuthorizer` via `ToolExecutor`.
See `docs/architecture/decision-records/ADR-0010-security-permissions.md`.

## Known Constraints
- Must never auto-merge or auto-publish; human approval required (see
  `docs/governance/contribution-guidelines.md`).
- Config in this folder must never contain API keys directly — reference
  environment variables only.
