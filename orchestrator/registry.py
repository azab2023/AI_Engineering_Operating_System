"""
orchestrator.registry
========================

Loads and validates the agent registry from config/agent_registry.yaml
and exposes typed query methods over it.

Why a new config/agent_registry.yaml instead of extending the existing
config/agents.yaml or config/models.yaml:
    Those two files predate Phase-04 and only carry (role, priority) and
    (provider, purpose) respectively -- neither has the fields this phase
    requires (capabilities, supported_tasks, config_reference, status).
    Extending either file's schema would be an undocumented breaking
    change to a file another phase/agent may already depend on. A new,
    additive file keeps this phase self-contained. See
    docs/architecture/decision-records/ADR-0002-agent-orchestration-layer.md.

Validation philosophy:
    Fail loudly and specifically. The prompt_registry.yaml incident (a
    duplicated YAML document silently overriding the first, with PyYAML
    raising no error) is the direct motivation for the strict schema
    checks below.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from orchestrator.exceptions import AgentRegistryError
from orchestrator.logging_setup import get_logger
from orchestrator.models import Agent, AgentCapability, AgentPriority, AgentStatus

logger = get_logger("registry")

_REQUIRED_AGENT_FIELDS = {
    "name",
    "provider",
    "capabilities",
    "supported_tasks",
    "config_reference",
    "status",
    "priority",
}

DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "agent_registry.yaml"
)


class AgentRegistry:
    """In-memory, validated view of the agent registry YAML file."""

    def __init__(self, registry_path: str | Path = DEFAULT_REGISTRY_PATH):
        self._registry_path = Path(registry_path)
        self._agents: dict[str, Agent] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Loading & validation
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if not self._registry_path.exists():
            raise AgentRegistryError(
                f"Agent registry file not found: {self._registry_path}"
            )

        try:
            raw_text = self._registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise AgentRegistryError(
                f"Could not read agent registry file: {self._registry_path}"
            ) from exc

        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise AgentRegistryError(
                f"Agent registry file is not valid YAML: {self._registry_path}\n{exc}"
            ) from exc

        if not isinstance(data, dict) or "agents" not in data:
            raise AgentRegistryError(
                "Agent registry must be a mapping with a top-level 'agents' key"
            )

        agents_data = data["agents"]
        if not isinstance(agents_data, list) or not agents_data:
            raise AgentRegistryError(
                "Agent registry 'agents' key must be a non-empty list"
            )

        seen_names: set[str] = set()
        for index, entry in enumerate(agents_data):
            agent = self._parse_agent(entry, index)
            if agent.name in seen_names:
                raise AgentRegistryError(
                    f"Duplicate agent name in registry: {agent.name!r}"
                )
            seen_names.add(agent.name)
            self._agents[agent.name] = agent

        logger.info(
            "Loaded agent registry: %d agent(s) from %s",
            len(self._agents),
            self._registry_path,
        )

    def _parse_agent(self, entry: Any, index: int) -> Agent:
        if not isinstance(entry, dict):
            raise AgentRegistryError(
                f"Agent registry entry at index {index} must be a mapping, got {type(entry).__name__}"
            )

        missing = _REQUIRED_AGENT_FIELDS - entry.keys()
        if missing:
            raise AgentRegistryError(
                f"Agent registry entry at index {index} is missing required "
                f"field(s): {sorted(missing)}"
            )

        raw_capabilities = entry["capabilities"]
        if not isinstance(raw_capabilities, list) or not raw_capabilities:
            raise AgentRegistryError(
                f"Agent {entry.get('name', '<unknown>')!r}: 'capabilities' must be a non-empty list"
            )

        capabilities: list[AgentCapability] = []
        for cap in raw_capabilities:
            if isinstance(cap, dict):
                cap_name = cap.get("name")
                cap_desc = cap.get("description", "")
            else:
                cap_name = cap
                cap_desc = ""
            if not cap_name or not isinstance(cap_name, str):
                raise AgentRegistryError(
                    f"Agent {entry.get('name')!r}: each capability needs a non-empty string 'name'"
                )
            capabilities.append(AgentCapability(name=cap_name, description=cap_desc or ""))

        raw_tasks = entry["supported_tasks"]
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise AgentRegistryError(
                f"Agent {entry.get('name')!r}: 'supported_tasks' must be a non-empty list"
            )

        raw_status = entry["status"]
        try:
            status = AgentStatus(raw_status)
        except ValueError as exc:
            raise AgentRegistryError(
                f"Agent {entry.get('name')!r}: invalid status {raw_status!r}. "
                f"Must be one of {[s.value for s in AgentStatus]}"
            ) from exc

        raw_priority = entry["priority"]
        try:
            priority = AgentPriority(raw_priority)
        except ValueError as exc:
            raise AgentRegistryError(
                f"Agent {entry.get('name')!r}: invalid priority {raw_priority!r}. "
                f"Must be one of {[p.value for p in AgentPriority]}"
            ) from exc

        try:
            return Agent(
                name=entry["name"],
                provider=entry["provider"],
                capabilities=tuple(capabilities),
                supported_tasks=tuple(raw_tasks),
                config_reference=entry["config_reference"],
                status=status,
                priority=priority,
            )
        except ValueError as exc:
            raise AgentRegistryError(f"Invalid agent definition at index {index}: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Query API
    # ------------------------------------------------------------------ #

    def get_agent(self, name: str) -> Agent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise AgentRegistryError(f"No agent registered with name {name!r}") from exc

    def list_agents(self, status: AgentStatus | None = None) -> list[Agent]:
        agents = list(self._agents.values())
        if status is not None:
            agents = [a for a in agents if a.status == status]
        return agents

    def find_by_capability(self, capability_name: str) -> list[Agent]:
        return [a for a in self._agents.values() if a.has_capability(capability_name)]

    def find_by_task(self, task_type: str) -> list[Agent]:
        return [a for a in self._agents.values() if a.supports_task(task_type)]

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: str) -> bool:
        return name in self._agents
