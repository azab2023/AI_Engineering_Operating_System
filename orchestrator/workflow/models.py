"""
orchestrator.workflow.models
===============================

Core data models for Phase-11 Workflow Engine (ADR-0009).

Design notes (matching ``orchestrator.models``' own conventions):
    - Plain dataclasses only (stdlib), no pydantic / ORM.
    - ``WorkflowStep`` / ``WorkflowDefinition`` are frozen (immutable,
      config-derived), mirroring ``AgentTask``. ``WorkflowRun`` is
      mutable, mirroring ``AgentExecution`` -- the engine updates
      ``state``, ``current_step_index``, ``context``, and timestamps as
      a run progresses.
    - Enums are used for closed sets of states, matching
      ``ExecutionState`` / ``AgentStatus``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class StepType(str, Enum):
    """The two step kinds a ``WorkflowStep`` may be. See ADR-0009
    decision 2 for why exactly these two, and no more, in this phase."""

    AGENT_TASK = "agent_task"
    TOOL_CALL = "tool_call"


class WorkflowRunState(str, Enum):
    """State machine for a ``WorkflowRun``.

    PENDING -> RUNNING -> (AWAITING_APPROVAL -> RUNNING)* -> (COMPLETED | FAILED)

    Mirrors ``ExecutionState`` (Phase-04). A run reaches
    ``AWAITING_APPROVAL`` whenever the ``agent_task`` step currently
    executing produces an ``AgentExecution`` that is itself
    ``AWAITING_APPROVAL`` -- see ADR-0009 decision 4.
    """

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class WorkflowStep:
    """A single step within a ``WorkflowDefinition``.

    Exactly one of the two field groups below is populated, depending
    on ``step_type``:

    - ``AGENT_TASK``: ``task_type`` and ``description`` are required;
      ``required_capabilities``, ``prompt_id``, ``prompt_variables`` are
      optional. These are the same fields ``orchestrator.models.AgentTask``
      already has -- a step's ``agent_task`` fields exist only to
      construct an ``AgentTask``, not to redefine one.
    - ``TOOL_CALL``: ``tool_name`` is required; ``tool_arguments`` is
      optional.
    """

    step_id: str
    step_type: StepType

    # AGENT_TASK fields
    task_type: str | None = None
    description: str | None = None
    required_capabilities: tuple[str, ...] = field(default_factory=tuple)
    prompt_id: str | None = None
    prompt_variables: dict[str, str] = field(default_factory=dict)

    # TOOL_CALL fields
    tool_name: str | None = None
    tool_arguments: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.step_id or not self.step_id.strip():
            raise ValueError("WorkflowStep.step_id must be a non-empty string")

        if self.step_type == StepType.AGENT_TASK:
            if not self.task_type or not self.task_type.strip():
                raise ValueError(
                    f"WorkflowStep {self.step_id!r}: 'task_type' is required for "
                    "step_type=agent_task"
                )
            if not self.description or not self.description.strip():
                raise ValueError(
                    f"WorkflowStep {self.step_id!r}: 'description' is required for "
                    "step_type=agent_task"
                )
        elif self.step_type == StepType.TOOL_CALL:
            if not self.tool_name or not self.tool_name.strip():
                raise ValueError(
                    f"WorkflowStep {self.step_id!r}: 'tool_name' is required for "
                    "step_type=tool_call"
                )


@dataclass(frozen=True)
class WorkflowDefinition:
    """A named, ordered, linear sequence of ``WorkflowStep``\\ s, loaded
    from ``config/workflows.yaml`` by ``WorkflowRegistry``."""

    workflow_id: str
    steps: tuple[WorkflowStep, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.workflow_id or not self.workflow_id.strip():
            raise ValueError("WorkflowDefinition.workflow_id must be a non-empty string")
        if not self.steps:
            raise ValueError(
                f"WorkflowDefinition {self.workflow_id!r} must declare at least one step"
            )
        seen: set[str] = set()
        for step in self.steps:
            if step.step_id in seen:
                raise ValueError(
                    f"WorkflowDefinition {self.workflow_id!r}: duplicate step_id {step.step_id!r}"
                )
            seen.add(step.step_id)

    def step_at(self, index: int) -> WorkflowStep:
        return self.steps[index]

    def __len__(self) -> int:
        return len(self.steps)


@dataclass
class WorkflowRun:
    """Tracks the lifecycle of one execution of a ``WorkflowDefinition``.

    Mutable by design (unlike ``WorkflowStep``/``WorkflowDefinition``),
    matching ``AgentExecution``: ``WorkflowEngine`` updates ``state``,
    ``current_step_index``, ``context``, ``pending_execution_id``, and
    timestamps as the run progresses.
    """

    workflow_id: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: WorkflowRunState = WorkflowRunState.PENDING
    current_step_index: int = 0
    context: dict[str, str] = field(default_factory=dict)
    pending_execution_id: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)
