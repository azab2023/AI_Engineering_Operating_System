"""
orchestrator.tools.builtin.read_file_tool
=============================================

``ReadFileTool``: the ``Tool`` implementation for ``tool_type:
read_file`` -- reads the full text contents of one file on disk.

Read-only, single-file, no shell/subprocess involvement. Path
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

logger = get_logger("tools.builtin.read_file_tool")


class ReadFileTool:
    """``Tool`` implementation that reads one file's text contents."""

    def __init__(self, definition: ToolDefinition):
        self._tool_name = definition.tool_name

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = Path(str(arguments["path"]))
        started = time.monotonic()

        if not path.exists():
            raise ToolExecutionError(self._tool_name, f"Path does not exist: {path}")
        if not path.is_file():
            raise ToolExecutionError(self._tool_name, f"Path is not a file: {path}")

        try:
            output = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ToolExecutionError(self._tool_name, f"Could not read file {path}: {exc}") from exc

        duration = time.monotonic() - started
        logger.info("read_file succeeded: path=%s duration=%.4fs", path, duration)
        return ToolResult(tool_name=self._tool_name, output=output, duration_seconds=duration)
