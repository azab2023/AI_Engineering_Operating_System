# ADR-0002: Agent Orchestration Layer (Phase-04)

- **Status:** Accepted (amended by Phase-04 Patch Release — see Amendment
  section below)
- **Date:** Phase-04
- **Deciders:** Lead AI Systems Architect

## Context

ADR-0001 flagged that a Phase-04 ADR would be needed for orchestration and
routing design. This ADR is that follow-up.

At the time this work began, the repository's own documentation declared
Phase-01 as active, with Phase-02 (agent config schemas + validation) and
Phase-03 (prompt library population) still marked as Planned in the
roadmap. Several artifacts those phases would normally produce did not
exist: per-agent `permissions.yaml` files, populated `prompts/templates/`
content, schema validation for `config/*.yaml`, and the `configs/global/
routing.yaml` referenced by `docs/architecture/data-flow.md`.

The project owner explicitly authorized proceeding directly to Phase-04
on the `phase-04` branch, with instruction to add only the minimal
unblockers needed rather than deliver full Phase-02/03 scope. This ADR
documents that decision and the resulting design choices, per the
"docs before code" principle in `docs/architecture/overview.md`.

## Decision

### 1. Proceed to Phase-04 with minimal unblockers, not full Phase-02/03

Phase-04 (Agent Orchestration) is implemented now. It does not depend on
`permissions.yaml`, populated prompt templates, or a general config
validation framework — those remain open Phase-02/Phase-03 work. Where
Phase-04 needed something those phases would have provided (a structured,
validated agent registry), it was built as a self-contained addition
scoped strictly to orchestration (see decision 2).

### 2. New `config/agent_registry.yaml`, existing `agents.yaml` / `models.yaml` untouched

`config/agents.yaml` (role/priority) and `config/models.yaml` (provider/
purpose) predate this phase and do not carry the fields orchestration
requires (`capabilities`, `supported_tasks`, `config_reference`,
`status`). Extending either file's schema in place would be an
undocumented breaking change to files other phases or agents may already
depend on. Instead, `config/agent_registry.yaml` was added as the single
canonical source for orchestration, using the same agent identifiers
(`claude_code`, `codex`, `aider`, `gemini`) so the three files stay
conceptually aligned without one duplicating another's authority.

### 3. Location: `config/`, not `configs/`

The repository has two top-level configuration locations —
`config/` (existing `aeos.yaml`, `agents.yaml`, `models.yaml`) and
`configs/global/` + `configs/environments/` (empty, referenced by
`docs/architecture/overview.md` as the intended location for shared
settings). This inconsistency was flagged in the prior architecture
assessment and is **not resolved by this ADR** — `agent_registry.yaml`
was placed in `config/` purely for consistency with the other agent
metadata files it complements. Resolving `config/` vs `configs/` is
left as explicit follow-up (see below).

### 4. Deterministic, rule-based agent selection (no LLM-based routing)

An agent is eligible for a task if it is `active`, supports the task's
`task_type`, and has every capability the task requires. The first
eligible agent (registry order) is selected. This matches
`docs/architecture/data-flow.md`'s description of routing as a
deterministic layer, and avoids introducing an LLM call (with its cost,
latency, and non-determinism) into what is currently a foundational,
easily-testable decision path. Priority/scoring-based selection among
multiple eligible agents is a natural future extension, not implemented
here to avoid speculative complexity.

### 5. No execution backend in this phase

`Orchestrator.route()` selects an agent and transitions execution state
(`PENDING -> ASSIGNED -> RUNNING`), but does not call any agent CLI, API,
or subprocess. Building agent adapters that actually invoke Claude Code /
Aider / Codex / Gemini is separate, later work. Conflating "decide which
agent should do this" with "actually run that agent" would have coupled
this phase to credentials, network access, and per-agent invocation
protocols — none of which are in scope per the stated constraints (no API
keys/secrets, no n8n/Telegram integration yet).

### 6. Human-in-the-loop kept structural, not bolted on

`ExecutionState` includes `AWAITING_APPROVAL` as a distinct state between
an agent's output and `COMPLETED`. No method transitions an execution to
`COMPLETED` except an explicit `approve()` call. This reflects the
governance rule that no output is published or merged without human
review, made structurally true rather than left to caller discipline.

### 7. One centralized logging setup

No logging architecture existed anywhere in the repository before this
phase. `orchestrator/logging_setup.py` is introduced as the single
logging entry point (`get_logger(name)`), configured via the `LOG_LEVEL`
environment variable already declared in `.env.example`. Future phases
should reuse this rather than configuring `logging` independently.

## Alternatives Considered

- **Extend `config/agents.yaml` in place with the new fields.** Rejected
  — breaking change to an existing file's contract with unclear
  downstream impact.
- **LLM-based agent selection (ask a model which agent fits a task).**
  Rejected for this phase — non-deterministic, harder to test and audit,
  and unnecessary given task metadata is already structured enough for
  rule-based matching.
- **Have `route()` actually invoke agents.** Rejected — pulls in
  credentials/network/subprocess concerns explicitly excluded from this
  phase's scope, and conflates two distinct responsibilities (deciding
  vs. doing).
- **Persist execution state to disk/DB.** Rejected for now — no
  persistence requirement was specified; in-memory state keeps the phase
  minimal. Flagged as a likely Phase-05 need once observability/logging
  infrastructure matures.

## Consequences

- **Positive:** Phase-04 is fully testable without any external
  dependency (no network, no credentials, no subprocess calls). Agent
  metadata has one authoritative, schema-validated source for
  orchestration purposes. Failure modes (bad YAML, unknown status,
  duplicate agent names) raise specific, catchable exceptions instead of
  failing silently — directly addressing the class of bug found in the
  `prompt_registry.yaml` incident.
- **Negative:** There are now three files describing agents
  (`agents.yaml`, `models.yaml`, `agent_registry.yaml`) with partial
  overlap in identifiers. This is a deliberate, documented trade-off
  favoring phase isolation over premature consolidation, but it is debt
  that should be resolved once Phase-02's config-schema work happens.
  Execution state is in-memory only and is lost on process restart.

## Amendment: Phase-04 Patch Release

A post-implementation review of Phase-04 found that decisions 4 and 6
above did not hold up under direct execution: `select_agent()` ordered
candidates by registry file order only (no use of agent priority), and
none of `route()` / `mark_awaiting_approval()` / `approve()` checked an
execution's current state before transitioning it — meaning `approve()`
could be called directly on a freshly-submitted (`PENDING`) execution,
reaching `COMPLETED` with `assigned_agent = None` and no result ever
having been produced or reviewed. This made the "human-in-the-loop kept
structural" claim in decision 6 inaccurate as originally implemented.
This patch release addresses exactly those two gaps, plus one related
cleanup, without altering the design decisions above:

1. **State-machine guards added.** `route()` now requires the execution
   to be `PENDING`, `mark_awaiting_approval()` requires `RUNNING`, and
   `approve()` requires `AWAITING_APPROVAL`. Any other current state
   raises `InvalidStateTransitionError` and leaves the execution's state
   unchanged. `COMPLETED` is now only reachable via the full
   `PENDING → RUNNING → AWAITING_APPROVAL → COMPLETED` path, making
   decision 6's human-review guarantee actually true rather than merely
   intended.

2. **Agent `priority` used as the primary selection key.** `Agent` gained
   a required `priority` field (`high` / `medium` / `low`, mirroring the
   scale already used in `config/agents.yaml`), populated in
   `config/agent_registry.yaml` for all four agents. `select_agent()`
   now selects the highest-priority eligible agent; agents sharing the
   same priority still fall back to registry (insertion) order, which
   was the entirety of the pre-patch rule. This is additive to decision
   4, not a replacement of its deterministic, non-LLM-based approach.

3. **`AgentTask.priority` removed.** It was defined but never read
   anywhere in the codebase. Giving it real behavior would require some
   form of task queueing/ordering, which is a design change beyond a
   patch release's scope; since it had no consumer, removing it was the
   minimal-change option. (Not to be confused with the new `Agent.priority`
   in point 2 above — task priority and agent priority are different,
   unrelated concepts, and only the latter exists post-patch.)

No files outside `orchestrator/`, `config/agent_registry.yaml`, and this
ADR were changed as part of the patch.

## Follow-up

- Resolve `config/` vs `configs/` (still open from ADR-0001/prior
  assessment) — likely belongs in the Phase-02 ADR on config schema
  format.
- Phase-02: add `permissions.yaml` per agent; consider whether
  `agent_registry.yaml` should then be generated from / cross-validated
  against `agents.yaml` + `models.yaml` + `permissions.yaml` rather than
  maintained as a fourth parallel source.
- Phase-05: persistence for `AgentExecution` state, and wiring
  `orchestrator`'s logger output into whatever CI/observability tooling
  that phase introduces.
- Agent adapters (actual invocation of each agent) are required before
  `route()`'s `RUNNING` state means anything beyond "assigned."
- (Patch release follow-up) Consider whether a scoring strategy beyond
  priority-then-registry-order is needed once agent count grows — not
  required for Phase-05 as currently scoped.
