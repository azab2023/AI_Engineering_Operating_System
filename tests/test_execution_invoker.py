"""Unit tests for orchestrator.execution.invoker.SubprocessAgentInvoker.

Uses ``sys.executable`` to invoke small inline Python scripts as the
"agent CLI", so these tests need no external tools installed and are
platform-independent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from orchestrator.exceptions import (
    AgentInvocationError,
    AgentTimeoutError,
    PromptNotAllowedForAgentError,
)
from orchestrator.execution.command_registry import AgentCommandRegistry
from orchestrator.execution.invoker import SubprocessAgentInvoker
from orchestrator.models import Agent, AgentCapability, AgentPriority, AgentStatus, AgentTask
from orchestrator.prompts.prompt_manager import PromptManager
from orchestrator.prompts.prompt_registry import PromptRegistry


def _agent(name: str = "test_agent") -> Agent:
    return Agent(
        name=name,
        provider="test",
        capabilities=(AgentCapability(name="cap"),),
        supported_tasks=("test_task",),
        config_reference="agents/test",
        status=AgentStatus.ACTIVE,
        priority=AgentPriority.HIGH,
    )


def _registry_with(tmp_path: Path, agent_name: str, command: list, timeout: float = 5):
    import yaml

    path = tmp_path / "agent_commands.yaml"
    data = {"commands": {agent_name: {"command": command, "timeout_seconds": timeout}}}
    path.write_text(yaml.safe_dump(data))
    return AgentCommandRegistry(path)


def test_successful_invocation_returns_result(tmp_path: Path):
    registry = _registry_with(
        tmp_path,
        "test_agent",
        [sys.executable, "-c", "import sys; print(sys.argv[1])", "{task_description}"],
    )
    invoker = SubprocessAgentInvoker(registry)
    result = invoker.invoke(_agent(), AgentTask(task_type="test_task", description="hello"))

    assert result.succeeded()
    assert result.exit_code == 0
    assert result.output.strip() == "hello"
    assert result.duration_seconds >= 0


def test_nonzero_exit_returns_failed_result_with_stderr(tmp_path: Path):
    script = "import sys; print('boom', file=sys.stderr); sys.exit(1)"
    registry = _registry_with(
        tmp_path, "test_agent", [sys.executable, "-c", script, "{task_description}"]
    )
    invoker = SubprocessAgentInvoker(registry)
    result = invoker.invoke(_agent(), AgentTask(task_type="test_task", description="x"))

    assert not result.succeeded()
    assert result.exit_code == 1
    assert "boom" in result.output


def test_timeout_raises_agent_timeout_error(tmp_path: Path):
    script = "import time; time.sleep(5)"
    registry = _registry_with(
        tmp_path,
        "test_agent",
        [sys.executable, "-c", script, "{task_description}"],
        timeout=0.2,
    )
    invoker = SubprocessAgentInvoker(registry)
    with pytest.raises(AgentTimeoutError):
        invoker.invoke(_agent(), AgentTask(task_type="test_task", description="x"))


def test_missing_executable_raises_agent_invocation_error(tmp_path: Path):
    registry = _registry_with(
        tmp_path, "test_agent", ["definitely_not_a_real_executable_xyz", "{task_description}"]
    )
    invoker = SubprocessAgentInvoker(registry)
    with pytest.raises(AgentInvocationError):
        invoker.invoke(_agent(), AgentTask(task_type="test_task", description="x"))


def test_task_description_is_not_shell_interpreted(tmp_path: Path):
    """A description containing shell metacharacters must be passed through
    literally (argv, not a shell string) and not cause command injection."""
    registry = _registry_with(
        tmp_path,
        "test_agent",
        [sys.executable, "-c", "import sys; print(sys.argv[1])", "{task_description}"],
    )
    invoker = SubprocessAgentInvoker(registry)
    dangerous = "hello; rm -rf /tmp/should_not_run && echo pwned"
    result = invoker.invoke(_agent(), AgentTask(task_type="test_task", description=dangerous))

    assert result.output.strip() == dangerous


# --------------------------------------------------------------------- #
# Phase-08: prompt resolution (ADR-0006 decision 6)
# --------------------------------------------------------------------- #


def test_prompt_id_none_uses_description_unchanged_from_phase07(tmp_path: Path):
    """Regression guard: when task.prompt_id is None, behavior must be
    byte-for-byte identical to pre-Phase-08 -- task.description is used
    as-is, with no PromptManager involvement at all."""
    registry = _registry_with(
        tmp_path,
        "test_agent",
        [sys.executable, "-c", "import sys; print(sys.argv[1])", "{task_description}"],
    )
    invoker = SubprocessAgentInvoker(registry)
    result = invoker.invoke(_agent(), AgentTask(task_type="test_task", description="hello"))

    assert result.output.strip() == "hello"


def test_prompt_id_set_renders_via_prompt_manager(tmp_path: Path):
    registry = _registry_with(
        tmp_path,
        "codex",
        [sys.executable, "-c", "import sys; print(sys.argv[1])", "{task_description}"],
    )
    invoker = SubprocessAgentInvoker(
        registry, prompt_manager=PromptManager(registry=PromptRegistry())
    )
    task = AgentTask(
        task_type="test_task",
        description="unused when prompt_id is set",
        prompt_id="code_generation",
        prompt_variables={"task_description": "add two numbers", "language": "Python"},
    )
    result = invoker.invoke(_agent("codex"), task)

    assert "add two numbers" in result.output
    assert "Python" in result.output


def test_prompt_not_allowed_for_agent_propagates_uncaught(tmp_path: Path):
    """A prompt/agent mismatch is a configuration error, not a transient
    failure -- it must propagate out of invoke() unretried, exactly like
    AgentCommandNotConfiguredError does today."""
    registry = _registry_with(
        tmp_path,
        "gemini",
        [sys.executable, "-c", "print('should not run')", "{task_description}"],
    )
    invoker = SubprocessAgentInvoker(
        registry, prompt_manager=PromptManager(registry=PromptRegistry())
    )
    task = AgentTask(
        task_type="test_task",
        description="x",
        prompt_id="code_generation",  # not allowed for gemini
        prompt_variables={"task_description": "x"},
    )
    with pytest.raises(PromptNotAllowedForAgentError):
        invoker.invoke(_agent("gemini"), task)
