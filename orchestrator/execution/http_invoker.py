"""
orchestrator.execution.http_invoker
======================================

``HttpAgentInvoker``: a second implementation of the Phase-06
``AgentInvoker`` Protocol, running an agent by calling a model
provider's HTTP API directly instead of shelling out to a CLI (contrast
with ``SubprocessAgentInvoker`` in ``invoker.py``).

This module is the translation boundary described in ADR-0005 decision
2: it is the *only* place that knows both the execution layer
(``ExecutionResult``, ``AgentTimeoutError``, ``AgentInvocationError``)
and the provider layer (``ModelProviderRegistry``, ``ProviderFactory``,
``ProviderResponse``, ``ProviderTimeoutError``, ``ProviderRequestError``)
exist. It contains no provider-specific branching -- resolving *which*
adapter to use is entirely delegated to ``ProviderFactory``.

Error mapping (ADR-0005 decision 5) -- exactly two translations, nothing
else:

    ProviderTimeoutError  -> AgentTimeoutError      (retried by ExecutionEngine)
    ProviderRequestError  -> AgentInvocationError    (retried by ExecutionEngine)

Everything else -- ``ProviderConfigNotFoundError``, ``ProviderDisabledError``,
``UnsupportedProviderTypeError`` -- is a configuration/wiring problem, not
a transient failure, and is deliberately left to propagate out of
``invoke()`` unchanged. ``ExecutionEngine.execute()`` only catches
``AgentTimeoutError`` / ``AgentInvocationError`` for its retry loop (see
``engine.py``), so these three exceptions surface immediately rather
than being retried -- the same behavior ``AgentCommandNotConfiguredError``
already has via ``SubprocessAgentInvoker``.
"""

from __future__ import annotations

import httpx

from orchestrator.exceptions import (
    AgentInvocationError,
    AgentTimeoutError,
    ProviderRequestError,
    ProviderTimeoutError,
)
from orchestrator.execution.models import ExecutionResult
from orchestrator.logging_setup import get_logger
from orchestrator.models import Agent, AgentTask
from orchestrator.prompts.prompt_manager import PromptManager
from orchestrator.providers.provider_factory import ProviderFactory
from orchestrator.providers.provider_registry import ModelProviderRegistry

logger = get_logger("execution.http_invoker")


class HttpAgentInvoker:
    """Invokes an agent by calling its configured model provider's HTTP
    API directly, per ``config/model_providers.yaml``.

    Implements the same ``AgentInvoker`` Protocol as
    ``SubprocessAgentInvoker`` (no changes to that Protocol) -- an
    ``ExecutionEngine`` can be constructed with either one
    interchangeably.
    """

    def __init__(
        self,
        provider_registry: ModelProviderRegistry | None = None,
        client: httpx.Client | None = None,
        prompt_manager: PromptManager | None = None,
    ):
        self._provider_registry = provider_registry or ModelProviderRegistry()
        self._client = client
        self._prompt_manager = prompt_manager

    def _resolve_prompt_text(self, agent: Agent, task: AgentTask) -> str:
        # Phase-08: if task.prompt_id is set, resolve/render it via
        # PromptManager and use that text in place of task.description
        # (see ADR-0006 decision 6). Lazily constructed so existing
        # callers that never use prompts are unaffected even if
        # prompts/prompt_registry.yaml is absent or invalid.
        if task.prompt_id is None:
            return task.description
        if self._prompt_manager is None:
            self._prompt_manager = PromptManager()
        rendered = self._prompt_manager.render(task.prompt_id, agent.name, task.prompt_variables)
        return rendered.text

    def invoke(self, agent: Agent, task: AgentTask) -> ExecutionResult:
        prompt_text = self._resolve_prompt_text(agent, task)

        # Deliberately not caught here -- ProviderConfigNotFoundError /
        # ProviderDisabledError / UnsupportedProviderTypeError are
        # configuration bugs, not transient failures. See module
        # docstring.
        config = self._provider_registry.get_config(agent.name)
        provider = ProviderFactory.create(config, client=self._client)

        try:
            response = provider.generate(prompt_text)
        except ProviderTimeoutError as exc:
            logger.warning(
                "Agent invocation timed out: agent=%s timeout=%.1fs",
                agent.name,
                config.timeout_seconds,
            )
            raise AgentTimeoutError(agent.name, config.timeout_seconds) from exc
        except ProviderRequestError as exc:
            logger.error("Agent invocation failed: agent=%s error=%s", agent.name, exc)
            raise AgentInvocationError(agent.name, str(exc)) from exc

        logger.info(
            "Agent invocation finished: agent=%s duration=%.2fs",
            agent.name,
            response.duration_seconds,
        )
        return ExecutionResult(
            output=response.output,
            exit_code=0,
            duration_seconds=response.duration_seconds,
        )
