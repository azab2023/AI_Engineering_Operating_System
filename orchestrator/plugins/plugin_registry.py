"""
orchestrator.plugins.plugin_registry
=======================================

Loads and validates ``config/plugins.yaml`` and exposes typed lookup of
each plugin's metadata.

Responsibility boundary (mirrors ADR-0007 decision 3 for
``ToolRegistry``): this module is responsible for **configuration
loading, validation, and lookup only**. It never checks whether a
plugin's ``target_name`` actually exists in ``ToolRegistry`` /
``ModelProviderRegistry`` -- that cross-registry check belongs to
``PluginManager.validate()`` (ADR-0012 decision 4), so this registry's
behavior never needs to change when a new tool/provider is added
elsewhere.

Validation philosophy matches ``orchestrator.tools.tool_registry.
ToolRegistry`` and ``orchestrator.observability.observability_registry.
ObservabilityRegistry``: fail loudly and specifically rather than
falling back to a default value silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from orchestrator.exceptions import PluginDisabledError, PluginNotFoundError, PluginRegistryError
from orchestrator.logging_setup import get_logger
from orchestrator.plugins.models import PluginExtensionType, PluginMetadata

logger = get_logger("plugins.plugin_registry")

_REQUIRED_FIELDS = {
    "version",
    "description",
    "enabled",
    "extension_type",
    "target_name",
    "min_aeos_version",
}
_VALID_EXTENSION_TYPES = {member.value for member in PluginExtensionType}

DEFAULT_PLUGINS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "plugins.yaml"


class PluginRegistry:
    """In-memory, validated view of ``config/plugins.yaml``.

    Configuration loading, validation, and per-plugin lookup only --
    see the module docstring above. Resolving a looked-up
    ``PluginMetadata`` into a running lifecycle (``PluginRecord``) is
    ``PluginManager``'s responsibility, not this class's.
    """

    def __init__(self, registry_path: str | Path = DEFAULT_PLUGINS_PATH):
        self._registry_path = Path(registry_path)
        self._definitions: dict[str, PluginMetadata] = {}
        self._load()

    def _load(self) -> None:
        if not self._registry_path.exists():
            raise PluginRegistryError(f"Plugin file not found: {self._registry_path}")

        try:
            raw_text = self._registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PluginRegistryError(f"Could not read plugin file: {self._registry_path}") from exc

        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise PluginRegistryError(
                f"Plugin file is not valid YAML: {self._registry_path}\n{exc}"
            ) from exc

        if not isinstance(data, dict) or "plugins" not in data:
            raise PluginRegistryError(
                "Plugin file must be a mapping with a top-level 'plugins' key"
            )

        plugins_data = data["plugins"]
        if not isinstance(plugins_data, dict) or not plugins_data:
            raise PluginRegistryError("Plugin file 'plugins' key must be a non-empty mapping")

        for plugin_name, entry in plugins_data.items():
            self._definitions[plugin_name] = self._parse_entry(plugin_name, entry)

        logger.info(
            "Loaded plugin registry: %d plugin(s) from %s",
            len(self._definitions),
            self._registry_path,
        )

    def _parse_entry(self, plugin_name: str, entry: Any) -> PluginMetadata:
        if not isinstance(entry, dict):
            raise PluginRegistryError(
                f"Plugin entry for {plugin_name!r} must be a mapping, got {type(entry).__name__}"
            )

        missing = _REQUIRED_FIELDS - entry.keys()
        if missing:
            raise PluginRegistryError(
                f"Plugin entry for {plugin_name!r} is missing required field(s): {sorted(missing)}"
            )

        version = entry["version"]
        if not isinstance(version, str) or not version.strip():
            raise PluginRegistryError(
                f"Plugin entry for {plugin_name!r}: 'version' must be a non-empty string"
            )

        description = entry["description"]
        if not isinstance(description, str) or not description.strip():
            raise PluginRegistryError(
                f"Plugin entry for {plugin_name!r}: 'description' must be a non-empty string"
            )

        enabled = entry["enabled"]
        if not isinstance(enabled, bool):
            raise PluginRegistryError(
                f"Plugin entry for {plugin_name!r}: 'enabled' must be a boolean"
            )

        extension_type = entry["extension_type"]
        if not isinstance(extension_type, str) or extension_type not in _VALID_EXTENSION_TYPES:
            raise PluginRegistryError(
                f"Plugin entry for {plugin_name!r}: 'extension_type' must be one of "
                f"{sorted(_VALID_EXTENSION_TYPES)}, got {extension_type!r}"
            )

        target_name = entry["target_name"]
        if not isinstance(target_name, str) or not target_name.strip():
            raise PluginRegistryError(
                f"Plugin entry for {plugin_name!r}: 'target_name' must be a non-empty string"
            )

        min_aeos_version = entry["min_aeos_version"]
        if not isinstance(min_aeos_version, str) or not min_aeos_version.strip():
            raise PluginRegistryError(
                f"Plugin entry for {plugin_name!r}: 'min_aeos_version' must be a non-empty string"
            )

        max_aeos_version = entry.get("max_aeos_version")
        if max_aeos_version is not None and (
            not isinstance(max_aeos_version, str) or not max_aeos_version.strip()
        ):
            raise PluginRegistryError(
                f"Plugin entry for {plugin_name!r}: 'max_aeos_version' must be a "
                f"non-empty string or null"
            )

        unknown = set(entry.keys()) - _REQUIRED_FIELDS - {"max_aeos_version"}
        if unknown:
            raise PluginRegistryError(
                f"Plugin entry for {plugin_name!r} has unknown field(s): {sorted(unknown)}"
            )

        try:
            return PluginMetadata(
                plugin_name=plugin_name,
                version=version,
                description=description,
                enabled=enabled,
                extension_type=PluginExtensionType(extension_type),
                target_name=target_name,
                min_aeos_version=min_aeos_version,
                max_aeos_version=max_aeos_version,
            )
        except ValueError as exc:
            raise PluginRegistryError(f"Plugin entry for {plugin_name!r}: {exc}") from exc

    def get_definition(self, plugin_name: str) -> PluginMetadata:
        """Return the validated, *enabled* ``PluginMetadata`` for
        ``plugin_name``.

        Raises:
            PluginNotFoundError: no entry exists for ``plugin_name``.
            PluginDisabledError: an entry exists but has
                ``enabled: false``.
        """
        try:
            definition = self._definitions[plugin_name]
        except KeyError as exc:
            raise PluginNotFoundError(plugin_name) from exc

        if not definition.enabled:
            raise PluginDisabledError(plugin_name)

        return definition

    def is_enabled(self, plugin_name: str) -> bool:
        """Return whether ``plugin_name`` has a configured, enabled
        plugin entry.

        Never raises -- returns ``False`` for both an unconfigured
        plugin and a configured-but-disabled one, mirroring
        ``ToolRegistry.is_enabled()``.
        """
        definition = self._definitions.get(plugin_name)
        return definition is not None and definition.enabled

    def __len__(self) -> int:
        return len(self._definitions)

    def __contains__(self, plugin_name: str) -> bool:
        return plugin_name in self._definitions
