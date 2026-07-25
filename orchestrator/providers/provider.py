"""
orchestrator.providers.provider
==================================

Defines ``ModelProvider``, the Port (Strategy/Protocol pattern) that a
model-provider adapter must implement.

This is the extension point ADR-0005 is built around: exactly one
concrete implementation exists per upstream model provider (Anthropic,
OpenAI, Gemini, ...; see ``anthropic_provider.py`` / ``openai_provider.py``
/ ``gemini_provider.py``, added in Task 7.4). ``HttpAgentInvoker``
(Task 7.5) depends only on this Protocol -- never on a concrete adapter
class -- so adding a new provider never requires modifying
``HttpAgentInvoker`` or ``ExecutionEngine``. See ADR-0005 decision 8 for
the full Open/Closed Principle rationale.

This mirrors the ``AgentInvoker`` Protocol in
``orchestrator.execution.invoker`` (Phase-06) one layer deeper: where
``AgentInvoker`` decouples ``ExecutionEngine`` from *how* an agent is run
(CLI subprocess vs. HTTP API), ``ModelProvider`` decouples
``HttpAgentInvoker`` from *which* HTTP API it is calling.
"""

from __future__ import annotations

from typing import Protocol

from orchestrator.providers.models import ProviderResponse


class ModelProvider(Protocol):
    """Port: something that can turn one prompt into one generated
    response by calling a single upstream model provider's HTTP API.

    A conforming implementation owns everything specific to its
    provider: authentication header format, request body shape, and
    where the generated text lives in the response. Callers
    (``HttpAgentInvoker``) know none of that -- they only call
    ``generate()`` and handle its return value or the two exceptions
    below.
    """

    def generate(self, prompt: str) -> ProviderResponse:
        """Send ``prompt`` to the upstream provider and return the
        generated output.

        Raises:
            ProviderTimeoutError: the request exceeded its configured
                ``timeout_seconds``. Treated as retryable by
                ``HttpAgentInvoker`` (mapped to ``AgentTimeoutError``).
            ProviderRequestError: the request could not be completed for
                any other reason -- a connection/network failure, or a
                non-2xx HTTP response (including invalid or expired
                credentials). Treated as retryable by ``HttpAgentInvoker``
                (mapped to ``AgentInvocationError``). See ADR-0005
                decision 5 for why these are not split into finer-grained
                exception types.
        """
        ...
