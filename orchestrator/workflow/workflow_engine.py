"""
orchestrator.workflow.workflow_engine
========================================

``WorkflowEngine``: the Phase-11 Workflow Engine's sole Facade. Composes
three already-existing, unmodified components -- ``Orchestrator`` +
``ExecutionEngine`` (``agent_task`` steps) and ``ToolExecutor``
(``tool_call`` steps) -- into a linear, config-driven sequence, closing
the "no caller yet" loop ADR-0007 decision 6 and ADR-0008 decision 7
both left open for ``ToolExecutor``.

Scope note: this module does not modify ``AgentTask``, ``Orchestrator``,
``ExecutionEngine``, or ``ToolExecutor`` in any way -- it only calls
their existing public methods, exactly as any other caller would. See
ADR-0009 decision 3.

Human-in-the-loop note: an ``agent_task`` step's ``AgentExecution``
only ever reaches ``AWAITING_APPROVAL`` via ``ExecutionEngine.execute()``
(never ``COMPLETED`` -- that requires a separate, human-driven
``Orchestrator.approve()`` call). A ``WorkflowRun`` therefore pauses at
``AWAITING_APPROVAL`` whenever it hits such a step, and only advances
past it once ``resume()`` observes that the pending execution has
actually been approved. See ADR-0009 decision 4.
"""

from __future__ import annotations

from orchestrator.core import Orchestrator
from orchestrator.exceptions import (
    InvalidWorkflowStateTransitionError,
    ToolError,
    WorkflowStepNotApprovedError,
)
from orchestrator.execution.engine import ExecutionEngine
from orchestrator.logging_setup import get_logger
from orchestrator.models import AgentTask, ExecutionState
from orchestrator.tools.tool_executor import ToolExecutor
from orchestrator.workflow.models import StepType, WorkflowRun, WorkflowRunState, WorkflowStep
from orchestrator.workflow.repository import InMemoryWorkflowRunRepository, WorkflowRunRepository
from orchestrator.workflow.workflow_registry import WorkflowRegistry

logger = get_logger("workflow.workflow_engine")


class WorkflowEngine:
    """Drives a ``WorkflowRun`` from ``PENDING`` through to a recorded
    final outcome (``COMPLETED`` / ``FAILED``), pausing at
    ``AWAITING_APPROVAL`` for each ``agent_task`` step in between.

    Args:
        orchestrator: used to submit and route ``agent_task`` steps and
            to check whether a paused step's execution has been
            approved yet.
        execution_engine: used to actually invoke ``agent_task`` steps.
        tool_executor: used to run ``tool_call`` steps.
        registry: source of validated ``WorkflowDefinition`` lookups.
            Defaults to a ``WorkflowRegistry`` loaded from the default
            ``config/workflows.yaml`` path.
        repository: where ``WorkflowRun`` records are stored. Defaults
            to ``InMemoryWorkflowRunRepository()``.
    """

    def __init__(
        self,
        orchestrator: Orchestrator,
        execution_engine: ExecutionEngine,
        tool_executor: ToolExecutor | None = None,
        registry: WorkflowRegistry | None = None,
        repository: WorkflowRunRepository | None = None,
    ):
        self._orchestrator = orchestrator
        self._execution_engine = execution_engine
        self._tool_executor = tool_executor or ToolExecutor()
        self._registry = registry or WorkflowRegistry()
        self._repository = repository or InMemoryWorkflowRunRepository()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def start(self, workflow_id: str) -> WorkflowRun:
        """Look up ``workflow_id``, create a new ``WorkflowRun``
        (``PENDING``), and immediately begin advancing it.

        Raises:
            WorkflowNotFoundError: no entry exists for ``workflow_id``.
        """
        definition = self._registry.get_definition(workflow_id)
        run = WorkflowRun(workflow_id=workflow_id, state=WorkflowRunState.PENDING)
        self._repository.add(run)
        logger.info("Workflow run started: workflow_id=%s run_id=%s", workflow_id, run.run_id)

        run.state = WorkflowRunState.RUNNING
        run.touch()
        self._repository.update(run)

        return self._advance(run, definition)

    def resume(self, run_id: str) -> WorkflowRun:
        """Continue a run paused at ``AWAITING_APPROVAL`` past its
        current ``agent_task`` step, once that step's ``AgentExecution``
        has been approved.

        Raises:
            UnknownWorkflowRunError: no run exists for ``run_id``.
            InvalidWorkflowStateTransitionError: ``run`` is not
                currently ``AWAITING_APPROVAL``.
            WorkflowStepNotApprovedError: the pending execution has not
                yet reached ``COMPLETED`` (i.e. has not been approved).
        """
        run = self._repository.get(run_id)
        if run.state != WorkflowRunState.AWAITING_APPROVAL:
            raise InvalidWorkflowStateTransitionError(
                run_id,
                action="resume",
                expected_state=WorkflowRunState.AWAITING_APPROVAL.value,
                actual_state=run.state.value,
            )

        assert run.pending_execution_id is not None, (
            "AWAITING_APPROVAL run must have a pending_execution_id"
        )
        execution = self._orchestrator.track(run.pending_execution_id)
        if execution.state != ExecutionState.COMPLETED:
            raise WorkflowStepNotApprovedError(
                run_id, run.pending_execution_id, execution.state.value
            )

        definition = self._registry.get_definition(run.workflow_id)
        current_step = definition.step_at(run.current_step_index)
        run.context[current_step.step_id] = execution.result or ""
        run.pending_execution_id = None
        run.current_step_index += 1
        run.state = WorkflowRunState.RUNNING
        run.touch()
        self._repository.update(run)
        logger.info("Workflow run resumed: run_id=%s", run_id)

        return self._advance(run, definition)

    def get_run(self, run_id: str) -> WorkflowRun:
        """Look up the current state of a run by id."""
        return self._repository.get(run_id)

    def list_runs(self, state: WorkflowRunState | None = None) -> list[WorkflowRun]:
        return self._repository.list(state)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _advance(self, run: WorkflowRun, definition) -> WorkflowRun:  # noqa: ANN001
        """Run steps starting at ``run.current_step_index`` until the run
        pauses (``AWAITING_APPROVAL``), fails (``FAILED``), or completes
        (``COMPLETED``)."""
        while run.current_step_index < len(definition):
            step = definition.step_at(run.current_step_index)

            if step.step_type == StepType.TOOL_CALL:
                if not self._run_tool_step(run, step):
                    return run
                run.current_step_index += 1
                run.touch()
                self._repository.update(run)
                continue

            # StepType.AGENT_TASK
            paused = self._run_agent_task_step(run, step)
            if paused:
                return run
            if run.state == WorkflowRunState.FAILED:
                return run
            run.current_step_index += 1
            run.touch()
            self._repository.update(run)

        run.state = WorkflowRunState.COMPLETED
        run.touch()
        self._repository.update(run)
        logger.info("Workflow run completed: run_id=%s", run.run_id)
        return run

    def _run_tool_step(self, run: WorkflowRun, step: WorkflowStep) -> bool:
        """Run one ``tool_call`` step inline. Returns ``True`` on success
        (caller should advance to the next step), ``False`` if the run
        was just marked ``FAILED`` (caller should stop)."""
        try:
            result = self._tool_executor.execute(step.tool_name, step.tool_arguments)
        except ToolError as exc:
            run.state = WorkflowRunState.FAILED
            run.error = str(exc)
            run.touch()
            self._repository.update(run)
            logger.warning(
                "Workflow run failed: run_id=%s step_id=%s error=%s",
                run.run_id,
                step.step_id,
                exc,
            )
            return False

        run.context[step.step_id] = result.output
        return True

    def _run_agent_task_step(self, run: WorkflowRun, step: WorkflowStep) -> bool:
        """Run one ``agent_task`` step. Returns ``True`` if the run just
        paused at ``AWAITING_APPROVAL`` (caller should stop), ``False``
        otherwise (either the step failed, marking the run ``FAILED``,
        or -- not expected in practice -- some other terminal state was
        reached)."""
        task = AgentTask(
            task_type=step.task_type,
            description=step.description,
            required_capabilities=step.required_capabilities,
            prompt_id=step.prompt_id,
            prompt_variables=step.prompt_variables,
        )
        execution = self._orchestrator.submit_task(task)
        execution = self._execution_engine.execute(execution)

        if execution.state == ExecutionState.AWAITING_APPROVAL:
            run.pending_execution_id = execution.execution_id
            run.state = WorkflowRunState.AWAITING_APPROVAL
            run.touch()
            self._repository.update(run)
            logger.info(
                "Workflow run awaiting approval: run_id=%s step_id=%s execution_id=%s",
                run.run_id,
                step.step_id,
                execution.execution_id,
            )
            return True

        # FAILED (routing failure or exhausted retries) -- see ADR-0009
        # decision 6: no workflow-level retry, no skip.
        run.state = WorkflowRunState.FAILED
        run.error = execution.error or "agent task step failed"
        run.touch()
        self._repository.update(run)
        logger.warning(
            "Workflow run failed: run_id=%s step_id=%s error=%s",
            run.run_id,
            step.step_id,
            run.error,
        )
        return False
