"""
orchestrator.plugins.models
==============================

Data models for Phase-14 (Plugin & Extension System, ADR-0012).

Design notes:
    - Plain dataclasses only, matching the convention already
      established in ``orchestrator.models`` (Phase-04),
      ``orchestrator.workflow.models`` (Phase-11), and
      ``orchestrator.observability.models`` (Phase-13) -- no pydantic /
      ORM / external validation libraries.
    - ``PluginMetadata`` is frozen (immutable, config-derived),
      mirroring ``WorkflowDefinition`` (Phase-11) and ``ToolDefinition``
      (Phase-09). ``PluginRecord`` is mutable, mirroring ``WorkflowRun``
      -- ``PluginManager`` updates its ``state`` and ``updated_at`` as a
      plugin moves through its lifecycle.
    - Exactly two ``PluginExtensionType`` values this phase, tied 1:1
      to the two existing Open/Closed extension points documented in
      ADR-0007 decision 4 (``ToolFactory``) and ADR-0005 decision 8
      (``ProviderFactory``). See ADR-0012 decision 2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

#: The AEOS version this running codebase reports for plugin
#: version-compatibility checks. Bumped alongside ``pyproject.toml``'s
#: ``version`` field. Kept as a local constant rather than reusing
#: ``orchestrator.__init__.__version__`` -- see ADR-0012 decision 6 for
#: why reconciling the two is out of scope for this phase.
CURRENT_AEOS_VERSION = "1.5.0"

_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def parse_version(value: str) -> tuple[int, int, int]:
    """Parse a strict ``MAJOR.MINOR.PATCH`` string into a comparable
    tuple of ints.

    Raises:
        ValueError: ``value`` does not match ``MAJOR.MINOR.PATCH``.
    """
    if not isinstance(value, str) or not _VERSION_PATTERN.match(value):
        raise ValueError(
            f"Version {value!r} must match the MAJOR.MINOR.PATCH format (e.g. '1.4.0')"
        )
    major, minor, patch = value.split(".")
    return (int(major), int(minor), int(patch))


class PluginExtensionType(str, Enum):
    """Which existing Open/Closed extension point a plugin activates.

    Deliberately limited to the two that already exist -- a plugin
    never introduces a new ``Tool``/``ModelProvider`` implementation
    of its own this phase, it only activates/deactivates an
    already-registered one. See ADR-0012 Context item 1.
    """

    TOOL = "tool"
    PROVIDER = "provider"


class PluginLifecycleState(str, Enum):
    """State machine for a ``PluginRecord``.

    DISCOVERED -> VALIDATED -> INITIALIZED -> UNLOADED

    Mirrors ``WorkflowRunState`` (Phase-11) / ``ExecutionState``
    (Phase-04). Each transition is one-way and performed by exactly one
    ``PluginManager`` method (``load``/``validate``/``initialize``/
    ``unload``); see ADR-0012 decision 4.
    """

    DISCOVERED = "discovered"
    VALIDATED = "validated"
    INITIALIZED = "initialized"
    UNLOADED = "unloaded"


@dataclass(frozen=True)
class PluginMetadata:
    """A validated plugin entry, loaded from ``config/plugins.yaml`` by
    ``PluginRegistry``.

    Attributes:
        plugin_name: unique identifier (the entry's top-level YAML
            key).
        version: the plugin's own version (``MAJOR.MINOR.PATCH``),
            documentation/identification only -- not compared against
            anything.
        description: human-readable purpose, for documentation only.
        enabled: whether this plugin entry may be loaded. A disabled
            entry is a configuration error at ``PluginManager.load()``
            time, not a transient failure.
        extension_type: which existing extension point this plugin
            activates -- ``tool`` or ``provider``.
        target_name: the name of the already-registered entry this
            plugin activates: a ``tool_name`` from ``config/tools.yaml``
            when ``extension_type == TOOL``, or an agent name from
            ``config/model_providers.yaml`` when
            ``extension_type == PROVIDER``.
        min_aeos_version: the minimum AEOS version
            (``MAJOR.MINOR.PATCH``) this plugin is compatible with.
        max_aeos_version: the maximum AEOS version this plugin is
            compatible with, or ``None`` for no upper bound.
    """

    plugin_name: str
    version: str
    description: str
    enabled: bool
    extension_type: PluginExtensionType
    target_name: str
    min_aeos_version: str
    max_aeos_version: str | None = None

    def __post_init__(self) -> None:
        if not self.plugin_name or not self.plugin_name.strip():
            raise ValueError("PluginMetadata.plugin_name must be a non-empty string")
        if not self.description or not self.description.strip():
            raise ValueError("PluginMetadata.description must be a non-empty string")
        if not self.target_name or not self.target_name.strip():
            raise ValueError("PluginMetadata.target_name must be a non-empty string")
        if not isinstance(self.extension_type, PluginExtensionType):
            raise ValueError(
                f"PluginMetadata {self.plugin_name!r}: extension_type must be a "
                f"PluginExtensionType, got {type(self.extension_type).__name__}"
            )

        try:
            parse_version(self.version)
        except ValueError as exc:
            raise ValueError(
                f"PluginMetadata {self.plugin_name!r}: invalid 'version': {exc}"
            ) from exc

        try:
            minimum = parse_version(self.min_aeos_version)
        except ValueError as exc:
            raise ValueError(
                f"PluginMetadata {self.plugin_name!r}: invalid 'min_aeos_version': {exc}"
            ) from exc

        if self.max_aeos_version is not None:
            try:
                maximum = parse_version(self.max_aeos_version)
            except ValueError as exc:
                raise ValueError(
                    f"PluginMetadata {self.plugin_name!r}: invalid 'max_aeos_version': {exc}"
                ) from exc
            if maximum < minimum:
                raise ValueError(
                    f"PluginMetadata {self.plugin_name!r}: max_aeos_version "
                    f"{self.max_aeos_version!r} is lower than min_aeos_version "
                    f"{self.min_aeos_version!r}"
                )


@dataclass
class PluginRecord:
    """Tracks the lifecycle of one loaded plugin.

    Mutable by design (unlike ``PluginMetadata``), matching
    ``WorkflowRun``: ``PluginManager`` updates ``state`` and
    ``updated_at`` as the plugin progresses through
    DISCOVERED -> VALIDATED -> INITIALIZED -> UNLOADED.
    """

    plugin_name: str
    metadata: PluginMetadata
    state: PluginLifecycleState = PluginLifecycleState.DISCOVERED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)
