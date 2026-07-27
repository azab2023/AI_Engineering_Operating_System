"""
orchestrator.tools.tool_executor
====================================

``ToolExecutor``: the sole Facade for running a tool by name. Mirrors
``orchestrator.prompts.prompt_manager.PromptManager`` (Phase-08) one
layer over -- it composes ``ToolRegistry`` (lookup/validation) and
``ToolFactory`` (resolution to a concrete ``Tool``), and is the only
entry point a future caller (e.g. the Phase-11 Workflow Engine) is
expected to depend on. Neither ``ToolRegistry`` nor ``ToolFactory`` is
meant to be used directly by such a caller.

Phase-09 does not wire this into ``AgentTask``, ``ExecutionEngine``, or
either ``AgentInvoker`` -- see ADR-0007 decision 6. It is a
self-contained, additive package with no call sites elsewhere in the
codebase yet.
"""

from __future__ import annotations

from typing import Any

from orchestrator.exceptions import (
    InvalidArgumentTypeError,
    MissingRequiredArgumentError,
    ToolExecutionError,
    UnknownArgumentError,
)
from orchestrator.logging_setup import get_logger
from orchestrator.security.authorizer import ToolAuthorizer
from orchestrator.tools.models import ToolDefinition, ToolResult
from orchestrator.tools.tool_factory import ToolFactory
from orchestrator.tools.tool_registry import ToolRegistry

logger = get_logger("tools.tool_executor")

_PYTHON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "boolean": bool,
}


class ToolExecutor:
    """Resolves a ``tool_name``, validates arguments against its
    declared parameters, and runs it.

    Args:
        registry: source of validated ``ToolDefinition`` lookups.
            Defaults to a ``ToolRegistry`` loaded from the default
            ``config/tools.yaml`` path.
        factory: resolves a ``ToolDefinition`` to a concrete ``Tool``
            instance. Defaults to ``ToolFactory``.
        authorizer: the Phase-12 (ADR-0010) authorization layer --
            path-sandbox and per-agent read/write checks. Defaults to
            a ``ToolAuthorizer`` loaded from the default
            ``config/permissions.yaml`` path.
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        factory: type[ToolFactory] = ToolFactory,
        authorizer: ToolAuthorizer | None = None,
    ):
        self._registry = registry or ToolRegistry()
        self._factory = factory
        self._authorizer = authorizer or ToolAuthorizer()

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        agent_name: str | None = None,
    ) -> ToolResult:
        """Resolve ``tool_name``, validate ``arguments`` against its
        declared parameters, authorize the call, and run it.

        Args:
            tool_name: the tool to run.
            arguments: the arguments to pass to it.
            agent_name: the calling agent's identity, if known (e.g. a
                ``WorkflowStep.agent_name``). When ``None`` (the
                default), no agent-level permission check is performed
                -- unchanged behavior for every pre-Phase-12 caller.
                The path-sandbox check always runs regardless. See
                ADR-0010 decision 7.

        Raises:
            ToolNotFoundError: no entry exists for ``tool_name``.
            ToolDisabledError: the entry exists but has
                ``enabled: false``.
            UnsupportedToolTypeError: no ``Tool`` implementation is
                registered for the definition's ``tool_type``.
            MissingRequiredArgumentError: a required argument is absent.
            UnknownArgumentError: an undeclared argument was supplied.
            InvalidArgumentTypeError: an argument's value does not match
                its declared type.
            UnknownAgentPermissionError: ``agent_name`` was given but is
                not configured in ``config/permissions.yaml``.
            AgentPermissionError: ``agent_name`` is configured but not
                permitted this tool's ``access_mode``.
            PathPermissionError: a sandboxed argument resolves outside
                the configured path sandbox.
            ToolExecutionError: the tool resolved, its arguments
                validated, and authorization passed, but running it
                failed.
        """
        definition = self._registry.get_definition(tool_name)
        arguments = arguments or {}
        self._validate_arguments(definition, arguments)
        self._authorizer.authorize(definition, arguments, agent_name)

        tool = self._factory.create(definition)

        try:
            result = tool.execute(arguments)
        except ToolExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - see docstring below
            # A conforming ``Tool`` implementation should only ever
            # raise ``ToolExecutionError`` (per the ``Tool`` Protocol
            # docstring), but this boundary still wraps any other
            # exception rather than letting an implementation-specific
            # failure leak past the ``ToolExecutor`` Facade unannounced
            # -- the same fail-loudly-but-specifically posture as every
            # prior phase's boundary layer.
            raise ToolExecutionError(tool_name, str(exc)) from exc

        logger.info(
            "Tool executed: tool_name=%s duration=%.4fs", tool_name, result.duration_seconds
        )
        return result

    def _validate_arguments(self, definition: ToolDefinition, arguments: dict[str, Any]) -> None:
        provided = set(arguments.keys())
        declared = definition.declared_argument_names()

        missing = definition.required_argument_names() - provided
        if missing:
            raise MissingRequiredArgumentError(definition.tool_name, sorted(missing)[0])

        unknown = provided - declared
        if unknown:
            raise UnknownArgumentError(definition.tool_name, sorted(unknown)[0])

        for name, value in arguments.items():
            parameter = definition.parameter(name)
            expected = _PYTHON_TYPES[parameter.type]
            # bool is a subclass of int; only "number" should accept it
            # implicitly via int, never disguise a bool as a number.
            if parameter.type == "number" and isinstance(value, bool):
                raise InvalidArgumentTypeError(definition.tool_name, name, parameter.type, value)
            if not isinstance(value, expected):
                raise InvalidArgumentTypeError(definition.tool_name, name, parameter.type, value)
