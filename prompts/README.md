# Prompt Library

Central, agent-agnostic prompt storage for AEOS. Prompts here are treated
as versioned engineering artifacts, not throwaway chat text.

## Structure

```
prompts/
├── system/       # Core system-level prompts (agent identity, guardrails)
├── templates/     # Reusable prompt templates with placeholders
└── workflows/      # Multi-step / multi-prompt workflow definitions
```

- **`system/`** — Prompts that define baseline behavior/guardrails shared
  across agents (e.g. "always require human approval before merge").
- **`templates/`** — Parameterized prompts meant to be filled in per task
  (e.g. a "generate ADR draft" template).
- **`workflows/`** — Ordered sequences of prompts representing a multi-step
  process (e.g. analyze → propose → review → implement).

## Status

Empty in Phase-01 by design. Population begins in Phase-03 once agent
configuration (Phase-02) establishes how each agent consumes these files.

## Conventions (to apply starting Phase-03)

- One prompt per file, `.md` format, kebab-case filenames.
- Each prompt file should open with a short YAML front-matter block
  (purpose, intended agent(s), last-reviewed date) once implemented.
- No agent-specific hacks in `system/` or `templates/` — those belong in
  `agents/<agent-name>/`.
