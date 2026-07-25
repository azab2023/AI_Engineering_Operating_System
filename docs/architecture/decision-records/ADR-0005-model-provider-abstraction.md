# ADR-0005: Model Provider Abstraction (Phase-07)

- **Status:** Accepted
- **Date:** Phase-07
- **Deciders:** Lead AI Systems Architect

## Context

ADR-0004's Follow-up section flagged this explicitly: "Phase-07 (Model
Provider Abstraction, per `PROJECT_ROADMAP.md`) is the natural place to
add a second `AgentInvoker` implementation for raw HTTP provider APIs...
`ExecutionEngine` requires no changes for that -- only a new invoker."

Through Phase-06, the only way to run an agent is
`SubprocessAgentInvoker`, which shells out to each agent's local CLI
(`claude`, `codex`, `aider`, `gemini`) per `config/agent_commands.yaml`.
That requires the CLI to be installed and authenticated on the machine
running AEOS. There is no way to invoke a model provider's HTTP API
directly (e.g. from a CI runner or a server process with no CLI
installed), even though `.env.example` has carried
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` placeholders
since Phase-01.

`requirements.txt` has no HTTP client library. `orchestrator.execution`
already isolates *how an agent is invoked* behind the `AgentInvoker`
Protocol (ADR-0004, decision 2) specifically so a second implementation
could be added without touching `ExecutionEngine`, `Orchestrator`, or
`orchestrator/models.py`.

## Decision

### 1. One `ModelProvider` implementation per provider, no generic branching client

`orchestrator/providers/provider.py` defines `ModelProvider` as a
`typing.Protocol` with one method, `generate(prompt: str) ->
ProviderResponse` -- the same Port/Strategy shape as `AgentInvoker`
(ADR-0004, decision 2) and `ExecutionRepository` (ADR-0003, decision 1).

Three concrete adapters implement it: `AnthropicProvider`,
`OpenAIProvider`, `GeminiProvider` (`orchestrator/providers/
anthropic_provider.py`, `openai_provider.py`, `gemini_provider.py`).
Each owns exactly one provider's request/response shape (endpoint path,
auth header format, JSON body, and where the generated text lives in the
response). A single generic client with an `if provider_type ==
"anthropic": ...` branch was considered and rejected -- see Alternatives.

### 2. `HttpAgentInvoker` is provider-agnostic by construction

`orchestrator/execution/http_invoker.py` adds `HttpAgentInvoker`,
a second implementation of the existing `AgentInvoker` Protocol
(no changes to that Protocol). It depends only on `ModelProviderRegistry`
to resolve `agent.name -> ModelProvider` and on the `ModelProvider`
Protocol to call `.generate()`. It contains no `if provider ==
"anthropic"` branching and no knowledge of any provider's request/
response shape -- that knowledge is fully owned by the three adapters
in decision 1. This mirrors how `ExecutionEngine` itself stays agent-
invoker-agnostic; `HttpAgentInvoker` now applies the same discipline one
layer down.

### 3. `ModelProviderRegistry`: configuration and lookup only

`orchestrator/providers/provider_registry.py` adds
`ModelProviderRegistry`, loaded from the new `config/model_providers.yaml`.
Its responsibility is strictly: parse/validate the YAML (same
fail-loudly philosophy as `AgentRegistry` and `AgentCommandRegistry`),
instantiate the correct `ModelProvider` adapter class for each entry's
declared `provider_type`, and expose `get_provider(agent_name) ->
ModelProvider`. It does not call `.generate()`, retry, or otherwise
touch provider behavior -- that stays in `HttpAgentInvoker` (decision 2)
and the adapters (decision 1). This keeps the registry unit-testable
with zero HTTP calls, matching `AgentCommandRegistry`'s existing test
style.

### 4. New `config/model_providers.yaml`, `config/models.yaml` untouched

Additive, not a replacement -- the same reasoning ADR-0004 decision 3
already applied to `agent_commands.yaml` vs `agent_registry.yaml`.
`config/models.yaml` (Phase-01/02: provider/purpose metadata) is
selection-adjacent documentation, not invocation configuration, and
keeps its existing shape and callers.

Each entry additionally carries an `enabled: true|false` flag so a
provider can be turned off without deleting or commenting out its
config block:

```yaml
providers:
  claude_code:
    provider_type: anthropic
    enabled: true
    base_url: https://api.anthropic.com/v1/messages
    model: claude-sonnet-4-6
    api_key_env_var: ANTHROPIC_API_KEY
    timeout_seconds: 300

  codex:
    provider_type: openai
    enabled: true
    base_url: https://api.openai.com/v1/chat/completions
    model: gpt-4.1
    api_key_env_var: OPENAI_API_KEY
    timeout_seconds: 300

  gemini:
    provider_type: gemini
    enabled: false
    base_url: https://generativelanguage.googleapis.com/v1beta/models
    model: gemini-2.0-flash
    api_key_env_var: GEMINI_API_KEY
    timeout_seconds: 300
```

Only the *name* of the environment variable holding a credential is ever
written to this file, never a key value, per `CLAUDE.md` §3 ("Never
commit secrets"). `ModelProviderRegistry.get_provider()` raises
`ProviderDisabledError` for a disabled entry and
`ProviderConfigNotFoundError` for a missing one -- both are configuration
errors, not transient failures, so `HttpAgentInvoker` lets them propagate
immediately rather than retrying, mirroring how
`AgentCommandNotConfiguredError` is handled in `SubprocessAgentInvoker` /
`ExecutionEngine` today.

### 5. Error mapping onto the existing `ExecutionEngine` retry contract

`HttpAgentInvoker` translates every provider/network failure into the
same two exceptions `ExecutionEngine` already knows how to retry
(ADR-0004, decision 4) -- no changes to `ExecutionEngine` or
`RetryPolicy` are needed:

| Condition | Raised as | Retried by `ExecutionEngine`? |
|---|---|---|
| Request exceeds `timeout_seconds` | `AgentTimeoutError` | Yes |
| Connection/network failure | `AgentInvocationError` | Yes |
| Non-2xx HTTP response (incl. invalid/expired credentials, 4xx/5xx) | `AgentInvocationError` | Yes |
| Provider disabled (`enabled: false`) | `ProviderDisabledError` | No -- config bug, propagates immediately |
| No config entry for the agent | `ProviderConfigNotFoundError` | No -- config bug, propagates immediately |

A non-2xx response is deliberately *not* surfaced as a distinct
exception type (e.g. no separate "auth error" exception): from
`ExecutionEngine`'s point of view a 401 and a 503 are both "this attempt
failed, and a second attempt is cheap and harmless" -- exactly the same
reasoning ADR-0004 decision 4 already used for `AgentInvocationError`
covering a missing CLI executable.

### 6. Scope boundary: no streaming, no tool-calling

`ModelProvider.generate()` returns one complete `ProviderResponse` per
call; no server-sent-events / chunked streaming and no function/tool-
calling support are implemented in this phase. Both are real provider
capabilities but are unrelated to closing the ADR-0004 follow-up item
(having an HTTP-based `AgentInvoker` at all) and would each need their
own design (streaming would change `AgentInvoker`'s one-shot return
contract; tool-calling overlaps with the not-yet-built Phase-09 Tool
Execution Framework).

### 7. New runtime dependency: `httpx`

`requirements.txt` gains `httpx` -- the only new runtime dependency this
phase introduces. Chosen over `requests` for built-in per-request timeout
handling (needed to implement `AgentTimeoutError` precisely) and because
its `httpx.MockTransport` allows the adapter and invoker test suites to
run against a fully in-process fake transport, with no real network
call, no `unittest.mock.patch` of internals, and no live API credentials
-- matching the existing project convention (see `tests/
test_execution_invoker.py`, which exercises the real
`SubprocessAgentInvoker` against harmless inline subprocesses rather than
mocking `subprocess.run`).

### 8. The provider layer satisfies the Open/Closed Principle by construction

Decisions 1-3 are deliberately layered so that adding a new provider is
an *extension*, never a *modification*, of `HttpAgentInvoker` or
`ExecutionEngine`:

- `HttpAgentInvoker` depends only on `ModelProviderRegistry.get_provider()`
  and the `ModelProvider` Protocol (decision 2) -- it has no reference to
  any concrete provider class, so it cannot need editing when a provider
  is added or removed.
- `ModelProviderRegistry` depends only on `provider_type` strings from
  `config/model_providers.yaml` mapped to adapter classes (decision 3) --
  registering a new mapping does not touch existing mappings or lookup
  logic.
- `ExecutionEngine` (Phase-06) depends only on the `AgentInvoker`
  Protocol and never on `HttpAgentInvoker` or any provider concept at
  all, so it is two layers removed from this extension point and is
  never a candidate for modification here.

Concretely: adding support for a new provider -- e.g. **Groq**,
**Ollama**, or **Azure OpenAI** -- requires exactly two additions and
zero modifications:

1. One new `ModelProvider` implementation (e.g. `groq_provider.py`)
   implementing `generate()` for that provider's request/response shape.
2. One new `provider_type` entry in `config/model_providers.yaml` (and,
   if the registry's `provider_type -> class` mapping is a literal
   dict rather than a plug-in/entry-point mechanism, one new line adding
   that mapping in `ModelProviderRegistry`'s constructor -- this is
   registration data, not behavior, and is the only place outside a new
   adapter file that a new provider ever touches).

`ExecutionEngine`, `HttpAgentInvoker`, the `ModelProvider` Protocol, the
`AgentInvoker` Protocol, and every existing provider adapter remain
byte-for-byte unchanged. This is the same Open/Closed guarantee
`ExecutionRepository` already gives Phase-05 storage backends and
`AgentInvoker` already gives Phase-06/07 invocation backends -- Phase-07
extends that guarantee one layer deeper, into provider selection itself.

## Architecture Diagram

```
 ┌────────────────────┐
 │  ExecutionEngine    │   orchestrator/execution/engine.py (Phase-06, UNCHANGED)
 │  (retry, state       │
 │   transitions)        │
 └──────────┬────────────┘
            │ AgentInvoker.invoke(agent, task)
            ▼
 ┌────────────────────┐
 │  HttpAgentInvoker    │   orchestrator/execution/http_invoker.py (NEW)
 │  - provider-agnostic  │   implements the existing AgentInvoker Protocol
 │  - maps errors to      │   knows NOTHING about anthropic/openai/gemini
 │    AgentTimeoutError /  │   request/response shapes
 │    AgentInvocationError  │
 └──────────┬────────────────┘
            │ registry.get_provider(agent.name)
            ▼
 ┌────────────────────┐
 │ ModelProviderRegistry │   orchestrator/providers/provider_registry.py (NEW)
 │  - loads/validates      │   config/model_providers.yaml
 │    model_providers.yaml  │   enabled/disabled lookup
 │  - instantiates the       │   NO provider behavior lives here
 │    right adapter class     │
 └──────────┬─────────────────┘
            │ returns a ModelProvider
            ▼
 ┌────────────────────┐
 │   ModelProvider       │   orchestrator/providers/provider.py (NEW, Protocol)
 │   (Protocol: generate)  │
 └──────────┬─────────────┘
            │ implemented by exactly one of:
            ▼
 ┌───────────────┬───────────────┬───────────────┐
 │AnthropicProvider│ OpenAIProvider │ GeminiProvider │   orchestrator/providers/*.py (NEW)
 │ (Messages API)   │ (Chat Completions)│ (generateContent)│  each owns ONE provider's
 └───────┬─────────┴───────┬───────┴───────┬───────┘   request/response shape
         │                 │               │
         ▼                 ▼               ▼
    api.anthropic.com  api.openai.com  generativelanguage
                                        .googleapis.com
                    (httpx.Client, real network at runtime;
                     httpx.MockTransport in tests)
```

## Alternatives Considered

- **One generic `HttpModelProvider` with provider-specific branching
  inside it** (`if provider_type == "anthropic": ...`). Rejected --
  this is the exact shape ADR-0002 and ADR-0004 already rejected once
  each for a different concern (routing logic embedded in a registry,
  invocation knowledge embedded in selection metadata). A branching
  client also fails the "one adapter, one responsibility" pattern every
  other Port/Adapter pair in this codebuse uses (`AgentInvoker` ->
  `SubprocessAgentInvoker`; `ExecutionRepository` -> `InMemory...` /
  `Sqlite...`), and would need its own internal tests per branch anyway
  -- at which point it is three adapters wearing one class's name.
- **Add `command`-style HTTP config directly onto `Agent` /
  `agent_registry.yaml`.** Rejected for the same reason ADR-0004 decision
  3 rejected it for CLI commands: couples selection metadata to
  invocation mechanics.
- **Let `ModelProviderRegistry` also perform the HTTP call (a
  "registry that generates").** Rejected -- collapses configuration
  lookup and behavior into one class, which is harder to unit-test in
  isolation and breaks the Repository/Registry convention already
  established in `AgentCommandRegistry` (config-and-lookup only, never
  behavior).
- **`requests` instead of `httpx`.** Rejected -- `requests` has no
  native per-request timeout-as-exception ergonomics as clean as
  `httpx`'s, and lacks an equivalent to `httpx.MockTransport` for
  dependency-free testing without patching internals.
- **Implement streaming now, since providers support it.** Rejected --
  out of scope per this phase's stated boundary (decision 6); would
  change `AgentInvoker`'s synchronous one-shot contract, a bigger design
  change than "add a second invoker."

## Consequences

- AEOS can now run an agent's underlying model via direct HTTP API call,
  with no CLI installation required on the host running AEOS -- closing
  the ADR-0004 follow-up item.
- `ExecutionEngine`, `Orchestrator`, `orchestrator/models.py`,
  `orchestrator/registry.py`, and `agent_registry.yaml`'s schema are
  **unchanged** by this phase -- verified by construction, since
  `HttpAgentInvoker` only implements the pre-existing `AgentInvoker`
  Protocol.
- Operators choosing `HttpAgentInvoker` must populate
  `config/model_providers.yaml` for every agent they intend to run this
  way, and export the real credential under the env var name referenced
  there (`.env.example` already reserves the three names used above).
  A missing or disabled entry fails immediately and specifically
  (`ProviderConfigNotFoundError` / `ProviderDisabledError`) rather than
  attempting a doomed network call.
- `requirements.txt` gains one new runtime dependency, `httpx`.
- Adding a fifth provider (e.g. Groq, Ollama, Azure OpenAI) in the
  future means adding one new adapter class plus one new
  `model_providers.yaml` entry -- no changes to `ExecutionEngine`,
  `HttpAgentInvoker`, or the `ModelProvider` Protocol; see decision 8
  for why this is a structural (Open/Closed) guarantee rather than a
  convention that merely happens to hold today.

## Follow-up

- Streaming support, if needed later, requires its own ADR -- it changes
  `ModelProvider.generate()`'s (and possibly `AgentInvoker.invoke()`'s)
  synchronous, single-return contract.
- Tool-calling / function-calling is deferred to whichever phase
  implements Phase-09 (Tool Execution Framework); `ModelProvider` may
  need a second method then, not a change to `generate()`.
- No policy yet exists for choosing `SubprocessAgentInvoker` vs.
  `HttpAgentInvoker` per agent at runtime beyond "whichever the caller
  constructs `ExecutionEngine` with" -- a config-driven choice (e.g. per
  agent in `agent_commands.yaml` / `model_providers.yaml`) is a
  reasonable future extension, not required for this phase.
- `config/` vs `configs/` remains open (carried over from
  ADR-0001/0002/0003), unaffected by this phase.
