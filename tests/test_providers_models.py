"""Unit tests for orchestrator.providers.models (ProviderConfig, ProviderResponse)."""

from __future__ import annotations

import pytest

from orchestrator.providers.models import ProviderConfig, ProviderResponse

# --------------------------------------------------------------------- #
# ProviderConfig
# --------------------------------------------------------------------- #


def _valid_config_kwargs() -> dict:
    return {
        "provider_type": "anthropic",
        "enabled": True,
        "base_url": "https://api.anthropic.com/v1/messages",
        "model": "claude-sonnet-4-6",
        "api_key_env_var": "ANTHROPIC_API_KEY",
        "timeout_seconds": 300.0,
    }


def test_provider_config_accepts_valid_data():
    config = ProviderConfig(**_valid_config_kwargs())
    assert config.provider_type == "anthropic"
    assert config.enabled is True
    assert config.timeout_seconds == 300.0


def test_provider_config_is_provider_type_agnostic():
    """No closed set of provider_type values is enforced here -- a future
    provider (e.g. 'groq') must not require changes to this dataclass.
    See ADR-0005 decision 8."""
    kwargs = _valid_config_kwargs()
    kwargs["provider_type"] = "groq"
    config = ProviderConfig(**kwargs)
    assert config.provider_type == "groq"


def test_provider_config_disabled_is_valid():
    kwargs = _valid_config_kwargs()
    kwargs["enabled"] = False
    config = ProviderConfig(**kwargs)
    assert config.enabled is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_type", ""),
        ("provider_type", "   "),
        ("base_url", ""),
        ("model", ""),
        ("api_key_env_var", ""),
    ],
)
def test_provider_config_rejects_blank_required_strings(field, value):
    kwargs = _valid_config_kwargs()
    kwargs[field] = value
    with pytest.raises(ValueError):
        ProviderConfig(**kwargs)


@pytest.mark.parametrize("timeout", [0, -1, -0.5])
def test_provider_config_rejects_non_positive_timeout(timeout):
    kwargs = _valid_config_kwargs()
    kwargs["timeout_seconds"] = timeout
    with pytest.raises(ValueError):
        ProviderConfig(**kwargs)


def test_provider_config_is_frozen():
    config = ProviderConfig(**_valid_config_kwargs())
    with pytest.raises(AttributeError):
        config.model = "other-model"  # type: ignore[misc]


# --------------------------------------------------------------------- #
# ProviderResponse
# --------------------------------------------------------------------- #


def test_provider_response_accepts_valid_data():
    response = ProviderResponse(output="hello", duration_seconds=1.5)
    assert response.output == "hello"
    assert response.duration_seconds == 1.5


def test_provider_response_accepts_zero_duration():
    response = ProviderResponse(output="hello", duration_seconds=0.0)
    assert response.duration_seconds == 0.0


def test_provider_response_rejects_negative_duration():
    with pytest.raises(ValueError):
        ProviderResponse(output="hello", duration_seconds=-0.1)


def test_provider_response_is_frozen():
    response = ProviderResponse(output="hello", duration_seconds=1.0)
    with pytest.raises(AttributeError):
        response.output = "other"  # type: ignore[misc]
