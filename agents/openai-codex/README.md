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
- `config/permissions.yaml` — what this agent may read/write.
- `config/model-settings.yaml` — model/version, token limits.
- `config/prompts.yaml` — default prompts this agent should load.

## Known Constraints
- Must never auto-merge or auto-publish; human approval required (see
  `docs/governance/contribution-guidelines.md`).
- Config in this folder must never contain API keys directly — reference
  environment variables only.
