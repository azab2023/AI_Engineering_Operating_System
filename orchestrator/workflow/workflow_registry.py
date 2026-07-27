"""
orchestrator.workflow.workflow_registry
==========================================

Loads and validates ``config/workflows.yaml`` and exposes typed lookup
of each workflow's definition.

Responsibility boundary (mirrors ``orchestrator.tools.tool_registry.
ToolRegistry``, ADR-0007 decision 3, itself mirroring ADR-0005 decision
3 for ``ModelProviderRegistry``): this module is responsible for
**configuration loading, validation, and lookup only**. It never runs a
step and never instantiates ``Orchestrator``/``ExecutionEngine``/
``ToolExecutor`` -- that composition is ``WorkflowEngine``'s job (see
ADR-0009 decision 7), so this registry's behavior never needs to change
when a new workflow is added to config.

Validation philosophy matches every prior registry in this project:
fail loudly and specifically rather than falling back to a default
value silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from orchestrator.exceptions import WorkflowNotFoundError, WorkflowRegistryError
from orchestrator.logging_setup import get_logger
from orchestrator.workflow.models import StepType, WorkflowDefinition, WorkflowStep

logger = get_logger("workflow.workflow_registry")

_REQUIRED_WORKFLOW_FIELDS = {"steps"}
_REQUIRED_STEP_FIELDS = {"step_id", "step_type"}
_VALID_STEP_TYPES = {member.value for member in StepType}

DEFAULT_WORKFLOWS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "workflows.yaml"


class WorkflowRegistry:
    """In-memory, validated view of ``config/workflows.yaml``.

    Configuration loading, validation, and per-workflow lookup only --
    see the module docstring above.
    """

    def __init__(self, registry_path: str | Path = DEFAULT_WORKFLOWS_PATH):
        self._registry_path = Path(registry_path)
        self._definitions: dict[str, WorkflowDefinition] = {}
        self._load()

    def _load(self) -> None:
        if not self._registry_path.exists():
            raise WorkflowRegistryError(f"Workflow file not found: {self._registry_path}")

        try:
            raw_text = self._registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WorkflowRegistryError(
                f"Could not read workflow file: {self._registry_path}"
            ) from exc

        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise WorkflowRegistryError(
                f"Workflow file is not valid YAML: {self._registry_path}\n{exc}"
            ) from exc

        if not isinstance(data, dict) or "workflows" not in data:
            raise WorkflowRegistryError(
                "Workflow file must be a mapping with a top-level 'workflows' key"
            )

        workflows_data = data["workflows"]
        if not isinstance(workflows_data, dict) or not workflows_data:
            raise WorkflowRegistryError("Workflow file 'workflows' key must be a non-empty mapping")

        for workflow_id, entry in workflows_data.items():
            self._definitions[workflow_id] = self._parse_entry(workflow_id, entry)

        logger.info(
            "Loaded workflow registry: %d workflow(s) from %s",
            len(self._definitions),
            self._registry_path,
        )

    def _parse_entry(self, workflow_id: str, entry: Any) -> WorkflowDefinition:
        if not isinstance(entry, dict):
            raise WorkflowRegistryError(
                f"Workflow entry for {workflow_id!r} must be a mapping, got {type(entry).__name__}"
            )

        missing = _REQUIRED_WORKFLOW_FIELDS - entry.keys()
        if missing:
            raise WorkflowRegistryError(
                f"Workflow entry for {workflow_id!r} is missing required "
                f"field(s): {sorted(missing)}"
            )

        description = entry.get("description", "")
        if not isinstance(description, str):
            raise WorkflowRegistryError(
                f"Workflow entry for {workflow_id!r}: 'description' must be a string"
            )

        raw_steps = entry["steps"]
        if not isinstance(raw_steps, list) or not raw_steps:
            raise WorkflowRegistryError(
                f"Workflow entry for {workflow_id!r}: 'steps' must be a non-empty list"
            )

        steps = tuple(self._parse_step(workflow_id, raw_step) for raw_step in raw_steps)

        try:
            return WorkflowDefinition(workflow_id=workflow_id, steps=steps, description=description)
        except ValueError as exc:
            raise WorkflowRegistryError(f"Workflow {workflow_id!r}: {exc}") from exc

    def _parse_step(self, workflow_id: str, entry: Any) -> WorkflowStep:
        if not isinstance(entry, dict):
            raise WorkflowRegistryError(
                f"Workflow {workflow_id!r}: each step must be a mapping, got {type(entry).__name__}"
            )

        missing = _REQUIRED_STEP_FIELDS - entry.keys()
        if missing:
            raise WorkflowRegistryError(
                f"Workflow {workflow_id!r}: step entry is missing required "
                f"field(s): {sorted(missing)}"
            )

        step_id = entry["step_id"]
        if not isinstance(step_id, str) or not step_id.strip():
            raise WorkflowRegistryError(
                f"Workflow {workflow_id!r}: step 'step_id' must be a non-empty string"
            )

        step_type_raw = entry["step_type"]
        if step_type_raw not in _VALID_STEP_TYPES:
            raise WorkflowRegistryError(
                f"Workflow {workflow_id!r}, step {step_id!r}: 'step_type' must be "
                f"one of {sorted(_VALID_STEP_TYPES)}, got {step_type_raw!r}"
            )
        step_type = StepType(step_type_raw)

        required_capabilities = entry.get("required_capabilities", [])
        if not isinstance(required_capabilities, list):
            raise WorkflowRegistryError(
                f"Workflow {workflow_id!r}, step {step_id!r}: "
                "'required_capabilities' must be a list"
            )

        prompt_variables = entry.get("prompt_variables", {})
        if not isinstance(prompt_variables, dict):
            raise WorkflowRegistryError(
                f"Workflow {workflow_id!r}, step {step_id!r}: 'prompt_variables' must be a mapping"
            )

        tool_arguments = entry.get("tool_arguments", {})
        if not isinstance(tool_arguments, dict):
            raise WorkflowRegistryError(
                f"Workflow {workflow_id!r}, step {step_id!r}: 'tool_arguments' must be a mapping"
            )

        agent_name = entry.get("agent_name")
        if agent_name is not None and not isinstance(agent_name, str):
            raise WorkflowRegistryError(
                f"Workflow {workflow_id!r}, step {step_id!r}: 'agent_name' must be a string"
            )

        try:
            return WorkflowStep(
                step_id=step_id,
                step_type=step_type,
                task_type=entry.get("task_type"),
                description=entry.get("description"),
                required_capabilities=tuple(required_capabilities),
                prompt_id=entry.get("prompt_id"),
                prompt_variables=dict(prompt_variables),
                tool_name=entry.get("tool_name"),
                tool_arguments=dict(tool_arguments),
                agent_name=agent_name,
            )
        except ValueError as exc:
            raise WorkflowRegistryError(f"Workflow {workflow_id!r}: {exc}") from exc

    def get_definition(self, workflow_id: str) -> WorkflowDefinition:
        """Return the validated ``WorkflowDefinition`` for ``workflow_id``.

        Raises:
            WorkflowNotFoundError: no entry exists for ``workflow_id``.
        """
        try:
            return self._definitions[workflow_id]
        except KeyError as exc:
            raise WorkflowNotFoundError(workflow_id) from exc

    def __len__(self) -> int:
        return len(self._definitions)

    def __contains__(self, workflow_id: str) -> bool:
        return workflow_id in self._definitions
