"""Unit tests for orchestrator.providers.provider_factory.ProviderFactory."""

from __future__ import annotations

import pytest

from orchestrator.exceptions import UnsupportedProviderTypeError
from orchestrator.providers.anthropic_provider import AnthropicProvider
from orchestrator.providers.gemini_provider import GeminiProvider
from orchestrator.providers.models import ProviderConfig
from orchestrator.providers.openai_provider import OpenAIProvider
from orchestrator.providers.provider_factory import ProviderFactory


def _config(provider_type: str) -> ProviderConfig:
    return ProviderConfig(
        provider_type=provider_type,
        enabled=True,
        base_url="https://example.invalid/api",
        model="some-model",
        api_key_env_var="SOME_API_KEY",
        timeout_seconds=30.0,
    )


@pytest.mark.parametrize(
    "provider_type,expected_class",
    [
        ("anthropic", AnthropicProvider),
        ("openai", OpenAIProvider),
        ("gemini", GeminiProvider),
    ],
)
def test_create_returns_correct_adapter_type(provider_type, expected_class):
    provider = ProviderFactory.create(_config(provider_type))
    assert isinstance(provider, expected_class)


def test_create_passes_config_through_to_adapter():
    config = _config("anthropic")
    provider = ProviderFactory.create(config)
    assert provider._config is config  # noqa: SLF001 - internal check, adapter has no public getter


def test_create_unknown_provider_type_raises():
    with pytest.raises(UnsupportedProviderTypeError, match="groq"):
        ProviderFactory.create(_config("groq"))


def test_create_no_if_elif_chain_is_a_pure_lookup():
    """Adding a provider_type is meant to be a dict-entry addition, never
    a conditional branch -- assert the resolution mechanism really is a
    dict lookup, not incidentally correct behavior from branching logic."""
    assert isinstance(ProviderFactory._ADAPTERS, dict)  # noqa: SLF001
    assert set(ProviderFactory._ADAPTERS) == {"anthropic", "openai", "gemini"}  # noqa: SLF001
