"""
orchestrator.exceptions
========================

Custom exception hierarchy for the orchestration layer.

Rationale: silent failures / permissive fallbacks are what caused the
prompt_registry.yaml corruption discovered before this phase (a duplicate
top-level key was silently overridden by PyYAML instead of raising).
This package prefers to fail loudly and specifically instead.
"""

from __future__ import annotations


class OrchestratorError(Exception):
    """Base class for all orchestrator-related errors."""


class AgentRegistryError(OrchestratorError):
    """Raised when the agent registry cannot be loaded or fails validation."""


class NoSuitableAgentError(OrchestratorError):
    """Raised when no registered agent matches a task's requirements."""

    def __init__(self, task_type: str, required_capabilities: list[str]):
        self.task_type = task_type
        self.required_capabilities = required_capabilities
        super().__init__(
            f"No suitable agent found for task_type={task_type!r} "
            f"with required_capabilities={required_capabilities!r}"
        )


class AgentUnavailableError(OrchestratorError):
    """Raised when a matched agent's status is not 'active'."""

    def __init__(self, agent_name: str, status: str):
        self.agent_name = agent_name
        self.status = status
        super().__init__(f"Agent {agent_name!r} matched but is not active (status={status!r})")


class UnknownExecutionError(OrchestratorError):
    """Raised when an execution_id is not found in the orchestrator's state store."""

    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        super().__init__(f"No execution found with id={execution_id!r}")


class PersistenceError(OrchestratorError):
    """Base class for all Phase-05 persistence-layer errors.

    Raised for failures in the storage backend itself (schema
    initialization, connection, read/write corruption) as distinct from
    ``AgentRegistryError`` (config loading) or the execution-state errors
    below, which are orchestration-logic errors, not storage errors.
    """


class ExecutionAlreadyExistsError(PersistenceError):
    """Raised when adding an execution whose execution_id is already stored."""

    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        super().__init__(f"Execution already exists with id={execution_id!r}")


class ExecutionSerializationError(PersistenceError):
    """Raised when an ``AgentExecution`` cannot be serialized to, or
    reconstructed from, a persistence backend's stored representation
    (e.g. an unknown ``state``/``priority`` value in a SQLite row, or a
    reference to an ``assigned_agent`` no longer present in the current
    agent registry)."""


class ExecutionEngineError(OrchestratorError):
    """Base class for all Phase-06 agent-execution-engine errors.

    Distinct from ``PersistenceError`` (storage failures) and the
    orchestration-logic errors above (selection/state-transition
    failures) -- these errors originate from actually invoking an
    agent's CLI, not from deciding which agent to use or tracking state.
    """


class AgentCommandNotConfiguredError(ExecutionEngineError):
    """Raised when an agent has no invocation command registered in
    ``config/agent_commands.yaml``."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        super().__init__(f"No invocation command configured for agent {agent_name!r}")


class AgentCommandRegistryError(ExecutionEngineError):
    """Raised when ``config/agent_commands.yaml`` cannot be loaded or fails
    validation. Mirrors ``AgentRegistryError``'s fail-loudly philosophy."""


class AgentInvocationError(ExecutionEngineError):
    """Raised when an agent's CLI could not be started at all (e.g. the
    executable is missing from PATH), as distinct from the CLI running
    and exiting non-zero, which is reported via ``ExecutionResult`` and
    handled as a retryable failure by ``ExecutionEngine`` instead."""

    def __init__(self, agent_name: str, reason: str):
        self.agent_name = agent_name
        self.reason = reason
        super().__init__(f"Failed to invoke agent {agent_name!r}: {reason}")


class AgentTimeoutError(ExecutionEngineError):
    """Raised when an agent's CLI does not complete within its configured
    timeout. Treated as retryable by ``ExecutionEngine``."""

    def __init__(self, agent_name: str, timeout_seconds: float):
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Agent {agent_name!r} timed out after {timeout_seconds}s")


class MaxRetriesExceededError(ExecutionEngineError):
    """Raised internally when every retry attempt for an execution has
    been exhausted. ``ExecutionEngine`` catches this and transitions the
    execution to ``FAILED`` via ``Orchestrator.mark_failed`` rather than
    letting it propagate."""

    def __init__(self, agent_name: str, attempts: int, last_error: str):
        self.agent_name = agent_name
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Agent {agent_name!r} failed after {attempts} attempt(s): {last_error}")


class ModelProviderError(OrchestratorError):
    """Base class for all Phase-07 model-provider-layer errors.

    Distinct from ``ExecutionEngineError`` (Phase-06 CLI-invocation
    errors): these originate from a ``ModelProvider`` adapter talking to
    a model provider's HTTP API, not from a subprocess. See
    ADR-0005 decision 5 for how ``HttpAgentInvoker`` maps these onto the
    existing ``AgentTimeoutError`` / ``AgentInvocationError`` retry
    contract ``ExecutionEngine`` already understands, so
    ``ExecutionEngine`` itself never needs to know this hierarchy
    exists.
    """


class ModelProviderRegistryError(ModelProviderError):
    """Raised when ``config/model_providers.yaml`` cannot be loaded or
    fails validation. Mirrors ``AgentCommandRegistryError``'s (Phase-06)
    fail-loudly philosophy: a malformed or missing config file is a
    configuration bug, reported specifically at load time rather than
    surfacing confusingly later at lookup or invocation time."""


class ProviderConfigNotFoundError(ModelProviderRegistryError):
    """Raised when an agent has no entry in ``config/model_providers.yaml``."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        super().__init__(f"No model provider configured for agent {agent_name!r}")


class ProviderDisabledError(ModelProviderRegistryError):
    """Raised when the entry for an agent in
    ``config/model_providers.yaml`` has ``enabled: false``. This is a
    configuration state, not a transient failure -- ``HttpAgentInvoker``
    (Task 7.5) lets it propagate immediately rather than retrying, per
    ADR-0005 decision 5."""

    def __init__(self, agent_name: str, provider_type: str):
        self.agent_name = agent_name
        self.provider_type = provider_type
        super().__init__(f"Model provider {provider_type!r} for agent {agent_name!r} is disabled")


class UnsupportedProviderTypeError(ModelProviderError):
    """Raised by ``ProviderFactory`` when a ``ProviderConfig.provider_type``
    has no registered ``ModelProvider`` adapter. A configuration/wiring
    bug (a provider_type was written in ``config/model_providers.yaml``
    that no adapter has been registered for), not a transient failure --
    ``HttpAgentInvoker`` lets it propagate immediately rather than
    retrying, same as ``ProviderConfigNotFoundError`` /
    ``ProviderDisabledError``."""

    def __init__(self, provider_type: str):
        self.provider_type = provider_type
        super().__init__(f"No ModelProvider adapter registered for provider_type {provider_type!r}")


class ProviderTimeoutError(ModelProviderError):
    """Raised by a ``ModelProvider`` implementation when a request to the
    provider's API does not complete within its configured
    ``timeout_seconds``."""

    def __init__(self, provider_type: str, timeout_seconds: float):
        self.provider_type = provider_type
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Provider {provider_type!r} timed out after {timeout_seconds}s")


class ProviderRequestError(ModelProviderError):
    """Raised by a ``ModelProvider`` implementation when a request to the
    provider's API fails for any reason other than a timeout: a
    connection/network failure, or a non-2xx HTTP response (including,
    but not limited to, invalid or expired credentials). Deliberately
    not split into finer-grained subtypes -- see ADR-0005 decision 5 for
    why ``HttpAgentInvoker`` treats all of these identically (a single
    retryable failure)."""

    def __init__(self, provider_type: str, reason: str):
        self.provider_type = provider_type
        self.reason = reason
        super().__init__(f"Request to provider {provider_type!r} failed: {reason}")


class PromptManagementError(OrchestratorError):
    """Base class for all Phase-08 prompt-management-layer errors.

    Distinct from ``ExecutionEngineError`` (Phase-06) and
    ``ModelProviderError`` (Phase-07): these originate from resolving,
    validating, or rendering a prompt, not from invoking an agent. Per
    ADR-0006 decision 8, every subclass here is treated as a
    configuration/validation error, not a transient one --
    ``SubprocessAgentInvoker`` / ``HttpAgentInvoker`` let all of these
    propagate out of ``invoke()`` unchanged, exactly like
    ``ProviderConfigNotFoundError`` / ``ProviderDisabledError`` today, so
    ``ExecutionEngine`` never needs to know this hierarchy exists.
    """


class PromptRegistryError(PromptManagementError):
    """Raised when ``prompts/prompt_registry.yaml`` cannot be loaded or
    fails validation (missing/malformed field, non-existent
    ``template_path``). Mirrors ``ModelProviderRegistryError``'s
    fail-loudly philosophy."""


class DuplicatePromptKeyError(PromptRegistryError):
    """Raised when ``prompts/prompt_registry.yaml`` contains the same
    top-level prompt key more than once.

    This is a direct fix for a previously-documented incident: PyYAML's
    default loader silently keeps the last value of a duplicate mapping
    key instead of raising, which once corrupted this exact file. See
    ADR-0006 decision 3.
    """

    def __init__(self, prompt_id: str):
        self.prompt_id = prompt_id
        super().__init__(
            f"Duplicate prompt key {prompt_id!r} in prompt registry file "
            f"(a mapping key must appear at most once)"
        )


class PromptTemplateFileMissingError(PromptRegistryError):
    """Raised when a prompt entry's ``template_path`` does not exist on
    disk. Checked at registry-load time, not deferred to first render."""

    def __init__(self, prompt_id: str, template_path: str):
        self.prompt_id = prompt_id
        self.template_path = template_path
        super().__init__(
            f"Prompt {prompt_id!r} references template_path {template_path!r}, which does not exist"
        )


class PromptNotFoundError(PromptManagementError):
    """Raised when a requested ``prompt_id`` has no entry in the prompt
    registry."""

    def __init__(self, prompt_id: str):
        self.prompt_id = prompt_id
        super().__init__(f"No prompt found with id={prompt_id!r}")


class PromptNotAllowedForAgentError(PromptManagementError):
    """Raised when ``PromptManager.resolve()``/``render()`` is called
    with an ``agent_name`` that is not listed in the prompt definition's
    ``agents``. A configuration mismatch, not a transient failure."""

    def __init__(self, prompt_id: str, agent_name: str):
        self.prompt_id = prompt_id
        self.agent_name = agent_name
        super().__init__(f"Prompt {prompt_id!r} is not allowed for agent {agent_name!r}")


class MissingRequiredVariableError(PromptManagementError):
    """Raised when rendering a prompt omits a variable declared
    ``required: true`` in its definition."""

    def __init__(self, prompt_id: str, variable_name: str):
        self.prompt_id = prompt_id
        self.variable_name = variable_name
        super().__init__(f"Prompt {prompt_id!r} is missing required variable {variable_name!r}")


class UnknownVariableError(PromptManagementError):
    """Raised when rendering a prompt supplies a variable that is not
    declared in its definition. Rejected rather than silently ignored,
    per the project's fail-loudly philosophy (a typo'd variable name
    should never be silently dropped)."""

    def __init__(self, prompt_id: str, variable_name: str):
        self.prompt_id = prompt_id
        self.variable_name = variable_name
        super().__init__(f"Prompt {prompt_id!r} was given undeclared variable {variable_name!r}")


class ToolError(OrchestratorError):
    """Base class for all Phase-09 tool-execution-framework errors.

    Distinct from ``ExecutionEngineError`` (Phase-06 CLI invocation),
    ``ModelProviderError`` (Phase-07 HTTP provider calls), and
    ``PromptManagementError`` (Phase-08 prompt resolution/rendering):
    these originate from resolving, validating, or running a ``Tool``,
    not from any agent-invocation path. Phase-09 does not wire this
    hierarchy into ``AgentTask``, ``ExecutionEngine``, or either
    ``AgentInvoker`` -- see ADR-0007 decision 6.
    """


class ToolRegistryError(ToolError):
    """Raised when ``config/tools.yaml`` cannot be loaded or fails
    validation. Mirrors ``ModelProviderRegistryError``'s (Phase-07)
    fail-loudly philosophy."""


class ToolNotFoundError(ToolError):
    """Raised when a requested ``tool_name`` has no entry in the tool
    registry."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"No tool found with name={tool_name!r}")


class ToolDisabledError(ToolError):
    """Raised when the entry for ``tool_name`` in ``config/tools.yaml``
    has ``enabled: false``. A configuration state, not a transient
    failure -- mirrors ``ProviderDisabledError`` (Phase-07)."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool {tool_name!r} is disabled")


class UnsupportedToolTypeError(ToolError):
    """Raised by ``ToolFactory`` when a ``ToolDefinition.tool_type`` has
    no registered ``Tool`` adapter. A configuration/wiring bug, mirrors
    ``UnsupportedProviderTypeError`` (Phase-07)."""

    def __init__(self, tool_type: str):
        self.tool_type = tool_type
        super().__init__(f"No Tool implementation registered for tool_type {tool_type!r}")


class MissingRequiredArgumentError(ToolError):
    """Raised when ``ToolExecutor.execute()`` is called without a value
    for an argument declared ``required: true`` in the tool's
    definition. Mirrors ``MissingRequiredVariableError`` (Phase-08)."""

    def __init__(self, tool_name: str, argument_name: str):
        self.tool_name = tool_name
        self.argument_name = argument_name
        super().__init__(f"Tool {tool_name!r} is missing required argument {argument_name!r}")


class UnknownArgumentError(ToolError):
    """Raised when ``ToolExecutor.execute()`` is supplied an argument
    that is not declared in the tool's definition. Rejected rather than
    silently ignored, per the project's fail-loudly philosophy. Mirrors
    ``UnknownVariableError`` (Phase-08)."""

    def __init__(self, tool_name: str, argument_name: str):
        self.tool_name = tool_name
        self.argument_name = argument_name
        super().__init__(f"Tool {tool_name!r} was given undeclared argument {argument_name!r}")


class InvalidArgumentTypeError(ToolError):
    """Raised when an argument's runtime value does not match its
    declared ``type`` (``string`` | ``number`` | ``boolean``)."""

    def __init__(
        self, tool_name: str, argument_name: str, expected_type: str, actual_value: object
    ):
        self.tool_name = tool_name
        self.argument_name = argument_name
        self.expected_type = expected_type
        super().__init__(
            f"Tool {tool_name!r} argument {argument_name!r} must be of type "
            f"{expected_type!r}, got {type(actual_value).__name__}"
        )


class ToolExecutionError(ToolError):
    """Raised when a ``Tool`` implementation's ``execute()`` fails for
    any reason specific to that tool (e.g. file not found, permission
    denied) -- as distinct from the configuration/validation errors
    above, which are raised before a tool ever runs."""

    def __init__(self, tool_name: str, reason: str):
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Tool {tool_name!r} failed: {reason}")


class MemoryManagementError(OrchestratorError):
    """Base class for all Phase-10 memory-management-layer errors.

    Named ``MemoryManagementError`` rather than ``MemoryError`` to avoid
    shadowing the Python builtin ``MemoryError``, matching the
    ``PromptManagementError`` (Phase-08) naming convention. Distinct from
    ``PersistenceError`` (Phase-05, ``AgentExecution`` storage) and
    ``ToolError`` (Phase-09): these originate from a ``MemoryStore``
    Port/adapter storing or retrieving a ``MemoryEntry``, not from
    execution-state storage or tool execution. Phase-10 does not wire
    this hierarchy into ``AgentTask``, ``ExecutionEngine``, or
    ``ToolExecutor`` -- see ADR-0008 decision 7.
    """


class MemoryEntryNotFoundError(MemoryManagementError):
    """Raised when no entry exists for a given ``(key, scope)`` pair on
    ``MemoryStore.get()`` / ``update()`` / ``delete()``."""

    def __init__(self, key: str, scope: str):
        self.key = key
        self.scope = scope
        super().__init__(f"No memory entry found for key={key!r} scope={scope!r}")


class MemoryEntryAlreadyExistsError(MemoryManagementError):
    """Raised by ``MemoryStore.add()`` when an entry already exists for
    the given ``(key, scope)`` pair. Mirrors
    ``ExecutionAlreadyExistsError`` (Phase-05)."""

    def __init__(self, key: str, scope: str):
        self.key = key
        self.scope = scope
        super().__init__(f"Memory entry already exists for key={key!r} scope={scope!r}")


class MemorySerializationError(MemoryManagementError):
    """Raised when a ``MemoryEntry`` cannot be reconstructed from a
    ``SQLiteMemoryStore`` row (e.g. non-JSON ``metadata``). Mirrors
    ``ExecutionSerializationError`` (Phase-05)."""


class WorkflowError(OrchestratorError):
    """Base class for all Phase-11 workflow-engine-layer errors.

    Distinct from ``ToolError`` (Phase-09) and ``MemoryManagementError``
    (Phase-10): these originate from ``orchestrator.workflow`` composing
    the ``Orchestrator``/``ExecutionEngine``/``ToolExecutor`` boundary,
    not from a single component's own internals. See ADR-0009.
    """


class WorkflowRegistryError(WorkflowError):
    """Raised when ``config/workflows.yaml`` cannot be loaded or fails
    validation. Mirrors ``ToolRegistryError`` (Phase-09)."""


class WorkflowNotFoundError(WorkflowError):
    """Raised when no entry exists for a given ``workflow_id`` in the
    ``WorkflowRegistry``."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        super().__init__(f"No workflow found for workflow_id={workflow_id!r}")


class UnknownWorkflowRunError(WorkflowError):
    """Raised when no ``WorkflowRun`` exists for a given ``run_id`` in the
    ``WorkflowRunRepository``. Mirrors ``UnknownExecutionError``
    (Phase-05)."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"No workflow run found for run_id={run_id!r}")


class WorkflowRunAlreadyExistsError(WorkflowError):
    """Raised by ``WorkflowRunRepository.add()`` when a run already exists
    for the given ``run_id``. Mirrors ``ExecutionAlreadyExistsError``
    (Phase-05)."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Workflow run already exists for run_id={run_id!r}")


class InvalidWorkflowStateTransitionError(WorkflowError):
    """Raised when a ``WorkflowEngine`` method is called on a run whose
    current state does not permit that action. Mirrors
    ``InvalidStateTransitionError`` (Phase-04)."""

    def __init__(self, run_id: str, action: str, expected_state: str, actual_state: str):
        self.run_id = run_id
        self.action = action
        self.expected_state = expected_state
        self.actual_state = actual_state
        super().__init__(
            f"Cannot {action} workflow run {run_id!r}: requires state "
            f"{expected_state!r}, but current state is {actual_state!r}"
        )


class WorkflowStepNotApprovedError(WorkflowError):
    """Raised by ``WorkflowEngine.resume()`` when the pending
    ``AgentExecution`` for the current ``agent_task`` step has not yet
    reached ``COMPLETED`` (i.e. ``Orchestrator.approve()`` has not been
    called on it yet). See ADR-0009 decision 4."""

    def __init__(self, run_id: str, execution_id: str, actual_state: str):
        self.run_id = run_id
        self.execution_id = execution_id
        self.actual_state = actual_state
        super().__init__(
            f"Cannot resume workflow run {run_id!r}: pending execution "
            f"{execution_id!r} is not yet approved (current state: "
            f"{actual_state!r})"
        )


class SecurityError(OrchestratorError):
    """Base class for all Phase-12 security-and-permissions errors.

    Distinct from ``ToolError`` (Phase-09): these originate from
    ``orchestrator.security`` -- path-sandbox and per-agent read/write
    authorization -- not from resolving, validating, or running a
    ``Tool`` itself. ``ToolExecutor`` raises these via
    ``orchestrator.security.authorizer.ToolAuthorizer``, after argument
    validation and before a tool ever runs. See ADR-0010.
    """


class PermissionRegistryError(SecurityError):
    """Raised when ``config/permissions.yaml`` cannot be loaded or fails
    validation. Mirrors ``ToolRegistryError`` (Phase-09)."""


class PathPermissionError(SecurityError):
    """Raised when a tool argument declared in
    ``ToolDefinition.sandboxed_parameters`` resolves outside the
    configured path sandbox (``PathSandboxPolicy.allowed_roots``)."""

    def __init__(self, tool_name: str, argument_name: str, path: object):
        self.tool_name = tool_name
        self.argument_name = argument_name
        self.path = path
        super().__init__(
            f"Tool {tool_name!r} argument {argument_name!r} path {str(path)!r} "
            "is outside the allowed path sandbox"
        )


class AgentPermissionError(SecurityError):
    """Raised when a known agent's configured ``AgentPermission`` does
    not grant the access mode (``read`` | ``write``) a tool requires."""

    def __init__(self, agent_name: str, tool_name: str, access_mode: str):
        self.agent_name = agent_name
        self.tool_name = tool_name
        self.access_mode = access_mode
        super().__init__(
            f"Agent {agent_name!r} is not permitted {access_mode!r} access "
            f"required by tool {tool_name!r}"
        )


class UnknownAgentPermissionError(SecurityError):
    """Raised when an ``agent_name`` supplied to ``ToolExecutor.execute()``
    has no entry in ``config/permissions.yaml``'s ``agent_permissions``
    section. Denied outright rather than defaulted permissively, per
    this project's fail-loudly philosophy."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        super().__init__(f"No permission entry configured for agent_name={agent_name!r}")


class InvalidStateTransitionError(OrchestratorError):
    """Raised when an orchestrator method is called on an execution whose
    current state does not permit that action.

    Patch note: this exception closes a gap where route()/mark_awaiting_
    approval()/approve() previously performed their state transition
    unconditionally, regardless of the execution's current state -- which
    made it possible to call approve() on an execution that had never
    been routed, reaching COMPLETED with no assigned agent and no human
    review having actually occurred.
    """

    def __init__(self, execution_id: str, action: str, expected_state: str, actual_state: str):
        self.execution_id = execution_id
        self.action = action
        self.expected_state = expected_state
        self.actual_state = actual_state
        super().__init__(
            f"Cannot {action} execution {execution_id!r}: requires state "
            f"{expected_state!r}, but current state is {actual_state!r}"
        )


class ObservabilityError(OrchestratorError):
    """Base class for all Phase-13 monitoring-and-observability errors.

    Distinct from every other hierarchy above: these originate from
    ``orchestrator.observability`` -- recording/config-loading for
    structured events and metrics -- not from any agent-invocation,
    tool, or workflow path. Integrated components
    (``Orchestrator``/``ExecutionEngine``/``ToolExecutor``/
    ``WorkflowEngine``) never raise these themselves; they only ever
    reach an ``ObservabilityRecorder`` through the optional ``observer``
    parameter added in this phase. See ADR-0011.
    """


class ObservabilityRegistryError(ObservabilityError):
    """Raised when ``config/observability.yaml`` cannot be loaded or
    fails validation. Mirrors ``PermissionRegistryError`` (Phase-12)."""


class InvalidMetricTypeError(ObservabilityError):
    """Raised by ``InMemoryRecorder.record_metric()`` when a
    ``MetricPoint.metric_type`` is not one of the supported values
    (``"counter"`` | ``"timer"``). None of this phase's own integrated
    call sites can trigger this -- it exists to fail loudly on a future
    coding mistake rather than any input reachable through normal use.
    """

    def __init__(self, metric_name: str, metric_type: str):
        self.metric_name = metric_name
        self.metric_type = metric_type
        super().__init__(
            f"Metric {metric_name!r} has unsupported metric_type={metric_type!r}; "
            "expected 'counter' or 'timer'"
        )
