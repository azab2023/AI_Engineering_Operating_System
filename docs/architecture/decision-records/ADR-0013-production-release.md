# ADR-0013: Production Release Packaging & CLI Entry Point (Phase-15)

- **Status:** Accepted
- **Date:** Phase-15
- **Deciders:** Lead AI Systems Architect (project owner)

## Context

`PROJECT_ROADMAP.md` listed Phase-15 only as "Production Release (v1.0)"
with no objectives section and no prior deferral pointing at a concrete
scope — the same situation ADR-0011 (Phase-13) and ADR-0012 (Phase-14)
each documented. Repository analysis (`CLAUDE.md`,
`docs/architecture/overview.md`, `docs/setup/getting-started.md`) found
no further detail, and the repository had no `LICENSE`, no
`CHANGELOG.md`, no `[project.scripts]` entry, and no CLI module. The
scope below was proposed and explicitly approved by the project owner
before any code was written.

**In scope:**
- ADR-0013 itself (this document).
- `CHANGELOG.md` summarizing Phase-01 through Phase-15.
- `LICENSE` (MIT).
- A minimal `aeos` CLI entry point (`orchestrator/cli.py`,
  `orchestrator.cli:main`) exposing only existing functionality:
  version display, command listing/help, and loading the existing
  `AgentRegistry`/`Orchestrator` facades.
- `pyproject.toml` version bump (`1.4.0` → `1.5.0`) and
  `[project.scripts]` registration.
- `PROJECT_ROADMAP.md` updated to mark Phase-15 complete.

**Explicitly out of scope** (deferred, not designed against here): any
new orchestration, execution, workflow, provider, tool, or plugin
logic; a Docker/container image; PyPI publication; CI/CD release
automation (tagging, artifact building); and any change to
`orchestrator/plugins/models.py`'s `CURRENT_AEOS_VERSION` constant,
which remains `"1.4.0"` — see Follow-up.

This phase introduces **no new runtime capability**. Every command the
CLI exposes is a thin pass-through to a facade that already exists
(`AgentRegistry`, `Orchestrator`), consistent with every prior phase's
"reuse, don't redesign" rule.

## Decision

### 1. `orchestrator/cli.py`: a single, dependency-free module using stdlib `argparse`

```
orchestrator/cli.py
```

One file, not a package — the CLI has no state, no lifecycle, and no
sub-components to separate, unlike `orchestrator/plugins/` or
`orchestrator/observability/`. It exposes:

- `main(argv: list[str] | None = None) -> int` — the console-script
  entry point (`orchestrator.cli:main`), returning a process exit code
  instead of calling `sys.exit()` directly, so it stays testable as a
  plain function.
- `get_version() -> str` — reads the installed package version via
  `importlib.metadata.version("aeos")`, falling back to a hard-coded
  string only if the package metadata is unavailable (e.g. running
  from a source checkout without `pip install -e .`). This keeps
  `pyproject.toml`'s `[project].version` the single source of truth
  instead of duplicating it in `orchestrator/__init__.py`'s unrelated
  `__version__ = "0.1.1"` (a Phase-04-era constant this ADR does not
  touch — see Follow-up).

Three subcommands, matching the roadmap's "display version / display
available commands / show help / optionally load the existing
orchestrator" requirement exactly, no more:

| Command | Behavior |
|---|---|
| `aeos version` (also `aeos --version`) | Prints `get_version()`. |
| `aeos list-agents` | Constructs `AgentRegistry()` (Phase-04 default config path) and `Orchestrator(registry)`, then prints each agent's name/status/priority. This is the "optionally load the existing orchestrator" requirement — it proves the facades wire up cleanly without adding any new orchestration behavior. |
| `aeos help` (also no args, also `-h`/`--help`) | Prints `argparse`'s generated help/command list. |

`list-agents` catches `AgentRegistryError` (Phase-04) at the CLI
boundary and prints a one-line message to stderr with exit code `1`
instead of a raw traceback — the same "fail loudly but not with a
stack trace at a user-facing boundary" pattern already used nowhere
else in the codebase (no prior phase had a user-facing entry point),
but consistent with every prior phase's own internal fail-loudly
exceptions.

### 2. `[project.scripts]` in `pyproject.toml`

```toml
[project.scripts]
aeos = "orchestrator.cli:main"
```

Standard `setuptools` console-script mechanism — no new build
tooling, no change to `[build-system]`.

### 3. `LICENSE` (MIT) and `CHANGELOG.md`

Both are plain static files, not code — no architectural weight beyond
"they exist and are accurate." `CHANGELOG.md` is a human-readable
restatement of the `PROJECT_ROADMAP.md` "Completed Phases" table
(Phase-01 → Phase-15), in [Keep a Changelog](https://keepachangelog.com/)-style
sections, generated once and not automated (no release-automation
tooling was in scope).

## Alternatives Considered

### Alternative 1: `[project.scripts]` pointing at a `click`/`typer`-based CLI

Description: use a third-party CLI framework for nicer help output and
subcommand ergonomics.

Advantages: less boilerplate for larger CLIs; richer help formatting.

Disadvantages: adds a new runtime dependency for three trivial
commands — directly against `requirements.txt`'s documented "kept
minimal" constraint (ADR-0003 decision 8) and against this phase's
explicit "no new runtime capabilities" scope. Rejected.

### Alternative 2: Docs-only release (no CLI)

Description: ship only `LICENSE`, `CHANGELOG.md`, and the version bump;
treat "Production Release" as a documentation/versioning milestone
with no code changes.

Advantages: smallest possible diff; zero risk of touching runtime
behavior.

Disadvantages: the roadmap phrase "Production Release" and the
project owner's explicit approval both call for a minimal CLI entry
point as the concrete, user-facing deliverable of this phase. Rejected
in favor of the approved scope above.

### Alternative 3: CLI in a new top-level package (`cli/` at repo root, sibling to `orchestrator/`)

Description: mirror the `agents/`, `prompts/`, `templates/` top-level
layout instead of nesting inside `orchestrator/`.

Advantages: visually separates "entry point" from "library code."

Disadvantages: every prior phase's Python code lives under
`orchestrator/`; `[project.scripts]` and `[tool.setuptools.packages.find]`
already scope to `orchestrator`/`orchestrator.*` only, so a top-level
`cli/` package would need a build-system change out of this phase's
scope. Rejected.

## Consequences

### Positive

- AEOS is now installable with a working `aeos` console command
  (`pip install -e .` then `aeos version` / `aeos list-agents` /
  `aeos help`), closing the "Production Ready" row in
  `PROJECT_ROADMAP.md`'s Milestones table.
- Zero new runtime dependencies; zero changes to any completed phase's
  public API, module, or config schema.
- `get_version()` reading from package metadata means future version
  bumps only require editing `pyproject.toml`.

### Negative

- `orchestrator/__init__.py`'s `__version__` and
  `orchestrator/plugins/models.py`'s `CURRENT_AEOS_VERSION` were
  initially left unsynchronized with `pyproject.toml`'s `1.5.0` (see
  original Follow-up below); a same-phase follow-on pass subsequently
  synchronized both, along with `config/aeos.yaml`'s `system.version`,
  to `1.5.0`. This was a pure value substitution — `CURRENT_AEOS_VERSION`
  was already documented (see its docstring) as "bumped alongside
  `pyproject.toml`'s version field" each phase, and every
  `min_aeos_version`/`max_aeos_version` bound in `config/plugins.yaml`
  is `<= 1.4.0` with no upper bound, so Phase-14's plugin
  version-compatibility validation logic and behavior are unchanged.
- The CLI has no test coverage for the actual `console_scripts` shim
  (i.e., no test installs the package and shells out to `aeos`); tests
  cover `main()`/`get_version()`/`_list_agents()` as plain Python
  functions instead, which is standard practice for `argparse`-based
  CLIs but does not exercise `setuptools`' entry-point machinery
  itself.

## Implementation Notes

- New file: `orchestrator/cli.py`.
- New file: `tests/test_cli.py`.
- `pyproject.toml`: version bump + `[project.scripts]` section added.
- No changes to any file under `orchestrator/` other than the new
  `cli.py`.

## Follow-up

- ~~A future phase should reconcile `orchestrator/__init__.py`'s
  `__version__` and `orchestrator/plugins/models.py`'s
  `CURRENT_AEOS_VERSION` with `pyproject.toml`'s version~~ — **Resolved**
  within Phase-15 by a same-phase version-synchronization pass:
  `orchestrator/__init__.py.__version__`,
  `orchestrator/plugins/models.py.CURRENT_AEOS_VERSION`, and
  `config/aeos.yaml`'s `system.version` were all updated to `"1.5.0"`.
  All three still read from independent hardcoded constants rather than
  a single source (e.g. `importlib.metadata.version("aeos")`, as
  `orchestrator/cli.py.get_version()` does) — that structural
  consolidation remains a genuine future-phase candidate, but was out
  of scope for a "version string only" synchronization pass.
- No CI job currently runs `pip install -e .` and invokes `aeos`
  end-to-end; `.github/workflows/ci.yml` was intentionally left
  unmodified per this phase's scope.

## Related Components

`orchestrator/cli.py` (new), `orchestrator/registry.py` (`AgentRegistry`,
reused read-only), `orchestrator/core.py` (`Orchestrator`, reused
read-only), `orchestrator/exceptions.py` (`AgentRegistryError`, caught
at the CLI boundary), `pyproject.toml`, `PROJECT_ROADMAP.md`,
`CHANGELOG.md`, `LICENSE`.

## Date

Phase-15
