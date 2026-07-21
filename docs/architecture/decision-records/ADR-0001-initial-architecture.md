# ADR-0001: Initial Repository Architecture for AEOS

- **Status:** Accepted
- **Date:** Phase-01
- **Deciders:** Lead Software Architect

## Context

AEOS needs to manage four distinct AI coding agents (Claude Code, Aider,
OpenAI Codex, Gemini) from one repository without their configurations,
prompts, or state colliding. A structure was needed that scales to future
orchestration and CI/CD phases without requiring a rewrite.

## Decision

Adopt a four-pillar top-level structure:

1. `docs/` — documentation and architecture decisions, source of truth.
2. `agents/` — one isolated folder per agent, identical internal shape.
3. `prompts/` — centralized, agent-agnostic prompt library.
4. `configs/` — shared/global and environment-level configuration,
   separate from any single agent.

Supporting folders (`scripts/`, `tests/`, `logs/`, `.github/workflows/`)
are pre-created but intentionally empty in Phase-01 to reserve their place
in the architecture without introducing code before it's authorized.

## Alternatives Considered

- **Single flat `config/` folder for all agents combined.** Rejected —
  risks config leakage between agents and makes permissioning harder to
  reason about.
- **One repo per agent.** Rejected — defeats the purpose of a unified
  operating system; would require a separate orchestration repo anyway.
- **Prompts stored inside each agent folder.** Rejected — most prompts are
  reusable across agents; duplicating them per-agent would create drift.

## Consequences

- **Positive:** Clear ownership boundaries; easy to onboard a fifth agent
  later by copying the `agents/<name>/` shape; documentation-first culture
  is enforced structurally.
- **Negative:** Slightly more folders to navigate up front compared to a
  flat structure; mitigated by the folder-purpose table in the root
  `README.md`.

## Follow-up

- Phase-02 ADR needed for agent config schema format (YAML vs JSON).
- Phase-04 ADR needed for orchestration/routing design.
