"""
orchestrator.providers
=========================

Phase-07 Model Provider Abstraction for the AI_Engineering_Operating_System.

This package provides:
    - ``ProviderConfig`` / ``ProviderResponse`` data models (models.py)
    - The ``ModelProvider`` port (provider.py), implemented by exactly
      one adapter class per upstream model provider (Anthropic, OpenAI,
      Gemini, ... -- added in Task 7.4)
    - ``ModelProviderRegistry``, which loads and validates
      ``config/model_providers.yaml`` and resolves an agent name to a
      ``ModelProvider`` instance (added in Task 7.3)

Scope note (Phase-07): this package is what makes it possible to run an
agent by calling a model provider's HTTP API directly, as an alternative
to ``orchestrator.execution.invoker.SubprocessAgentInvoker``'s CLI-based
invocation. See ADR-0004's Phase-07 follow-up and ADR-0005 for the full
design rationale, including the diagram for how this package fits
together with ``orchestrator.execution``.

Only the models, the ``ModelProvider`` Protocol, ``ModelProviderRegistry``,
``ProviderFactory``, and the three concrete adapters (``AnthropicProvider``
/ ``OpenAIProvider`` / ``GeminiProvider``) exist as of Task 7.5. This
completes the Phase-07 provider layer. ``HttpAgentInvoker`` --
``orchestrator.execution.http_invoker.HttpAgentInvoker`` -- is the
translation boundary that wires this package into ``ExecutionEngine``;
it lives in ``orchestrator.execution`` (not here) since it is an
``AgentInvoker`` implementation, matching where
``SubprocessAgentInvoker`` already lives.
"""

from orchestrator.providers.anthropic_provider import AnthropicProvider
from orchestrator.providers.gemini_provider import GeminiProvider
from orchestrator.providers.models import ProviderConfig, ProviderResponse
from orchestrator.providers.openai_provider import OpenAIProvider
from orchestrator.providers.provider import ModelProvider
from orchestrator.providers.provider_factory import ProviderFactory
from orchestrator.providers.provider_registry import ModelProviderRegistry

__all__ = [
    "ProviderConfig",
    "ProviderResponse",
    "ModelProvider",
    "ModelProviderRegistry",
    "ProviderFactory",
    "AnthropicProvider",
    "OpenAIProvider",
    "GeminiProvider",
]
