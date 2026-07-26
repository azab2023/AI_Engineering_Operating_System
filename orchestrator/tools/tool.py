"""
orchestrator.tools.tool
==========================

Defines ``Tool``, the Port (Strategy/Protocol pattern) that a built-in
tool implementation must conform to.

This mirrors ``ModelProvider`` (``orchestrator.providers.provider``,
Phase-07) one layer over: where ``ModelProvider`` decouples
``HttpAgentInvoker`` from *which* upstream API it calls, ``Tool``
decouples ``ToolExecutor`` from *which* concrete tool it runs.
``ToolExecutor`` (Task 9.4) depends only on this Protocol -- never on a
concrete implementation class -- so adding a new built-in tool never
requires modifying ``ToolExecutor``. See ADR-0007 decision 4.
"""

from __future__ import annotations

from typing import Any, Protocol

from orchestrator.tools.models import ToolResult


class Tool(Protocol):
    """Port: something that can turn one validated set of arguments into
    one ``ToolResult`` by performing a single, self-contained, local
    operation.

    A conforming implementation owns everything specific to itself --
    how it interprets its arguments and what "running" means. Callers
    (``ToolExecutor``) know none of that; they only call ``execute()``
    after validating ``arguments`` against the tool's declared
    ``ToolDefinition.parameters``.
    """

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Run this tool against the given, already-validated
        ``arguments`` and return its result.

        Raises:
            ToolExecutionError: the operation could not be completed
                (e.g. a referenced file does not exist). Never raised
                for a missing/unknown/mistyped argument -- that
                validation happens in ``ToolExecutor`` before
                ``execute()`` is ever called.
        """
        ...
