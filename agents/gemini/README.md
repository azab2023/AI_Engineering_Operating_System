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
- `config/permissions.yaml` — what this agent may read/write.
- `config/model-settings.yaml` — model/version, multimodal input limits.
- `config/prompts.yaml` — default prompts this agent should load.

## Known Constraints
- Must never auto-merge or auto-publish; human approval required (see
  `docs/governance/contribution-guidelines.md`).
- Config in this folder must never contain API keys directly — reference
  environment variables only.
