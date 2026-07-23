"""
orchestrator.models
=====================

Core data models for Phase-04 Agent Orchestration.

Design notes:
    - Plain dataclasses only (stdlib) to keep dependencies minimal, per
      AEOS Phase-04 constraints. No pydantic / ORM / external validation
      libraries are introduced.
    - Enums are used for closed sets of states/statuses instead of raw
      strings, to make invalid states unrepresentable where practical.
    - All models are intentionally simple data holders; behavior
      (selection, routing, state transitions) lives in registry.py /
      core.py, not on the models themselves. This keeps the "what an
      agent/task IS" separate from "what the orchestrator DOES with it".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class AgentStatus(str, Enum):
    """Lifecycle status of a registered agent."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    PLANNED = "planned"


class AgentPriority(str, Enum):
    """Relative priority used to break ties when multiple active agents
    are eligible for the same task. Mirrors the priority scale already
    used in config/agents.yaml (high/medium), with 'low' added for
    completeness."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ExecutionState(str, Enum):
    """State machine for an AgentExecution.

    PENDING -> ASSIGNED -> RUNNING -> (COMPLETED | FAILED | AWAITING_APPROVAL)

    AWAITING_APPROVAL exists to keep human-in-the-loop review a first-class,
    structural part of execution state (per docs/governance/contribution-
    guidelines.md: no publish/merge without human review), even though no
    approval workflow is implemented yet.
    """

    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class AgentCapability:
    """A single named capability an agent offers (e.g. 'code_generation')."""

    name: str
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("AgentCapability.name must be a non-empty string")


@dataclass(frozen=True)
class Agent:
    """A registered AI coding agent (Claude Code, Aider, Codex, Gemini, ...)."""

    name: str
    provider: str
    capabilities: tuple[AgentCapability, ...]
    supported_tasks: tuple[str, ...]
    config_reference: str
    status: AgentStatus
    priority: AgentPriority

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Agent.name must be a non-empty string")
        if not self.provider or not self.provider.strip():
            raise ValueError("Agent.provider must be a non-empty string")
        if not self.supported_tasks:
            raise ValueError(f"Agent {self.name!r} must declare at least one supported task")

    def has_capability(self, capability_name: str) -> bool:
        return any(c.name == capability_name for c in self.capabilities)

    def supports_task(self, task_type: str) -> bool:
        return task_type in self.supported_tasks

    def is_active(self) -> bool:
        return self.status == AgentStatus.ACTIVE


@dataclass(frozen=True)
class AgentTask:
    """A unit of work to be routed to a suitable agent."""

    task_type: str
    description: str
    required_capabilities: tuple[str, ...] = field(default_factory=tuple)
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.task_type or not self.task_type.strip():
            raise ValueError("AgentTask.task_type must be a non-empty string")


@dataclass
class AgentExecution:
    """Tracks the lifecycle of a task being routed to (and run by) an agent.

    Mutable by design (unlike the other models) because the orchestrator
    updates `state`, `assigned_agent`, `result`, and timestamps as the
    execution progresses.
    """

    task: AgentTask
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: ExecutionState = ExecutionState.PENDING
    assigned_agent: Agent | None = None
    result: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)
