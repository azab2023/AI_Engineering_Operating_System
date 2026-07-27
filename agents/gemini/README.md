# Agent: Gemini

## Overview
Google's multimodal agent, capable of combining code reasoning with
documents, images, and diagrams.

## Role in AEOS
- Best suited for tasks that blend documentation/diagram understanding
  with code changes (e.g. implementing a feature from a design doc/image).

## Folder Contents (Phase-01)
- `README.md` — this file.
- `config/` — reserved, empty until Phase-02.

## Planned Configuration (Phase-02+)
- `config/model-settings.yaml` — model/version, multimodal input limits.
- `config/prompts.yaml` — default prompts this agent should load.

## Permissions (Phase-12)
This agent's read/write permissions are no longer planned as a
per-agent file in this folder. They are implemented centrally, as of
Phase-12, in the project-root `config/permissions.yaml`'s
`agent_permissions.gemini` entry, enforced by
`orchestrator.security.authorizer.ToolAuthorizer` via `ToolExecutor`.
See `docs/architecture/decision-records/ADR-0010-security-permissions.md`.

## Known Constraints
- Must never auto-merge or auto-publish; human approval required (see
  `docs/governance/contribution-guidelines.md`).
- Config in this folder must never contain API keys directly — reference
  environment variables only.
