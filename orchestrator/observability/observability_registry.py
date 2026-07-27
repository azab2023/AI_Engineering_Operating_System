"""
orchestrator.observability.observability_registry
======================================================

Loads and validates ``config/observability.yaml`` and exposes the
resulting ``ObservabilityConfig``. Mirrors
``orchestrator.security.permission_registry.PermissionRegistry``'s
configuration-loading-and-validation-only responsibility boundary and
fail-loud philosophy.

All four keys are optional -- see ADR-0011 decision 4 for why this is
the one deliberate deviation from ``PermissionRegistry``'s
all-required-fields posture: every key here is an independent boolean
toggle with an obvious, safe default, not a structural field like
``path_sandbox.allowed_roots`` whose absence has no sane default.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from orchestrator.exceptions import ObservabilityRegistryError
from orchestrator.logging_setup import get_logger
from orchestrator.observability.models import ObservabilityConfig

logger = get_logger("observability.observability_registry")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OBSERVABILITY_PATH = PROJECT_ROOT / "config" / "observability.yaml"

_BOOLEAN_FIELDS = ("enabled", "record_metrics", "record_events", "timing_enabled")


class ObservabilityRegistry:
    """In-memory, validated view of ``config/observability.yaml``.

    Configuration loading and validation only -- see the module
    docstring above.
    """

    def __init__(self, registry_path: str | Path = DEFAULT_OBSERVABILITY_PATH):
        self._registry_path = Path(registry_path)
        self._config = self._load()

    def _load(self) -> ObservabilityConfig:
        if not self._registry_path.exists():
            raise ObservabilityRegistryError(
                f"Observability config file not found: {self._registry_path}"
            )

        try:
            raw_text = self._registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ObservabilityRegistryError(
                f"Could not read observability config file: {self._registry_path}"
            ) from exc

        try:
            data: Any = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise ObservabilityRegistryError(
                f"Observability config file is not valid YAML: {self._registry_path}\n{exc}"
            ) from exc

        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ObservabilityRegistryError(
                "Observability config file must be a mapping at the top level, "
                f"got {type(data).__name__}"
            )

        values: dict[str, bool] = {}
        for field_name in _BOOLEAN_FIELDS:
            if field_name not in data:
                continue
            value = data[field_name]
            if not isinstance(value, bool):
                raise ObservabilityRegistryError(
                    f"Observability config field {field_name!r} must be a boolean, "
                    f"got {type(value).__name__}"
                )
            values[field_name] = value

        unknown = set(data.keys()) - set(_BOOLEAN_FIELDS)
        if unknown:
            raise ObservabilityRegistryError(
                f"Observability config file has unknown field(s): {sorted(unknown)}"
            )

        config = ObservabilityConfig(**values)
        logger.info(
            "Loaded observability config: enabled=%s record_metrics=%s "
            "record_events=%s timing_enabled=%s from %s",
            config.enabled,
            config.record_metrics,
            config.record_events,
            config.timing_enabled,
            self._registry_path,
        )
        return config

    def config(self) -> ObservabilityConfig:
        return self._config
