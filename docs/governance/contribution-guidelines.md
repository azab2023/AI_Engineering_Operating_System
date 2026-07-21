# Contribution Guidelines

These rules apply equally to human contributors and AI coding agents
(Claude Code, Aider, OpenAI Codex, Gemini) operating in this repository.

## 1. Human-in-the-loop is mandatory

No change produced by an AI agent may be merged to `main` or published
externally without explicit human review and approval. This is a hard
rule, not a default that can be silently overridden by agent configuration.

## 2. Documentation-first changes

Any structural or architectural change must:

1. Be described in a new or updated file under `docs/architecture/`.
2. Include a new ADR in `docs/architecture/decision-records/` if it changes
   a prior decision or introduces a new significant one.
3. Only then be reflected in the actual folder/file structure.

## 3. Agent boundaries

- An agent may only modify files inside its own `agents/<agent-name>/`
  folder, plus files explicitly relevant to the task it was asked to do.
- Cross-agent changes (e.g. modifying `configs/global/`) require the
  change to be documented and, in Phase-02+, explicitly permitted via that
  agent's `config/permissions.yaml`.
- No agent may commit secrets, credentials, or tokens under any
  circumstance (enforced structurally via `.gitignore`, and by convention
  here).

## 4. Phase discipline

Work must stay within the scope of the currently active phase (see root
`README.md` → Phase Roadmap). If a request would require work outside the
current phase's scope, it should be flagged and deferred rather than
silently expanded.

## 5. Commit & review conventions (to be extended in later phases)

- Commit messages should reference the phase and area, e.g.
  `Phase-02(agents/claude-code): add permissions schema`.
- Every pull request should link back to the relevant `docs/` entry or ADR.

## 6. Reporting issues

Until a formal issue template is added (future phase), open issues with a
clear title, the affected folder, and whether the report concerns
documentation, structure, or (in later phases) functional behavior.
