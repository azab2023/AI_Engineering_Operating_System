"""
orchestrator.security.permission_registry
=============================================

Loads and validates ``config/permissions.yaml`` and exposes the
resulting ``PermissionPolicy``.

Responsibility boundary (mirrors ``orchestrator.tools.tool_registry.
ToolRegistry``, ADR-0007 decision 3): this module is responsible for
**configuration loading, validation, and exposure only**. It never
performs an authorization check itself -- that is
``orchestrator.security.authorizer.ToolAuthorizer``'s job, so this
registry's behavior never needs to change when the authorization logic
does.

Validation philosophy matches every prior registry in this project:
fail loudly and specifically rather than falling back to a default
value silently.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import yaml

from orchestrator.exceptions import PermissionRegistryError
from orchestrator.logging_setup import get_logger
from orchestrator.security.models import AgentPermission, PathSandboxPolicy, PermissionPolicy

logger = get_logger("security.permission_registry")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PERMISSIONS_PATH = PROJECT_ROOT / "config" / "permissions.yaml"

_REQUIRED_PATH_SANDBOX_FIELDS = {"allowed_roots"}
_REQUIRED_AGENT_PERMISSION_FIELDS = {"read", "write"}


class PermissionRegistry:
    """In-memory, validated view of ``config/permissions.yaml``.

    Configuration loading and validation only -- see the module
    docstring above.
    """

    def __init__(self, registry_path: str | Path = DEFAULT_PERMISSIONS_PATH):
        self._registry_path = Path(registry_path)
        self._policy = self._load()

    def _load(self) -> PermissionPolicy:
        if not self._registry_path.exists():
            raise PermissionRegistryError(f"Permission file not found: {self._registry_path}")

        try:
            raw_text = self._registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PermissionRegistryError(
                f"Could not read permission file: {self._registry_path}"
            ) from exc

        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise PermissionRegistryError(
                f"Permission file is not valid YAML: {self._registry_path}\n{exc}"
            ) from exc

        if not isinstance(data, dict) or "path_sandbox" not in data:
            raise PermissionRegistryError(
                "Permission file must be a mapping with a top-level 'path_sandbox' key"
            )

        path_sandbox = self._parse_path_sandbox(data["path_sandbox"])
        agent_permissions = self._parse_agent_permissions(data.get("agent_permissions", {}))

        logger.info(
            "Loaded permission registry: %d allowed root(s), %d agent(s) from %s",
            len(path_sandbox.allowed_roots),
            len(agent_permissions),
            self._registry_path,
        )
        return PermissionPolicy(path_sandbox=path_sandbox, agent_permissions=agent_permissions)

    def _parse_path_sandbox(self, entry: Any) -> PathSandboxPolicy:
        if not isinstance(entry, dict):
            raise PermissionRegistryError(
                f"'path_sandbox' must be a mapping, got {type(entry).__name__}"
            )

        missing = _REQUIRED_PATH_SANDBOX_FIELDS - entry.keys()
        if missing:
            raise PermissionRegistryError(
                f"'path_sandbox' is missing required field(s): {sorted(missing)}"
            )

        raw_roots = entry["allowed_roots"]
        if not isinstance(raw_roots, list) or not raw_roots:
            raise PermissionRegistryError("'path_sandbox.allowed_roots' must be a non-empty list")

        roots: list[Path] = []
        for raw_root in raw_roots:
            if not isinstance(raw_root, str) or not raw_root.strip():
                raise PermissionRegistryError(
                    "'path_sandbox.allowed_roots' entries must be non-empty "
                    f"strings, got {raw_root!r}"
                )
            candidate = Path(raw_root)
            if candidate.is_absolute():
                resolved = candidate.resolve()
            else:
                resolved = (PROJECT_ROOT / candidate).resolve()
            roots.append(resolved)

        include_system_temp_dir = entry.get("include_system_temp_dir", False)
        if not isinstance(include_system_temp_dir, bool):
            raise PermissionRegistryError(
                "'path_sandbox.include_system_temp_dir' must be a boolean"
            )
        if include_system_temp_dir:
            roots.append(Path(tempfile.gettempdir()).resolve())

        try:
            return PathSandboxPolicy(allowed_roots=tuple(roots))
        except ValueError as exc:
            raise PermissionRegistryError(f"'path_sandbox': {exc}") from exc

    def _parse_agent_permissions(self, entry: Any) -> dict[str, AgentPermission]:
        if not isinstance(entry, dict):
            raise PermissionRegistryError(
                f"'agent_permissions' must be a mapping, got {type(entry).__name__}"
            )

        permissions: dict[str, AgentPermission] = {}
        for agent_name, raw_permission in entry.items():
            if not isinstance(raw_permission, dict):
                raise PermissionRegistryError(
                    f"'agent_permissions' entry for {agent_name!r} must be a mapping, "
                    f"got {type(raw_permission).__name__}"
                )

            missing = _REQUIRED_AGENT_PERMISSION_FIELDS - raw_permission.keys()
            if missing:
                raise PermissionRegistryError(
                    f"'agent_permissions' entry for {agent_name!r} is missing "
                    f"required field(s): {sorted(missing)}"
                )

            can_read = raw_permission["read"]
            can_write = raw_permission["write"]
            if not isinstance(can_read, bool) or not isinstance(can_write, bool):
                raise PermissionRegistryError(
                    f"'agent_permissions' entry for {agent_name!r}: 'read'/'write' must be booleans"
                )

            try:
                permissions[agent_name] = AgentPermission(
                    agent_name=agent_name, can_read=can_read, can_write=can_write
                )
            except ValueError as exc:
                raise PermissionRegistryError(f"'agent_permissions' entry: {exc}") from exc

        return permissions

    def policy(self) -> PermissionPolicy:
        return self._policy
