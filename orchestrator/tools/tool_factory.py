"""
orchestrator.tools.tool_factory
===================================

``ToolFactory``: resolves a ``ToolDefinition.tool_type`` string to a
concrete ``Tool`` instance.

This exists so ``ToolExecutor`` (Task 9.4) never has to know which
concrete tool classes exist -- it asks ``ToolFactory.create()`` for a
``Tool`` and only ever programs against the ``Tool`` Protocol from there
on. Resolution is a plain registration dict, not an
``if tool_type == "read_file": ...`` chain -- adding a new built-in tool
means adding one new class and one new dict entry here, never editing
existing entries or any conditional logic. Mirrors
``orchestrator.providers.provider_factory.ProviderFactory`` (Phase-07);
see ADR-0007 decision 4.
"""

from __future__ import annotations

from orchestrator.exceptions import UnsupportedToolTypeError
from orchestrator.tools.builtin.list_directory_tool import ListDirectoryTool
from orchestrator.tools.builtin.read_file_tool import ReadFileTool
from orchestrator.tools.models import ToolDefinition
from orchestrator.tools.tool import Tool


class ToolFactory:
    """Registration-dict-based resolver from ``tool_type`` to a ``Tool``
    instance. Stateless -- every method is a classmethod; there is
    nothing to construct an instance of this class for.
    """

    _IMPLEMENTATIONS: dict[str, type[Tool]] = {
        "read_file": ReadFileTool,
        "list_directory": ListDirectoryTool,
    }

    @classmethod
    def create(cls, definition: ToolDefinition) -> Tool:
        """Instantiate the ``Tool`` implementation registered for
        ``definition.tool_type``.

        Args:
            definition: the resolved, enabled ``ToolDefinition`` for one
                tool (typically from ``ToolRegistry.get_definition()``).

        Raises:
            UnsupportedToolTypeError: no implementation is registered
                for ``definition.tool_type``.
        """
        try:
            implementation_cls = cls._IMPLEMENTATIONS[definition.tool_type]
        except KeyError as exc:
            raise UnsupportedToolTypeError(definition.tool_type) from exc
        return implementation_cls(definition)
