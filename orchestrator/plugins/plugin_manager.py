"""
orchestrator.plugins.plugin_manager
======================================

``PluginManager``: the sole Facade for moving a plugin through its
four-stage lifecycle (load -> validate -> initialize -> unload).
Mirrors ``orchestrator.tools.tool_executor.ToolExecutor`` (Phase-09)
and ``orchestrator.memory.memory_manager.MemoryManager`` (Phase-10) one
layer over -- it composes ``PluginRegistry`` (config lookup) with the
existing ``ToolRegistry`` / ``ModelProviderRegistry`` (read-only
existence checks) and is the only entry point a future caller is
expected to depend on.

``PluginManager`` never calls ``Tool.execute()``, ``ToolFactory.
create()``, or any ``ModelProvider`` adapter -- it introduces no new
execution path, so it cannot bypass ``ToolAuthorizer`` (Phase-12).
See ADR-0012 decision 5.
"""

from __future__ import annotations

from orchestrator.exceptions import (
    InvalidPluginStateTransitionError,
    PluginAlreadyLoadedError,
    PluginTargetNotFoundError,
    PluginVersionIncompatibleError,
    UnknownPluginRecordError,
)
from orchestrator.logging_setup import get_logger
from orchestrator.observability.models import MetricPoint, ObservabilityEvent
from orchestrator.observability.recorder import ObservabilityRecorder
from orchestrator.plugins.models import (
    CURRENT_AEOS_VERSION,
    PluginExtensionType,
    PluginLifecycleState,
    PluginRecord,
    parse_version,
)
from orchestrator.plugins.plugin_registry import PluginRegistry
from orchestrator.providers.provider_registry import ModelProviderRegistry
from orchestrator.tools.tool_registry import ToolRegistry

logger = get_logger("plugins.plugin_manager")


class PluginManager:
    """Loads, validates, initializes, and unloads plugins declared in
    ``config/plugins.yaml``.

    Args:
        registry: source of validated ``PluginMetadata`` lookups.
            Defaults to a ``PluginRegistry`` loaded from the default
            ``config/plugins.yaml`` path.
        tool_registry: used only by ``validate()`` to confirm a
            ``PluginExtensionType.TOOL`` plugin's ``target_name`` is an
            enabled tool. Defaults to a ``ToolRegistry`` loaded from
            the default ``config/tools.yaml`` path.
        provider_registry: used only by ``validate()`` to confirm a
            ``PluginExtensionType.PROVIDER`` plugin's ``target_name``
            is an enabled provider. Defaults to a
            ``ModelProviderRegistry`` loaded from the default
            ``config/model_providers.yaml`` path.
        observer: the Phase-13 (ADR-0011) observability Port. Defaults
            to ``None`` -- unchanged, no-op behavior when omitted,
            matching every other integrated component's shape.
    """

    def __init__(
        self,
        registry: PluginRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
        provider_registry: ModelProviderRegistry | None = None,
        observer: ObservabilityRecorder | None = None,
    ):
        self._registry = registry or PluginRegistry()
        self._tool_registry = tool_registry or ToolRegistry()
        self._provider_registry = provider_registry or ModelProviderRegistry()
        self._observer = observer
        self._records: dict[str, PluginRecord] = {}

    # ------------------------------------------------------------------ #
    # Phase-13 (ADR-0011) observability helpers
    # ------------------------------------------------------------------ #

    def _observe_event(self, event_type: str, **attributes: str) -> None:
        if self._observer is None:
            return
        self._observer.record_event(
            ObservabilityEvent(
                component="plugin_manager", event_type=event_type, attributes=attributes
            )
        )

    def _observe_transition(self, plugin_name: str, stage: str, outcome: str) -> None:
        if self._observer is None:
            return
        self._observer.record_metric(
            MetricPoint(
                name="plugin_manager.lifecycle_transitions_total",
                value=1,
                metric_type="counter",
                tags={"plugin_name": plugin_name, "stage": stage, "outcome": outcome},
            )
        )

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def load(self, plugin_name: str) -> PluginRecord:
        """Look up ``plugin_name`` in the plugin registry and create a
        new ``PluginRecord`` in ``DISCOVERED`` state.

        Raises:
            PluginNotFoundError: no entry exists for ``plugin_name``.
            PluginDisabledError: the entry exists but has
                ``enabled: false``.
            PluginAlreadyLoadedError: a record for ``plugin_name`` was
                already created by an earlier ``load()`` call.
        """
        if plugin_name in self._records:
            self._observe_transition(plugin_name, "load", "error")
            raise PluginAlreadyLoadedError(plugin_name)

        metadata = self._registry.get_definition(plugin_name)
        record = PluginRecord(plugin_name=plugin_name, metadata=metadata)
        self._records[plugin_name] = record

        logger.info("Plugin loaded: plugin_name=%s", plugin_name)
        self._observe_event("plugin_loaded", plugin_name=plugin_name)
        self._observe_transition(plugin_name, "load", "success")
        return record

    def validate(self, plugin_name: str) -> PluginRecord:
        """Validate a ``DISCOVERED`` plugin's AEOS-version
        compatibility and confirm its ``target_name`` is an enabled
        entry in the registry its ``extension_type`` points at.

        Raises:
            UnknownPluginRecordError: ``load()`` has not been called
                for ``plugin_name`` yet.
            InvalidPluginStateTransitionError: the record is not
                currently in ``DISCOVERED`` state.
            PluginVersionIncompatibleError: ``CURRENT_AEOS_VERSION``
                falls outside the plugin's declared
                ``[min_aeos_version, max_aeos_version]`` range.
            PluginTargetNotFoundError: ``target_name`` has no enabled
                entry in the corresponding registry.
        """
        record = self._get_record(plugin_name)
        self._require_state(record, PluginLifecycleState.DISCOVERED, "validate")

        metadata = record.metadata
        if not self._is_version_compatible(metadata.min_aeos_version, metadata.max_aeos_version):
            self._observe_event(
                "plugin_validation_failed", plugin_name=plugin_name, reason="version_incompatible"
            )
            self._observe_transition(plugin_name, "validate", "error")
            raise PluginVersionIncompatibleError(
                plugin_name,
                CURRENT_AEOS_VERSION,
                metadata.min_aeos_version,
                metadata.max_aeos_version,
            )

        if not self._target_is_enabled(metadata.extension_type, metadata.target_name):
            self._observe_event(
                "plugin_validation_failed", plugin_name=plugin_name, reason="target_not_found"
            )
            self._observe_transition(plugin_name, "validate", "error")
            raise PluginTargetNotFoundError(
                plugin_name, metadata.extension_type.value, metadata.target_name
            )

        record.state = PluginLifecycleState.VALIDATED
        record.touch()

        logger.info("Plugin validated: plugin_name=%s", plugin_name)
        self._observe_event("plugin_validated", plugin_name=plugin_name)
        self._observe_transition(plugin_name, "validate", "success")
        return record

    def initialize(self, plugin_name: str) -> PluginRecord:
        """Transition a ``VALIDATED`` plugin to ``INITIALIZED`` --
        the point at which ``is_active()`` starts returning ``True``
        for it.

        Never calls ``Tool.execute()``, ``ToolFactory.create()``, or
        any ``ModelProvider`` adapter -- see ADR-0012 decision 5.

        Raises:
            UnknownPluginRecordError: ``load()`` has not been called
                for ``plugin_name`` yet.
            InvalidPluginStateTransitionError: the record is not
                currently in ``VALIDATED`` state.
        """
        record = self._get_record(plugin_name)
        self._require_state(record, PluginLifecycleState.VALIDATED, "initialize")

        record.state = PluginLifecycleState.INITIALIZED
        record.touch()

        logger.info("Plugin initialized: plugin_name=%s", plugin_name)
        self._observe_event("plugin_initialized", plugin_name=plugin_name)
        self._observe_transition(plugin_name, "initialize", "success")
        return record

    def unload(self, plugin_name: str) -> PluginRecord:
        """Transition an ``INITIALIZED`` plugin to ``UNLOADED``.

        Raises:
            UnknownPluginRecordError: ``load()`` has not been called
                for ``plugin_name`` yet.
            InvalidPluginStateTransitionError: the record is not
                currently in ``INITIALIZED`` state.
        """
        record = self._get_record(plugin_name)
        self._require_state(record, PluginLifecycleState.INITIALIZED, "unload")

        record.state = PluginLifecycleState.UNLOADED
        record.touch()

        logger.info("Plugin unloaded: plugin_name=%s", plugin_name)
        self._observe_event("plugin_unloaded", plugin_name=plugin_name)
        self._observe_transition(plugin_name, "unload", "success")
        return record

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #

    def get(self, plugin_name: str) -> PluginRecord:
        """Return the tracked ``PluginRecord`` for ``plugin_name``.

        Raises:
            UnknownPluginRecordError: ``load()`` has not been called
                for ``plugin_name`` yet.
        """
        return self._get_record(plugin_name)

    def list_plugins(self) -> list[PluginRecord]:
        """Return every tracked ``PluginRecord``, in load order."""
        return list(self._records.values())

    def is_active(self, plugin_name: str) -> bool:
        """Return whether ``plugin_name`` is currently ``INITIALIZED``.

        Never raises -- returns ``False`` for a plugin that has not
        been loaded at all, mirroring ``ToolRegistry.is_enabled()``'s
        "yes/no answer without exception handling" shape.
        """
        record = self._records.get(plugin_name)
        return record is not None and record.state == PluginLifecycleState.INITIALIZED

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get_record(self, plugin_name: str) -> PluginRecord:
        try:
            return self._records[plugin_name]
        except KeyError as exc:
            raise UnknownPluginRecordError(plugin_name) from exc

    def _require_state(
        self, record: PluginRecord, expected: PluginLifecycleState, action: str
    ) -> None:
        if record.state != expected:
            self._observe_transition(record.plugin_name, action, "error")
            raise InvalidPluginStateTransitionError(
                record.plugin_name, action, expected.value, record.state.value
            )

    def _is_version_compatible(self, minimum: str, maximum: str | None) -> bool:
        current = parse_version(CURRENT_AEOS_VERSION)
        if current < parse_version(minimum):
            return False
        if maximum is not None and current > parse_version(maximum):
            return False
        return True

    def _target_is_enabled(self, extension_type: PluginExtensionType, target_name: str) -> bool:
        if extension_type == PluginExtensionType.TOOL:
            return self._tool_registry.is_enabled(target_name)
        return self._provider_registry.is_enabled(target_name)
