# AI Engineering Operating System (AEOS)

**Status:** Phase-01 — Foundation & Architecture (no application code yet)
**Owner:** Lead Software Architect
**Repository path (local):** `D:\AI_Engineering_Operating_System`

---

## 1. What is AEOS?

AEOS is a professional engineering operating system that orchestrates and
manages multiple AI coding agents from a single, consistent, auditable
repository structure. Instead of every agent having its own ad-hoc config
scattered across a workstation, AEOS centralizes:

- Agent configuration (per-agent, versioned, environment-aware)
- Prompt libraries (system prompts, reusable templates, workflow prompts)
- Architecture documentation and decision history (ADRs)
- Governance rules for how agents are allowed to operate in this repo

### Agents managed by AEOS (Phase-01 scope)

| Agent | Vendor | Primary Use Case | Config Location |
|---|---|---|---|
| Claude Code | Anthropic | Autonomous coding, refactors, repo-aware tasks | `agents/claude-code/` |
| Aider | Open-source | Local/CLI pair-programming, git-native edits | `agents/aider/` |
| OpenAI Codex | OpenAI | Code generation, completion, review | `agents/openai-codex/` |
| Gemini | Google | Multimodal reasoning, code + docs | `agents/gemini/` |

---

## 2. Repository Layout

```
AI_Engineering_Operating_System/
├── README.md                     # This file — system overview
├── CLAUDE.md                     # Instructions specifically for Claude Code
├── .gitignore                    # Repo-wide ignore rules
│
├── docs/                         # All documentation lives here
│   ├── architecture/
│   │   ├── overview.md               # High-level system architecture
│   │   ├── agent-integration.md      # How each agent plugs into AEOS
│   │   ├── data-flow.md              # How prompts/configs/state move
│   │   └── decision-records/
│   │       └── ADR-0001-initial-architecture.md
│   ├── setup/
│   │   └── getting-started.md        # Onboarding instructions
│   └── governance/
│       └── contribution-guidelines.md# Rules of engagement for humans + agents
│
├── agents/                       # One folder per AI coding agent
│   ├── claude-code/
│   │   ├── README.md
│   │   └── config/                   # Agent-specific config (Phase-02+)
│   ├── aider/
│   │   ├── README.md
│   │   └── config/
│   ├── openai-codex/
│   │   ├── README.md
│   │   └── config/
│   └── gemini/
│       ├── README.md
│       └── config/
│
├── prompts/                      # Central prompt library (agent-agnostic)
│   ├── README.md
│   ├── system/                       # Core/system-level prompts
│   ├── templates/                    # Reusable prompt templates
│   └── workflows/                    # Multi-step workflow prompts
│
├── configs/                      # Cross-agent, environment-level configs
│   ├── global/                       # Shared defaults for all agents
│   └── environments/                 # dev / staging / prod overrides
│
├── scripts/                      # Automation scripts (empty — Phase-02+)
├── tests/                        # Test suite (empty — Phase-02+)
├── logs/                         # Runtime/agent logs (git-ignored)
└── .github/
    └── workflows/                    # CI/CD pipelines (empty — Phase-02+)
```

### Why each top-level folder exists

- **`docs/`** — Single source of truth for architecture, onboarding, and
  governance. Keeps design decisions out of code comments and chat history.
- **`agents/`** — Isolates each AI coding agent's identity and configuration
  so agents never share or leak settings. Each agent folder is self-contained
  and independently versionable.
- **`prompts/`** — Prompts are treated as first-class engineering artifacts
  (versioned, reviewed, reused) rather than throwaway chat text. Kept
  separate from `agents/` because prompts are agent-agnostic and can be
  reused across Claude Code, Aider, Codex, and Gemini.
- **`configs/`** — Settings that are not agent-specific (e.g. shared coding
  standards, environment variables, model routing rules) live here to avoid
  duplication across the four agent folders.
- **`scripts/`** — Reserved for future automation (setup scripts, CLI
  wrappers, agent orchestration). Intentionally empty in Phase-01 per scope.
- **`tests/`** — Reserved for future test suite validating configs/prompts
  once application code is introduced.
- **`logs/`** — Runtime output destination for agents; excluded from git via
  `.gitignore` to avoid committing sensitive/large log data.
- **`.github/workflows/`** — Reserved for CI/CD (lint prompts, validate
  configs, secret scanning) once automation is implemented.

---

## 3. Phase Roadmap

| Phase | Scope | Status |
|---|---|---|
| **Phase-01** | Folder architecture, README, CLAUDE.md, docs, empty prompts/agents structure | ✅ This delivery |
| Phase-02 | Agent configuration schemas (YAML/JSON) + validation scripts | Planned |
| Phase-03 | Prompt library population + prompt versioning system | Planned |
| Phase-04 | Orchestration layer (task routing across agents) | Planned |
| Phase-05 | CI/CD, testing, observability/logging pipeline | Planned |

---

## 4. Getting Started

See [`docs/setup/getting-started.md`](docs/setup/getting-started.md).

## 5. Architecture

See [`docs/architecture/overview.md`](docs/architecture/overview.md).

## 6. Governance

See [`docs/governance/contribution-guidelines.md`](docs/governance/contribution-guidelines.md).

## 7. License

To be determined by the project owner before public GitHub release.
