"""
orchestrator.tools.tool_registry
====================================

Loads and validates ``config/tools.yaml`` and exposes typed lookup of
each tool's definition.

Responsibility boundary (mirrors ADR-0005 decision 3 for
``ModelProviderRegistry``): this module is responsible for
**configuration loading, validation, and lookup only**. It does not run
any tool and does not instantiate a ``Tool`` implementation -- that
resolution (``tool_type`` string -> concrete class) is
``ToolFactory``'s job (Task 9.3), so this registry's behavior never
needs to change when a new built-in tool is added.

Validation philosophy matches ``orchestrator.registry.AgentRegistry``,
``orchestrator.execution.command_registry.AgentCommandRegistry``, and
``orchestrator.providers.provider_registry.ModelProviderRegistry``: fail
loudly and specifically rather than falling back to a default value
silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from orchestrator.exceptions import ToolDisabledError, ToolNotFoundError, ToolRegistryError
from orchestrator.logging_setup import get_logger
from orchestrator.tools.models import ToolDefinition, ToolParameter

logger = get_logger("tools.tool_registry")

_REQUIRED_FIELDS = {"tool_type", "enabled", "description"}
_REQUIRED_PARAMETER_FIELDS = {"name", "type", "required"}

DEFAULT_TOOLS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "tools.yaml"


class ToolRegistry:
    """In-memory, validated view of ``config/tools.yaml``.

    Configuration loading, validation, and per-tool lookup only -- see
    the module docstring above. Resolving a looked-up ``ToolDefinition``
    into a running ``Tool`` instance is ``ToolFactory``'s responsibility,
    not this class's.
    """

    def __init__(self, registry_path: str | Path = DEFAULT_TOOLS_PATH):
        self._registry_path = Path(registry_path)
        self._definitions: dict[str, ToolDefinition] = {}
        self._load()

    def _load(self) -> None:
        if not self._registry_path.exists():
            raise ToolRegistryError(f"Tool file not found: {self._registry_path}")

        try:
            raw_text = self._registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ToolRegistryError(f"Could not read tool file: {self._registry_path}") from exc

        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise ToolRegistryError(
                f"Tool file is not valid YAML: {self._registry_path}\n{exc}"
            ) from exc

        if not isinstance(data, dict) or "tools" not in data:
            raise ToolRegistryError("Tool file must be a mapping with a top-level 'tools' key")

        tools_data = data["tools"]
        if not isinstance(tools_data, dict) or not tools_data:
            raise ToolRegistryError("Tool file 'tools' key must be a non-empty mapping")

        for tool_name, entry in tools_data.items():
            self._definitions[tool_name] = self._parse_entry(tool_name, entry)

        logger.info(
            "Loaded tool registry: %d tool(s) from %s",
            len(self._definitions),
            self._registry_path,
        )

    def _parse_entry(self, tool_name: str, entry: Any) -> ToolDefinition:
        if not isinstance(entry, dict):
            raise ToolRegistryError(
                f"Tool entry for {tool_name!r} must be a mapping, got {type(entry).__name__}"
            )

        missing = _REQUIRED_FIELDS - entry.keys()
        if missing:
            raise ToolRegistryError(
                f"Tool entry for {tool_name!r} is missing required field(s): {sorted(missing)}"
            )

        tool_type = entry["tool_type"]
        if not isinstance(tool_type, str) or not tool_type.strip():
            raise ToolRegistryError(
                f"Tool entry for {tool_name!r}: 'tool_type' must be a non-empty string"
            )

        enabled = entry["enabled"]
        if not isinstance(enabled, bool):
            raise ToolRegistryError(f"Tool entry for {tool_name!r}: 'enabled' must be a boolean")

        description = entry["description"]
        if not isinstance(description, str) or not description.strip():
            raise ToolRegistryError(
                f"Tool entry for {tool_name!r}: 'description' must be a non-empty string"
            )

        raw_parameters = entry.get("parameters", [])
        if not isinstance(raw_parameters, list):
            raise ToolRegistryError(f"Tool entry for {tool_name!r}: 'parameters' must be a list")

        parameters = tuple(
            self._parse_parameter(tool_name, raw_parameter) for raw_parameter in raw_parameters
        )

        raw_sandboxed_parameters = entry.get("sandboxed_parameters", [])
        if not isinstance(raw_sandboxed_parameters, list):
            raise ToolRegistryError(
                f"Tool entry for {tool_name!r}: 'sandboxed_parameters' must be a list"
            )
        for name in raw_sandboxed_parameters:
            if not isinstance(name, str) or not name.strip():
                raise ToolRegistryError(
                    f"Tool entry for {tool_name!r}: 'sandboxed_parameters' entries must be "
                    f"non-empty strings, got {name!r}"
                )

        access_mode = entry.get("access_mode", "read")
        if not isinstance(access_mode, str):
            raise ToolRegistryError(f"Tool entry for {tool_name!r}: 'access_mode' must be a string")

        try:
            return ToolDefinition(
                tool_name=tool_name,
                tool_type=tool_type,
                enabled=enabled,
                description=description,
                parameters=parameters,
                sandboxed_parameters=tuple(raw_sandboxed_parameters),
                access_mode=access_mode,
            )
        except ValueError as exc:
            raise ToolRegistryError(f"Tool entry for {tool_name!r}: {exc}") from exc

    def _parse_parameter(self, tool_name: str, entry: Any) -> ToolParameter:
        if not isinstance(entry, dict):
            raise ToolRegistryError(
                f"Tool {tool_name!r}: each parameter must be a mapping, got {type(entry).__name__}"
            )

        missing = _REQUIRED_PARAMETER_FIELDS - entry.keys()
        if missing:
            raise ToolRegistryError(
                f"Tool {tool_name!r}: parameter entry is missing required "
                f"field(s): {sorted(missing)}"
            )

        name = entry["name"]
        if not isinstance(name, str) or not name.strip():
            raise ToolRegistryError(
                f"Tool {tool_name!r}: parameter 'name' must be a non-empty string"
            )

        param_type = entry["type"]
        if not isinstance(param_type, str):
            raise ToolRegistryError(f"Tool {tool_name!r}: parameter 'type' must be a string")

        required = entry["required"]
        if not isinstance(required, bool):
            raise ToolRegistryError(f"Tool {tool_name!r}: parameter 'required' must be a boolean")

        description = entry.get("description", "")
        if not isinstance(description, str):
            raise ToolRegistryError(f"Tool {tool_name!r}: parameter 'description' must be a string")

        try:
            return ToolParameter(
                name=name, type=param_type, required=required, description=description
            )
        except ValueError as exc:
            raise ToolRegistryError(f"Tool {tool_name!r}: {exc}") from exc

    def get_definition(self, tool_name: str) -> ToolDefinition:
        """Return the validated, *enabled* ``ToolDefinition`` for
        ``tool_name``.

        Raises:
            ToolNotFoundError: no entry exists for ``tool_name``.
            ToolDisabledError: an entry exists but has ``enabled: false``.
        """
        try:
            definition = self._definitions[tool_name]
        except KeyError as exc:
            raise ToolNotFoundError(tool_name) from exc

        if not definition.enabled:
            raise ToolDisabledError(tool_name)

        return definition

    def is_enabled(self, tool_name: str) -> bool:
        """Return whether ``tool_name`` has a configured, enabled tool.

        Never raises -- returns ``False`` for both an unconfigured tool
        and a configured-but-disabled one, for callers that only need a
        yes/no answer without handling two distinct exception types.
        """
        definition = self._definitions.get(tool_name)
        return definition is not None and definition.enabled

    def __len__(self) -> int:
        return len(self._definitions)

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self._definitions
