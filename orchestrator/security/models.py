"""
orchestrator.security.models
================================

Data models for Phase-12 (Security & Permissions, ADR-0010).

Design notes:
    - Plain, frozen dataclasses only, matching the convention already
      established in ``orchestrator.models`` (Phase-04),
      ``orchestrator.tools.models`` (Phase-09), and
      ``orchestrator.workflow.models`` (Phase-11) -- no pydantic / ORM
      / external validation libraries.
    - ``PathSandboxPolicy`` and ``AgentPermission`` are the validated,
      in-memory representation of ``config/permissions.yaml``'s two
      sections, produced by ``PermissionRegistry`` (see
      ``permission_registry.py``). ``PermissionPolicy`` composes both
      into the single object ``ToolAuthorizer`` (``authorizer.py``)
      consults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PathSandboxPolicy:
    """The set of directories a sandboxed tool argument may resolve
    within.

    Attributes:
        allowed_roots: absolute, already-resolved directories. Must be
            non-empty -- a policy with no allowed roots would deny
            every path, which is almost certainly a configuration
            mistake rather than an intended lockdown; see
            ``PermissionRegistry`` for how this is populated.
    """

    allowed_roots: tuple[Path, ...]

    def __post_init__(self) -> None:
        if not self.allowed_roots:
            raise ValueError("PathSandboxPolicy.allowed_roots must be non-empty")
        for root in self.allowed_roots:
            if not root.is_absolute():
                raise ValueError(f"PathSandboxPolicy allowed root must be an absolute path: {root}")

    def is_allowed(self, path: Path) -> bool:
        """Return whether ``path`` resolves to, or beneath, one of
        ``allowed_roots``. Follows symlinks (``Path.resolve()``)."""
        resolved = path.resolve()
        return any(resolved == root or resolved.is_relative_to(root) for root in self.allowed_roots)


@dataclass(frozen=True)
class AgentPermission:
    """One agent's read/write authorization, from
    ``config/permissions.yaml``'s ``agent_permissions`` section.

    Attributes:
        agent_name: matches the ``name`` used in ``config/agents.yaml``
            / ``config/agent_registry.yaml`` (e.g. ``"claude_code"``).
        can_read: whether this agent may call a tool whose
            ``ToolDefinition.access_mode == "read"``.
        can_write: whether this agent may call a tool whose
            ``ToolDefinition.access_mode == "write"``.
    """

    agent_name: str
    can_read: bool
    can_write: bool

    def __post_init__(self) -> None:
        if not self.agent_name or not self.agent_name.strip():
            raise ValueError("AgentPermission.agent_name must be a non-empty string")


@dataclass(frozen=True)
class PermissionPolicy:
    """The full, validated view of ``config/permissions.yaml``:
    ``path_sandbox`` (always present) plus ``agent_permissions``
    (may be empty -- see ``PermissionRegistry``).

    Attributes:
        path_sandbox: the path-sandbox policy, always populated.
        agent_permissions: agent_name -> ``AgentPermission``. An agent
            name absent from this mapping is treated by
            ``ToolAuthorizer`` as unrecognized (denied), not
            permissively defaulted.
    """

    path_sandbox: PathSandboxPolicy
    agent_permissions: dict[str, AgentPermission] = field(default_factory=dict)

    def permission_for(self, agent_name: str) -> AgentPermission | None:
        return self.agent_permissions.get(agent_name)
