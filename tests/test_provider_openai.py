"""Unit tests for orchestrator.providers.openai_provider.OpenAIProvider.

All HTTP interaction is mocked via httpx.MockTransport -- no real network
calls are made anywhere in this file.
"""

from __future__ import annotations

import httpx
import pytest

from orchestrator.exceptions import ProviderRequestError, ProviderTimeoutError
from orchestrator.providers.models import ProviderConfig
from orchestrator.providers.openai_provider import OpenAIProvider

ENV_VAR = "OPENAI_API_KEY"


def _config(**overrides) -> ProviderConfig:
    defaults = {
        "provider_type": "openai",
        "enabled": True,
        "base_url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4.1",
        "api_key_env_var": ENV_VAR,
        "timeout_seconds": 30.0,
    }
    defaults.update(overrides)
    return ProviderConfig(**defaults)


def _provider_with_handler(handler) -> OpenAIProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return OpenAIProvider(_config(), client=client)


# --------------------------------------------------------------------- #
# Success
# --------------------------------------------------------------------- #


def test_generate_success_returns_provider_response(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "sk-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-test-key"
        body = request.read()
        assert b"hello there" in body
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "Hi there!"}}]},
        )

    provider = _provider_with_handler(handler)
    result = provider.generate("hello there")

    assert result.output == "Hi there!"
    assert result.duration_seconds >= 0


def test_generate_sends_configured_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "sk-test-key")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = OpenAIProvider(_config(model="gpt-4o"), client=client)
    provider.generate("hi")

    assert seen["body"]["model"] == "gpt-4o"


# --------------------------------------------------------------------- #
# Missing credentials
# --------------------------------------------------------------------- #


def test_generate_missing_api_key_raises_without_network_call(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    called = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["count"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = _provider_with_handler(handler)
    with pytest.raises(ProviderRequestError, match=ENV_VAR):
        provider.generate("hi")
    assert called["count"] == 0


# --------------------------------------------------------------------- #
# Invalid credentials (non-2xx)
# --------------------------------------------------------------------- #


def test_generate_invalid_credentials_raises_provider_request_error(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(ENV_VAR, "sk-invalid")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}})

    provider = _provider_with_handler(handler)
    with pytest.raises(ProviderRequestError, match="401"):
        provider.generate("hi")


def test_generate_rate_limit_raises_provider_request_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "sk-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limit exceeded")

    provider = _provider_with_handler(handler)
    with pytest.raises(ProviderRequestError, match="429"):
        provider.generate("hi")


# --------------------------------------------------------------------- #
# Timeout
# --------------------------------------------------------------------- #


def test_generate_timeout_raises_provider_timeout_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "sk-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = _provider_with_handler(handler)
    with pytest.raises(ProviderTimeoutError):
        provider.generate("hi")


# --------------------------------------------------------------------- #
# Connection failure
# --------------------------------------------------------------------- #


def test_generate_connection_error_raises_provider_request_error(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(ENV_VAR, "sk-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = _provider_with_handler(handler)
    with pytest.raises(ProviderRequestError):
        provider.generate("hi")


# --------------------------------------------------------------------- #
# Malformed response
# --------------------------------------------------------------------- #


def test_generate_malformed_response_raises_provider_request_error(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(ENV_VAR, "sk-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = _provider_with_handler(handler)
    with pytest.raises(ProviderRequestError, match="Unexpected response shape"):
        provider.generate("hi")


def test_generate_non_json_response_raises_provider_request_error(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(ENV_VAR, "sk-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    provider = _provider_with_handler(handler)
    with pytest.raises(ProviderRequestError, match="Unexpected response shape"):
        provider.generate("hi")
