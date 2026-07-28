"""
orchestrator.plugins
=======================

Phase-14 (ADR-0012) Plugin & Extension System.

A "plugin" here is a config-driven metadata record that activates or
deactivates an already-registered ``Tool`` (``config/tools.yaml``,
Phase-09) or ``ModelProvider`` (``config/model_providers.yaml``,
Phase-07) entry -- it never introduces a new execution path, never
calls ``Tool.execute()`` / ``ToolFactory.create()`` / any
``ModelProvider`` adapter, and therefore cannot bypass ``ToolAuthorizer``
(Phase-12). See ADR-0012 decision 5.

This package provides:
    - ``PluginMetadata`` / ``PluginRecord`` / ``PluginExtensionType`` /
      ``PluginLifecycleState`` (models.py)
    - ``PluginRegistry``, loading and validating ``config/plugins.yaml``
    - ``PluginManager``, the Facade for the four-stage lifecycle:
      load -> validate -> initialize -> unload
"""

from orchestrator.plugins.models import (
    CURRENT_AEOS_VERSION,
    PluginExtensionType,
    PluginLifecycleState,
    PluginMetadata,
    PluginRecord,
)
from orchestrator.plugins.plugin_manager import PluginManager
from orchestrator.plugins.plugin_registry import PluginRegistry

__all__ = [
    "CURRENT_AEOS_VERSION",
    "PluginExtensionType",
    "PluginLifecycleState",
    "PluginMetadata",
    "PluginRecord",
    "PluginRegistry",
    "PluginManager",
]
