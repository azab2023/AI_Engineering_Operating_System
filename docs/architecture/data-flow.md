# Data Flow (Target Design)

This document describes how information is expected to move through AEOS
once later phases add implementation. Phase-01 ships no code — this is the
design contract implementers must follow in Phase-02+.

## 1. Inputs

- **Human request** — a task description from a developer/operator.
- **Repository state** — the current AEOS repo (docs, configs, prompts).
- **Agent capability declarations** — what each agent under `agents/` can do.

## 2. Flow (planned, Phase-04 orchestration)

```
Human request
     │
     ▼
[Orchestration Layer]  ── reads ──▶ configs/global/routing.yaml
     │
     ▼
Selected agent (claude-code | aider | openai-codex | gemini)
     │
     ├── reads its own agents/<agent>/config/
     ├── reads relevant prompts/ (system + template + workflow)
     └── reads shared configs/global/
     │
     ▼
Agent executes task against target codebase (outside AEOS repo)
     │
     ▼
Output: code changes / PR / report
     │
     ▼
[Human review & approval]  ◀── mandatory gate, no auto-merge
     │
     ▼
Logged to logs/ (git-ignored) + optionally summarized to docs/
```

## 3. Key Rule: Human-in-the-loop

No stage of this flow is permitted to skip human review before a change is
merged or an output is published externally. This applies uniformly across
all four agents.

## 4. State & Persistence

- Long-lived configuration → `configs/` (tracked in git).
- Agent-specific settings → `agents/<agent>/config/` (tracked in git,
  **no secrets**).
- Ephemeral run output → `logs/` (git-ignored).
- Design history → `docs/architecture/decision-records/` (tracked in git).
