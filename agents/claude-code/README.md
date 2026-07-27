# Agent: Claude Code

## Overview
Anthropic's agentic coding tool. Operates via CLI/IDE integration and is
capable of autonomous, multi-file, repo-aware coding tasks with tool use.

## Role in AEOS
- Reads root `CLAUDE.md` for repo-wide behavior.
- Best suited for larger refactors, repo-aware autonomous execution, and
  tasks requiring tool use (file edits, running commands, tests).

## Folder Contents (Phase-01)
- `README.md` — this file.
- `config/` — reserved, empty until Phase-02.

## Planned Configuration (Phase-02+)
- `config/model-settings.yaml` — model/version, context limits.
- `config/prompts.yaml` — default prompts this agent should load from
  `prompts/system/` and `prompts/workflows/`.

## Permissions (Phase-12)
This agent's read/write permissions are no longer planned as a
per-agent file in this folder. They are implemented centrally, as of
Phase-12, in the project-root `config/permissions.yaml`'s
`agent_permissions.claude_code` entry, enforced by
`orchestrator.security.authorizer.ToolAuthorizer` via `ToolExecutor`.
See `docs/architecture/decision-records/ADR-0010-security-permissions.md`.

## Known Constraints
- Must never auto-merge or auto-publish; human approval required (see
  `docs/governance/contribution-guidelines.md`).
- Must not write application code while the repo is in a phase that
  forbids it (see root `CLAUDE.md`).
