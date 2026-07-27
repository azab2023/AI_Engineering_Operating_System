"""
orchestrator.security.authorizer
====================================

``ToolAuthorizer``: the sole, reusable authorization entry point
``ToolExecutor`` calls before running any tool. Combines the two
Phase-12 checks (ADR-0010) behind one method so ``ToolExecutor`` itself
never contains permission logic:

- **Path sandbox** (argument-level, always enforced): any argument
  named in a ``ToolDefinition``'s ``sandboxed_parameters`` must resolve
  within the configured ``PathSandboxPolicy``.
- **Agent read/write permission** (caller-level, enforced only when a
  caller identifies itself): if an ``agent_name`` is supplied, it must
  have a configured ``AgentPermission`` granting the tool's
  ``access_mode`` ("read" | "write").

A future filesystem-touching tool inherits both checks automatically
by declaring ``sandboxed_parameters`` / ``access_mode`` in its
``config/tools.yaml`` entry -- no change to this class, ``ToolExecutor``,
or the tool's own ``execute()`` is needed. See ADR-0010 decision 7.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.exceptions import (
    AgentPermissionError,
    PathPermissionError,
    UnknownAgentPermissionError,
)
from orchestrator.security.models import PermissionPolicy
from orchestrator.security.permission_registry import PermissionRegistry
from orchestrator.tools.models import ToolDefinition


class ToolAuthorizer:
    """Reusable, centralized authorization layer for ``ToolExecutor``.

    Args:
        policy: the ``PermissionPolicy`` to authorize against. Defaults
            to loading the default ``config/permissions.yaml`` via
            ``PermissionRegistry``.
    """

    def __init__(self, policy: PermissionPolicy | None = None):
        self._policy = policy or PermissionRegistry().policy()

    def authorize(
        self,
        definition: ToolDefinition,
        arguments: dict[str, Any],
        agent_name: str | None = None,
    ) -> None:
        """Raise if ``agent_name`` (when given) lacks the required
        access mode, or if any sandboxed argument resolves outside the
        configured path sandbox.

        Raises:
            UnknownAgentPermissionError: ``agent_name`` was given but
                has no configured ``AgentPermission``.
            AgentPermissionError: ``agent_name`` is known but not
                permitted ``definition.access_mode``.
            PathPermissionError: a sandboxed argument resolves outside
                the configured path sandbox.
        """
        self._authorize_agent(definition, agent_name)
        self._authorize_paths(definition, arguments)

    def _authorize_agent(self, definition: ToolDefinition, agent_name: str | None) -> None:
        if agent_name is None:
            # No caller identity supplied -- unchanged, pre-Phase-12
            # behavior for every call site that predates agent-level
            # permissions. See ADR-0010 decision 7 / Alternatives.
            return

        permission = self._policy.permission_for(agent_name)
        if permission is None:
            raise UnknownAgentPermissionError(agent_name)

        allowed = permission.can_write if definition.access_mode == "write" else permission.can_read
        if not allowed:
            raise AgentPermissionError(agent_name, definition.tool_name, definition.access_mode)

    def _authorize_paths(self, definition: ToolDefinition, arguments: dict[str, Any]) -> None:
        for name in definition.sandboxed_parameters:
            if name not in arguments:
                continue
            candidate = Path(str(arguments[name]))
            if not self._policy.path_sandbox.is_allowed(candidate):
                raise PathPermissionError(definition.tool_name, name, candidate)
