# CLAUDE.md — Instructions for Claude Code

This file is read by Claude Code when operating inside the
`AI_Engineering_Operating_System` (AEOS) repository. It defines scope,
boundaries, and conventions Claude Code must follow.

---

## 1. Project Context

AEOS is an operating system for managing multiple AI coding agents
(Claude Code, Aider, OpenAI Codex, Gemini). Claude Code's role in this
repo is twofold:

1. **As a managed agent** — Claude Code's own configuration lives in
   `agents/claude-code/`.
2. **As the acting engineer** — When invoked to work on this repo, Claude
   Code follows the rules below regardless of which role it is filling.

## 2. Current Phase

We are in **Phase-01**. Scope is strictly limited to:

- Folder architecture
- Documentation (`README.md`, `docs/`)
- Empty/placeholder structure for `prompts/`, `agents/`, `configs/`
- This `CLAUDE.md` file, `.gitignore`

**Do not** write application code, scripts, or CI pipelines until a later
phase explicitly authorizes it. If asked to "implement" something while
Phase-01 is active, flag the phase mismatch before proceeding.

## 3. Repository Rules

- **Never commit secrets.** API keys, tokens, and credentials must never be
  written to any file in this repo, including `configs/` and `agents/*/config/`.
  Use environment variables and reference them by name only.
- **Docs before code.** Any new subsystem (orchestration, CI, scripts)
  needs a corresponding entry in `docs/architecture/` before or alongside
  implementation.
- **One ADR per architectural decision.** Significant decisions (agent
  routing logic, prompt versioning scheme, storage choices) get a new file
  in `docs/architecture/decision-records/` following the ADR-000N naming
  pattern.
- **Agent isolation.** Do not let one agent's folder under `agents/`
  reference or depend on another agent's config. Shared settings belong in
  `configs/global/`.
- **Prompts are versioned artifacts.** Treat files under `prompts/` as
  reviewed engineering assets — no inline "quick hack" prompts committed
  without going through `prompts/templates/` or `prompts/workflows/`
  conventions once populated in later phases.

## 4. Coding Conventions (for future phases)

To be defined in `docs/architecture/overview.md` once Phase-02 begins.
Placeholder principles already agreed:

- Config files: YAML preferred for human-edited config, JSON for
  machine-generated/consumed config.
- Scripts: language choice per-task, documented in `scripts/README.md`
  once created.
- All automation must be idempotent and safe to re-run.

## 5. Validation Expectations

Before marking any deliverable complete, Claude Code must:

1. Confirm the folder/file matches what's declared in `README.md`.
2. Confirm no application code was introduced if the active phase forbids it.
3. Produce or update a validation report summarizing what was created.

## 6. Escalation

If a request conflicts with the rules above (e.g. asks for secrets to be
committed, or asks to skip documentation), Claude Code should pause and
surface the conflict instead of proceeding silently.
