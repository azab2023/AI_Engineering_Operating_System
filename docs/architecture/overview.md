# Architecture Overview

## 1. Purpose

AEOS provides a single, consistent repository structure that lets multiple
AI coding agents (Claude Code, Aider, OpenAI Codex, Gemini) operate against
shared conventions, without stepping on each other's configuration or
producing inconsistent outputs.

## 2. Design Principles

1. **Agent-agnostic core, agent-specific edges.** Prompts (`prompts/`) and
   shared configs (`configs/global/`) are agent-agnostic. Only
   `agents/<agent-name>/` holds agent-specific detail.
2. **Documentation as infrastructure.** `docs/` is not an afterthought —
   architecture decisions are recorded before implementation, not after.
3. **No hidden state.** Nothing an agent needs to operate should live
   outside this repository (no undocumented local files, no untracked
   environment assumptions beyond what `.env.example` / `docs/setup/`
   describe).
4. **Phased rollout.** Each phase has a hard scope boundary (see root
   `README.md` → Phase Roadmap) to keep the system reviewable and to avoid
   premature complexity.
5. **Human approval stays in the loop.** AEOS is designed to assist
   engineering work, not to auto-merge or auto-publish anything without a
   human review step (this mirrors the same governance principle used for
   any AI-generated content in this project's broader ecosystem).

## 3. Logical Layers (target end-state, beyond Phase-01)

```
 ┌─────────────────────────────────────────────────────────┐
 │                     Orchestration Layer                  │  Phase-04
 │   (task routing: which agent handles which task type)    │
 └───────────────┬───────────────────────────┬──────────────┘
                  │                           │
        ┌─────────▼─────────┐       ┌─────────▼─────────┐
        │   Prompt Library   │       │   Config Layer     │   Phase-01 (structure)
        │   (prompts/)       │       │   (configs/, agents)│  Phase-02/03 (content)
        └─────────┬─────────┘       └─────────┬─────────┘
                  │                           │
        ┌─────────▼───────────────────────────▼─────────┐
        │              Agent Adapters                    │   Phase-02+
        │  claude-code | aider | openai-codex | gemini    │
        └─────────────────┬────────────────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │     Observability / Logs / CI        │   Phase-05
        │        (logs/, .github/workflows/)   │
        └───────────────────────────────────────┘
```

Phase-01 delivers the folder skeleton and documentation for every layer
above; no orchestration, adapter, or CI logic is implemented yet.

## 4. Related Documents

- [`agent-integration.md`](agent-integration.md) — how each agent plugs in
- [`data-flow.md`](data-flow.md) — how information moves through the system
- [`decision-records/`](decision-records/) — Architecture Decision Records (ADRs)
