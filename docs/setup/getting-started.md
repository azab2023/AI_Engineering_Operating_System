# Getting Started

## 1. Prerequisites

- Git installed and configured.
- A GitHub account/organization to host this repository.
- Access credentials for whichever agents you intend to use (Claude Code,
  Aider, OpenAI Codex, Gemini) — **do not store these in the repo**; see
  Section 3.

## 2. Clone / Initialize

```bash
cd D:\
git init AI_Engineering_Operating_System
cd AI_Engineering_Operating_System
git add .
git commit -m "Phase-01: initial AEOS architecture"
```

Then create a GitHub repository and push:

```bash
git remote add origin <your-github-repo-url>
git branch -M main
git push -u origin main
```

## 3. Environment & Secrets

Phase-01 does not ship an `.env.example` file yet (no application code
requires environment variables at this stage). When Phase-02 introduces
agent configuration that needs API keys, an `.env.example` will be added
to the repo root and referenced here. Actual secrets must always be kept
out of git via `.gitignore` (already configured).

## 4. Repository Orientation

- Start with the root [`README.md`](../../README.md) for the full map.
- Read [`../architecture/overview.md`](../architecture/overview.md) to
  understand the design.
- If you're Claude Code specifically, also read the root
  [`CLAUDE.md`](../../CLAUDE.md).
- Review [`../governance/contribution-guidelines.md`](../governance/contribution-guidelines.md)
  before making any change, human or agent-originated.

## 5. What You Can Do in Phase-01

- Read and review the documentation and structure.
- Propose changes to the architecture via a new ADR in
  `docs/architecture/decision-records/`.
- Prepare (but not yet commit) agent configuration drafts for Phase-02.

## 6. What You Cannot Do Yet

- Add application/automation code to `scripts/`.
- Add CI/CD pipelines to `.github/workflows/`.
- Populate `agents/*/config/` with functioning configuration (structure
  only, per Phase-01 scope).
