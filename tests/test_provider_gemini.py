"""Unit tests for orchestrator.providers.gemini_provider.GeminiProvider.

All HTTP interaction is mocked via httpx.MockTransport -- no real network
calls are made anywhere in this file.
"""

from __future__ import annotations

import httpx
import pytest

from orchestrator.exceptions import ProviderRequestError, ProviderTimeoutError
from orchestrator.providers.gemini_provider import GeminiProvider
from orchestrator.providers.models import ProviderConfig

ENV_VAR = "GEMINI_API_KEY"


def _config(**overrides) -> ProviderConfig:
    defaults = {
        "provider_type": "gemini",
        "enabled": True,
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "model": "gemini-2.0-flash",
        "api_key_env_var": ENV_VAR,
        "timeout_seconds": 30.0,
    }
    defaults.update(overrides)
    return ProviderConfig(**defaults)


def _provider_with_handler(handler) -> GeminiProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return GeminiProvider(_config(), client=client)


# --------------------------------------------------------------------- #
# Success
# --------------------------------------------------------------------- #


def test_generate_success_returns_provider_response(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "gemini-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "gemini-test-key"
        assert "gemini-2.0-flash:generateContent" in str(request.url)
        body = request.read()
        assert b"hello there" in body
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Hi there!"}], "role": "model"}}]},
        )

    provider = _provider_with_handler(handler)
    result = provider.generate("hello there")

    assert result.output == "Hi there!"
    assert result.duration_seconds >= 0


def test_generate_sends_configured_model_in_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "gemini-test-key")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = GeminiProvider(_config(model="gemini-1.5-pro"), client=client)
    provider.generate("hi")

    assert "gemini-1.5-pro:generateContent" in seen["url"]


# --------------------------------------------------------------------- #
# Missing credentials
# --------------------------------------------------------------------- #


def test_generate_missing_api_key_raises_without_network_call(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    called = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["count"] += 1
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

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
    monkeypatch.setenv(ENV_VAR, "gemini-invalid")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "API key not valid"}})

    provider = _provider_with_handler(handler)
    with pytest.raises(ProviderRequestError, match="400"):
        provider.generate("hi")


def test_generate_server_error_raises_provider_request_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "gemini-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    provider = _provider_with_handler(handler)
    with pytest.raises(ProviderRequestError, match="500"):
        provider.generate("hi")


# --------------------------------------------------------------------- #
# Timeout
# --------------------------------------------------------------------- #


def test_generate_timeout_raises_provider_timeout_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "gemini-test-key")

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
    monkeypatch.setenv(ENV_VAR, "gemini-test-key")

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
    monkeypatch.setenv(ENV_VAR, "gemini-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = _provider_with_handler(handler)
    with pytest.raises(ProviderRequestError, match="Unexpected response shape"):
        provider.generate("hi")


def test_generate_non_json_response_raises_provider_request_error(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(ENV_VAR, "gemini-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    provider = _provider_with_handler(handler)
    with pytest.raises(ProviderRequestError, match="Unexpected response shape"):
        provider.generate("hi")
