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
- `config/permissions.yaml` — what this agent may read/write.
- `config/model-settings.yaml` — model provider/version, edit format.
- `config/prompts.yaml` — default prompts this agent should load.

## Known Constraints
- Must never auto-merge or auto-publish; human approval required (see
  `docs/governance/contribution-guidelines.md`).
- Config in this folder must never contain API keys directly — reference
  environment variables only.
