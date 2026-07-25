"""
orchestrator.providers.provider_factory
===========================================

``ProviderFactory``: resolves a ``ProviderConfig.provider_type`` string
to a concrete ``ModelProvider`` adapter instance.

This exists so ``HttpAgentInvoker`` (Task 7.5) never has to know which
concrete adapter classes exist -- it asks ``ProviderFactory.create()``
for a ``ModelProvider`` and only ever programs against the
``ModelProvider`` Protocol from there on. Resolution is a plain
registration dict, not an ``if provider_type == "anthropic": ...`` chain
-- adding a new provider (Groq, Ollama, Azure OpenAI, ...) means adding
one new adapter class and one new dict entry here, never editing
existing entries or any conditional logic. See ADR-0005 decision 8.
"""

from __future__ import annotations

import httpx

from orchestrator.exceptions import UnsupportedProviderTypeError
from orchestrator.providers.anthropic_provider import AnthropicProvider
from orchestrator.providers.gemini_provider import GeminiProvider
from orchestrator.providers.models import ProviderConfig
from orchestrator.providers.openai_provider import OpenAIProvider
from orchestrator.providers.provider import ModelProvider


class ProviderFactory:
    """Registration-dict-based resolver from ``provider_type`` to a
    ``ModelProvider`` instance. Stateless -- every method is a
    classmethod; there is nothing to construct an instance of this class
    for."""

    _ADAPTERS: dict[str, type[ModelProvider]] = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "gemini": GeminiProvider,
    }

    @classmethod
    def create(cls, config: ProviderConfig, client: httpx.Client | None = None) -> ModelProvider:
        """Instantiate the ``ModelProvider`` adapter registered for
        ``config.provider_type``.

        Args:
            config: the resolved, enabled ``ProviderConfig`` for one agent
                (typically from ``ModelProviderRegistry.get_config()``).
            client: optional ``httpx.Client`` to inject into the adapter
                (used by tests to supply an ``httpx.MockTransport``-backed
                client). When omitted, the adapter constructs its own.

        Raises:
            UnsupportedProviderTypeError: no adapter is registered for
                ``config.provider_type``.
        """
        try:
            adapter_cls = cls._ADAPTERS[config.provider_type]
        except KeyError as exc:
            raise UnsupportedProviderTypeError(config.provider_type) from exc
        return adapter_cls(config, client=client)
