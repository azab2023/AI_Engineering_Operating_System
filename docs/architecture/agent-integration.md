# Agent Integration

Describes how each managed AI coding agent is expected to integrate with
AEOS once Phase-02+ implements the actual adapters. Phase-01 only defines
the contract and folder ownership below — no adapter code exists yet.

## 1. Common Contract (all agents)

Every agent folder under `agents/<agent-name>/` will eventually expose:

| Item | Purpose | Phase Introduced |
|---|---|---|
| `README.md` | What the agent is, how it's invoked, known limitations | Phase-01 |
| `config/` | Agent-specific settings (model, temperature, tool access, etc.) | Phase-02 |
| `config/permissions.yaml` | What the agent is allowed to touch in this repo | Phase-02 |
| `config/prompts.yaml` | Which files under `prompts/` this agent uses by default | Phase-03 |

No agent is permitted to read or write another agent's `config/` folder.
Shared behavior belongs in `configs/global/`.

## 2. Per-Agent Notes

### Claude Code (`agents/claude-code/`)
- Invoked via CLI/IDE integration; reads root `CLAUDE.md` for repo-wide
  behavior in addition to its own `agents/claude-code/README.md`.
- Best suited for: repo-aware refactors, multi-file changes, autonomous
  task execution with tool use.

### Aider (`agents/aider/`)
- CLI-native, git-first pair-programming agent.
- Best suited for: fast, local, commit-oriented iterative edits.

### OpenAI Codex (`agents/openai-codex/`)
- API/CLI-based code generation and review.
- Best suited for: targeted code generation, completions, review tasks.

### Gemini (`agents/gemini/`)
- Multimodal agent (code + documents + images).
- Best suited for: tasks that combine documentation/diagrams with code
  reasoning.

## 3. Routing (future — Phase-04)

Task-to-agent routing rules will live in `configs/global/routing.yaml`
(not yet created). Phase-01 intentionally leaves routing undefined.
