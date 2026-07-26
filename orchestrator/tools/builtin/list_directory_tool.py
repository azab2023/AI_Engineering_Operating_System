"""
orchestrator.tools.builtin.list_directory_tool
==================================================

``ListDirectoryTool``: the ``Tool`` implementation for ``tool_type:
list_directory`` -- lists the immediate entries of one directory on
disk.

Read-only, non-recursive, no shell/subprocess involvement. Path
sandboxing / permission enforcement is out of scope for Phase-09 (see
ADR-0007 Follow-up; planned for Phase-12 Security & Permissions).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from orchestrator.exceptions import ToolExecutionError
from orchestrator.logging_setup import get_logger
from orchestrator.tools.models import ToolDefinition, ToolResult

logger = get_logger("tools.builtin.list_directory_tool")


class ListDirectoryTool:
    """``Tool`` implementation that lists one directory's entries."""

    def __init__(self, definition: ToolDefinition):
        self._tool_name = definition.tool_name

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = Path(str(arguments["path"]))
        started = time.monotonic()

        if not path.exists():
            raise ToolExecutionError(self._tool_name, f"Path does not exist: {path}")
        if not path.is_dir():
            raise ToolExecutionError(self._tool_name, f"Path is not a directory: {path}")

        try:
            entries = sorted(entry.name for entry in path.iterdir())
        except OSError as exc:
            raise ToolExecutionError(
                self._tool_name, f"Could not list directory {path}: {exc}"
            ) from exc

        duration = time.monotonic() - started
        output = "\n".join(entries)
        logger.info(
            "list_directory succeeded: path=%s entries=%d duration=%.4fs",
            path,
            len(entries),
            duration,
        )
        return ToolResult(tool_name=self._tool_name, output=output, duration_seconds=duration)
