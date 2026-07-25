"""
orchestrator.providers.anthropic_provider
=============================================

``AnthropicProvider``: the ``ModelProvider`` adapter for Anthropic's
Messages API (``POST {base_url}``, e.g.
``https://api.anthropic.com/v1/messages``).

Owns everything specific to this one provider -- auth header format,
request body shape, and where the generated text lives in the response.
Nothing outside this file knows any of that; see ADR-0005 decisions 1
and 8.
"""

from __future__ import annotations

import os
import time

import httpx

from orchestrator.exceptions import ProviderRequestError, ProviderTimeoutError
from orchestrator.logging_setup import get_logger
from orchestrator.providers.models import ProviderConfig, ProviderResponse

logger = get_logger("providers.anthropic_provider")

_PROVIDER_TYPE = "anthropic"
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_TOKENS = 4096


class AnthropicProvider:
    """``ModelProvider`` implementation for Anthropic's Messages API."""

    def __init__(self, config: ProviderConfig, client: httpx.Client | None = None):
        self._config = config
        self._client = client or httpx.Client()

    def generate(self, prompt: str) -> ProviderResponse:
        api_key = os.environ.get(self._config.api_key_env_var)
        if not api_key:
            raise ProviderRequestError(
                _PROVIDER_TYPE,
                f"Environment variable {self._config.api_key_env_var!r} is not set",
            )

        headers = {
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": self._config.model,
            "max_tokens": _MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }

        started = time.monotonic()
        try:
            response = self._client.post(
                self._config.base_url,
                headers=headers,
                json=body,
                timeout=self._config.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            logger.warning(
                "Anthropic request timed out: model=%s timeout=%.1fs",
                self._config.model,
                self._config.timeout_seconds,
            )
            raise ProviderTimeoutError(_PROVIDER_TYPE, self._config.timeout_seconds) from exc
        except httpx.HTTPError as exc:
            logger.error("Anthropic request failed: %s", exc)
            raise ProviderRequestError(_PROVIDER_TYPE, str(exc)) from exc

        duration = time.monotonic() - started

        if response.status_code >= 400:
            raise ProviderRequestError(
                _PROVIDER_TYPE,
                f"HTTP {response.status_code}: {response.text}",
            )

        try:
            data = response.json()
            output = data["content"][0]["text"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderRequestError(_PROVIDER_TYPE, f"Unexpected response shape: {exc}") from exc

        logger.info(
            "Anthropic request succeeded: model=%s duration=%.2fs",
            self._config.model,
            duration,
        )
        return ProviderResponse(output=output, duration_seconds=duration)
