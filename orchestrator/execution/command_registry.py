"""
orchestrator.execution.command_registry
==========================================

Loads and validates ``config/agent_commands.yaml`` and exposes typed
lookup of each agent's CLI invocation command.

Why a separate file from ``config/agent_registry.yaml`` instead of adding
a ``command`` field there: ``AgentRegistry`` (Phase-04) is orchestration
metadata used for *selection*; it has no reason to know how an agent is
actually invoked, and giving it that knowledge would couple selection to
execution concerns the same way ADR-0002 already rejected once (see
"No execution backend in this phase" there). See ADR-0004 for the full
rationale.

Validation philosophy matches ``orchestrator.registry``: fail loudly and
specifically rather than falling back to a default command silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from orchestrator.exceptions import AgentCommandNotConfiguredError, AgentCommandRegistryError
from orchestrator.execution.models import AgentCommand
from orchestrator.logging_setup import get_logger

logger = get_logger("execution.command_registry")

_REQUIRED_COMMAND_FIELDS = {"command", "timeout_seconds"}
_PLACEHOLDER = "{task_description}"

DEFAULT_COMMANDS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "agent_commands.yaml"
)


class AgentCommandRegistry:
    """In-memory, validated view of ``config/agent_commands.yaml``."""

    def __init__(self, registry_path: str | Path = DEFAULT_COMMANDS_PATH):
        self._registry_path = Path(registry_path)
        self._commands: dict[str, AgentCommand] = {}
        self._load()

    def _load(self) -> None:
        if not self._registry_path.exists():
            raise AgentCommandRegistryError(f"Agent command file not found: {self._registry_path}")

        try:
            raw_text = self._registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise AgentCommandRegistryError(
                f"Could not read agent command file: {self._registry_path}"
            ) from exc

        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise AgentCommandRegistryError(
                f"Agent command file is not valid YAML: {self._registry_path}\n{exc}"
            ) from exc

        if not isinstance(data, dict) or "commands" not in data:
            raise AgentCommandRegistryError(
                "Agent command file must be a mapping with a top-level 'commands' key"
            )

        commands_data = data["commands"]
        if not isinstance(commands_data, dict) or not commands_data:
            raise AgentCommandRegistryError(
                "Agent command file 'commands' key must be a non-empty mapping"
            )

        for agent_name, entry in commands_data.items():
            self._commands[agent_name] = self._parse_command(agent_name, entry)

        logger.info(
            "Loaded agent command registry: %d agent(s) from %s",
            len(self._commands),
            self._registry_path,
        )

    def _parse_command(self, agent_name: str, entry: Any) -> AgentCommand:
        if not isinstance(entry, dict):
            raise AgentCommandRegistryError(
                f"Agent command entry for {agent_name!r} must be a mapping, "
                f"got {type(entry).__name__}"
            )

        missing = _REQUIRED_COMMAND_FIELDS - entry.keys()
        if missing:
            raise AgentCommandRegistryError(
                f"Agent command entry for {agent_name!r} is missing required "
                f"field(s): {sorted(missing)}"
            )

        raw_command = entry["command"]
        if (
            not isinstance(raw_command, list)
            or not raw_command
            or not all(isinstance(token, str) for token in raw_command)
        ):
            raise AgentCommandRegistryError(
                f"Agent command entry for {agent_name!r}: 'command' must be a "
                f"non-empty list of strings"
            )
        if _PLACEHOLDER not in raw_command:
            raise AgentCommandRegistryError(
                f"Agent command entry for {agent_name!r}: 'command' must contain "
                f"the {_PLACEHOLDER!r} placeholder exactly once"
            )

        timeout_seconds = entry["timeout_seconds"]
        if not isinstance(timeout_seconds, int | float) or timeout_seconds <= 0:
            raise AgentCommandRegistryError(
                f"Agent command entry for {agent_name!r}: 'timeout_seconds' must "
                f"be a positive number"
            )

        return AgentCommand(command=tuple(raw_command), timeout_seconds=float(timeout_seconds))

    def get_command(self, agent_name: str) -> AgentCommand:
        try:
            return self._commands[agent_name]
        except KeyError as exc:
            raise AgentCommandNotConfiguredError(agent_name) from exc

    def __len__(self) -> int:
        return len(self._commands)

    def __contains__(self, agent_name: str) -> bool:
        return agent_name in self._commands
