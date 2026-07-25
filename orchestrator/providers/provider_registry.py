"""
orchestrator.providers.provider_registry
===========================================

Loads and validates ``config/model_providers.yaml`` and exposes typed
lookup of each agent's model-provider configuration.

Responsibility boundary (ADR-0005 decision 3): this module is
responsible for **configuration loading, validation, and lookup only**.
It does not perform HTTP calls, does not know any provider's
request/response shape, and does not instantiate a ``ModelProvider``
adapter -- that resolution (``provider_type`` string -> concrete adapter
class) is deliberately deferred to a later task (see ADR-0005 decision 8
and its Follow-up note) so that this registry's behavior never needs to
change when a new provider adapter is added.

Validation philosophy matches ``orchestrator.registry.AgentRegistry`` and
``orchestrator.execution.command_registry.AgentCommandRegistry``: fail
loudly and specifically rather than falling back to a default value
silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from orchestrator.exceptions import (
    ModelProviderRegistryError,
    ProviderConfigNotFoundError,
    ProviderDisabledError,
)
from orchestrator.logging_setup import get_logger
from orchestrator.providers.models import ProviderConfig

logger = get_logger("providers.provider_registry")

_REQUIRED_FIELDS = {
    "provider_type",
    "enabled",
    "base_url",
    "model",
    "api_key_env_var",
    "timeout_seconds",
}

DEFAULT_MODEL_PROVIDERS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "model_providers.yaml"
)


class ModelProviderRegistry:
    """In-memory, validated view of ``config/model_providers.yaml``.

    Configuration loading, validation, and per-agent lookup only -- see
    the module docstring above. Resolving a looked-up ``ProviderConfig``
    into a running ``ModelProvider`` instance is a later task's
    responsibility, not this class's.
    """

    def __init__(self, registry_path: str | Path = DEFAULT_MODEL_PROVIDERS_PATH):
        self._registry_path = Path(registry_path)
        self._configs: dict[str, ProviderConfig] = {}
        self._load()

    def _load(self) -> None:
        if not self._registry_path.exists():
            raise ModelProviderRegistryError(
                f"Model provider file not found: {self._registry_path}"
            )

        try:
            raw_text = self._registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ModelProviderRegistryError(
                f"Could not read model provider file: {self._registry_path}"
            ) from exc

        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise ModelProviderRegistryError(
                f"Model provider file is not valid YAML: {self._registry_path}\n{exc}"
            ) from exc

        if not isinstance(data, dict) or "providers" not in data:
            raise ModelProviderRegistryError(
                "Model provider file must be a mapping with a top-level 'providers' key"
            )

        providers_data = data["providers"]
        if not isinstance(providers_data, dict) or not providers_data:
            raise ModelProviderRegistryError(
                "Model provider file 'providers' key must be a non-empty mapping"
            )

        for agent_name, entry in providers_data.items():
            self._configs[agent_name] = self._parse_entry(agent_name, entry)

        logger.info(
            "Loaded model provider registry: %d agent(s) from %s",
            len(self._configs),
            self._registry_path,
        )

    def _parse_entry(self, agent_name: str, entry: Any) -> ProviderConfig:
        if not isinstance(entry, dict):
            raise ModelProviderRegistryError(
                f"Model provider entry for {agent_name!r} must be a mapping, "
                f"got {type(entry).__name__}"
            )

        missing = _REQUIRED_FIELDS - entry.keys()
        if missing:
            raise ModelProviderRegistryError(
                f"Model provider entry for {agent_name!r} is missing required "
                f"field(s): {sorted(missing)}"
            )

        provider_type = entry["provider_type"]
        if not isinstance(provider_type, str) or not provider_type.strip():
            raise ModelProviderRegistryError(
                f"Model provider entry for {agent_name!r}: 'provider_type' must "
                f"be a non-empty string"
            )

        enabled = entry["enabled"]
        if not isinstance(enabled, bool):
            raise ModelProviderRegistryError(
                f"Model provider entry for {agent_name!r}: 'enabled' must be a boolean"
            )

        base_url = entry["base_url"]
        if not isinstance(base_url, str) or not base_url.strip():
            raise ModelProviderRegistryError(
                f"Model provider entry for {agent_name!r}: 'base_url' must be a non-empty string"
            )

        model = entry["model"]
        if not isinstance(model, str) or not model.strip():
            raise ModelProviderRegistryError(
                f"Model provider entry for {agent_name!r}: 'model' must be a non-empty string"
            )

        api_key_env_var = entry["api_key_env_var"]
        if not isinstance(api_key_env_var, str) or not api_key_env_var.strip():
            raise ModelProviderRegistryError(
                f"Model provider entry for {agent_name!r}: 'api_key_env_var' must "
                f"be a non-empty string"
            )

        timeout_seconds = entry["timeout_seconds"]
        if not isinstance(timeout_seconds, int | float) or isinstance(timeout_seconds, bool):
            raise ModelProviderRegistryError(
                f"Model provider entry for {agent_name!r}: 'timeout_seconds' must be a number"
            )
        if timeout_seconds <= 0:
            raise ModelProviderRegistryError(
                f"Model provider entry for {agent_name!r}: 'timeout_seconds' must "
                f"be a positive number"
            )

        return ProviderConfig(
            provider_type=provider_type,
            enabled=enabled,
            base_url=base_url,
            model=model,
            api_key_env_var=api_key_env_var,
            timeout_seconds=float(timeout_seconds),
        )

    def get_config(self, agent_name: str) -> ProviderConfig:
        """Return the validated, *enabled* ``ProviderConfig`` for ``agent_name``.

        Raises:
            ProviderConfigNotFoundError: no entry exists for ``agent_name``.
            ProviderDisabledError: an entry exists but has ``enabled: false``.
        """
        try:
            config = self._configs[agent_name]
        except KeyError as exc:
            raise ProviderConfigNotFoundError(agent_name) from exc

        if not config.enabled:
            raise ProviderDisabledError(agent_name, config.provider_type)

        return config

    def is_enabled(self, agent_name: str) -> bool:
        """Return whether ``agent_name`` has a configured, enabled provider.

        Never raises -- returns ``False`` for both an unconfigured agent
        and a configured-but-disabled one, for callers that only need a
        yes/no answer without handling two distinct exception types.
        """
        config = self._configs.get(agent_name)
        return config is not None and config.enabled

    def __len__(self) -> int:
        return len(self._configs)

    def __contains__(self, agent_name: str) -> bool:
        return agent_name in self._configs
