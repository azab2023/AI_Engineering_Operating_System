"""
orchestrator.providers.gemini_provider
==========================================

``GeminiProvider``: the ``ModelProvider`` adapter for Google's Gemini
``generateContent`` API (``POST {base_url}/{model}:generateContent``,
e.g.
``https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent``).

Owns everything specific to this one provider -- auth is a query-string
API key rather than a header, request body shape, and where the
generated text lives in the response. Nothing outside this file knows
any of that; see ADR-0005 decisions 1 and 8.
"""

from __future__ import annotations

import os
import time

import httpx

from orchestrator.exceptions import ProviderRequestError, ProviderTimeoutError
from orchestrator.logging_setup import get_logger
from orchestrator.providers.models import ProviderConfig, ProviderResponse

logger = get_logger("providers.gemini_provider")

_PROVIDER_TYPE = "gemini"


class GeminiProvider:
    """``ModelProvider`` implementation for Google's Gemini ``generateContent`` API."""

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

        url = f"{self._config.base_url}/{self._config.model}:generateContent"
        body = {"contents": [{"parts": [{"text": prompt}]}]}

        started = time.monotonic()
        try:
            response = self._client.post(
                url,
                params={"key": api_key},
                json=body,
                timeout=self._config.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            logger.warning(
                "Gemini request timed out: model=%s timeout=%.1fs",
                self._config.model,
                self._config.timeout_seconds,
            )
            raise ProviderTimeoutError(_PROVIDER_TYPE, self._config.timeout_seconds) from exc
        except httpx.HTTPError as exc:
            logger.error("Gemini request failed: %s", exc)
            raise ProviderRequestError(_PROVIDER_TYPE, str(exc)) from exc

        duration = time.monotonic() - started

        if response.status_code >= 400:
            raise ProviderRequestError(
                _PROVIDER_TYPE,
                f"HTTP {response.status_code}: {response.text}",
            )

        try:
            data = response.json()
            output = data["candidates"][0]["content"]["parts"][0]["text"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderRequestError(_PROVIDER_TYPE, f"Unexpected response shape: {exc}") from exc

        logger.info(
            "Gemini request succeeded: model=%s duration=%.2fs",
            self._config.model,
            duration,
        )
        return ProviderResponse(output=output, duration_seconds=duration)
