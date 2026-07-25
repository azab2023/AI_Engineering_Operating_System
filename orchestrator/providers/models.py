"""
orchestrator.providers.models
================================

Data models for Phase-07 (Model Provider Abstraction).

Design notes:
    - Plain, frozen dataclasses only, matching the convention already
      established in ``orchestrator.models`` (Phase-04) and
      ``orchestrator.execution.models`` (Phase-06) -- no pydantic / ORM /
      external validation libraries.
    - ``ProviderConfig`` is intentionally agnostic of any specific
      provider: it is the same shape for Anthropic, OpenAI, Gemini, or a
      future provider (Groq, Ollama, Azure OpenAI, ...). Per ADR-0005
      decision 8, nothing about this dataclass needs to change to add a
      new provider -- ``provider_type`` is a free-form string resolved to
      a concrete ``ModelProvider`` adapter class by
      ``ModelProviderRegistry`` (Task 7.3), not validated against a
      closed set here.
    - ``ProviderResponse`` is the HTTP-provider analogue of
      ``orchestrator.execution.models.ExecutionResult``, but deliberately
      has no ``exit_code``: a ``ModelProvider.generate()`` call either
      returns a successful ``ProviderResponse`` or raises
      (``ProviderTimeoutError`` / ``ProviderRequestError``) -- there is
      no "ran but failed" return value to represent, unlike a CLI
      subprocess's exit code.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    """A validated model-provider configuration for one agent, loaded
    from ``config/model_providers.yaml`` by ``ModelProviderRegistry``.

    Attributes:
        provider_type: which ``ModelProvider`` adapter to use (e.g.
            ``"anthropic"``, ``"openai"``, ``"gemini"``). Free-form by
            design -- see ADR-0005 decision 8.
        enabled: whether this provider entry may be used. A disabled
            entry is a configuration error at lookup time, not a
            transient failure.
        base_url: the provider API endpoint to call.
        model: the provider-side model identifier to request.
        api_key_env_var: name of the environment variable holding the
            credential. Never the credential value itself.
        timeout_seconds: max wall-clock time before a request is treated
            as a timeout.
    """

    provider_type: str
    enabled: bool
    base_url: str
    model: str
    api_key_env_var: str
    timeout_seconds: float

    def __post_init__(self) -> None:
        if not self.provider_type or not self.provider_type.strip():
            raise ValueError("ProviderConfig.provider_type must be a non-empty string")
        if not self.base_url or not self.base_url.strip():
            raise ValueError("ProviderConfig.base_url must be a non-empty string")
        if not self.model or not self.model.strip():
            raise ValueError("ProviderConfig.model must be a non-empty string")
        if not self.api_key_env_var or not self.api_key_env_var.strip():
            raise ValueError("ProviderConfig.api_key_env_var must be a non-empty string")
        if self.timeout_seconds <= 0:
            raise ValueError("ProviderConfig.timeout_seconds must be a positive number")


@dataclass(frozen=True)
class ProviderResponse:
    """The successful outcome of one ``ModelProvider.generate()`` call."""

    output: str
    duration_seconds: float

    def __post_init__(self) -> None:
        if self.duration_seconds < 0:
            raise ValueError("ProviderResponse.duration_seconds must be >= 0")
