"""
orchestrator.execution.invoker
=================================

Defines the ``AgentInvoker`` interface (Strategy/Port pattern) that
``ExecutionEngine`` depends on to actually run an agent, plus
``SubprocessAgentInvoker``, the concrete implementation that shells out to
each agent's CLI per ``config/agent_commands.yaml``.

Why an interface instead of hard-coding subprocess calls into
``ExecutionEngine``: keeps the engine's retry/state-transition logic unit-
testable without spawning real processes, and keeps the door open for a
future HTTP-based provider adapter (Phase-07: Model Provider Abstraction)
without touching the engine again -- same rationale as
``ExecutionRepository`` in Phase-05.

Security note: commands are executed via ``subprocess.run(..., shell=False)``
with an argv list, never a shell string, so a task description containing
shell metacharacters cannot escape into command injection.
"""

from __future__ import annotations

import subprocess
import time
from typing import Protocol

from orchestrator.exceptions import AgentInvocationError, AgentTimeoutError
from orchestrator.execution.command_registry import AgentCommandRegistry
from orchestrator.execution.models import ExecutionResult
from orchestrator.logging_setup import get_logger
from orchestrator.models import Agent, AgentTask

logger = get_logger("execution.invoker")

_PLACEHOLDER = "{task_description}"


class AgentInvoker(Protocol):
    """Port: something that can run one agent against one task and report
    the outcome as an ``ExecutionResult``."""

    def invoke(self, agent: Agent, task: AgentTask) -> ExecutionResult:
        """Run ``agent`` against ``task`` and return the outcome.

        Raises:
            AgentTimeoutError: the invocation exceeded its configured
                timeout. Treated as retryable by ``ExecutionEngine``.
            AgentInvocationError: the invocation could not be started at
                all (e.g. missing executable). Treated as retryable by
                ``ExecutionEngine`` -- transient environment issues (a
                CLI not yet on PATH) are indistinguishable from
                permanent ones without a second attempt.
        """
        ...


class SubprocessAgentInvoker:
    """Invokes an agent by running its configured CLI command as a
    subprocess, per ``config/agent_commands.yaml``."""

    def __init__(self, command_registry: AgentCommandRegistry | None = None):
        self._command_registry = command_registry or AgentCommandRegistry()

    def invoke(self, agent: Agent, task: AgentTask) -> ExecutionResult:
        agent_command = self._command_registry.get_command(agent.name)
        argv = [
            token if token != _PLACEHOLDER else task.description for token in agent_command.command
        ]

        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=agent_command.timeout_seconds,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            logger.warning(
                "Agent invocation timed out: agent=%s timeout=%.1fs",
                agent.name,
                agent_command.timeout_seconds,
            )
            raise AgentTimeoutError(agent.name, agent_command.timeout_seconds) from exc
        except OSError as exc:
            logger.error("Agent invocation could not start: agent=%s error=%s", agent.name, exc)
            raise AgentInvocationError(agent.name, str(exc)) from exc

        duration = time.monotonic() - started
        output = completed.stdout if completed.returncode == 0 else completed.stderr
        logger.info(
            "Agent invocation finished: agent=%s exit_code=%d duration=%.2fs",
            agent.name,
            completed.returncode,
            duration,
        )
        return ExecutionResult(
            output=output,
            exit_code=completed.returncode,
            duration_seconds=duration,
        )
