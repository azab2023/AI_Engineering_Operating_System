"""Unit tests for Orchestrator.select_agent (task -> agent matching)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator.core import Orchestrator
from orchestrator.exceptions import AgentUnavailableError, NoSuitableAgentError
from orchestrator.models import (
    Agent,
    AgentCapability,
    AgentPriority,
    AgentStatus,
    AgentTask,
)
from orchestrator.registry import AgentRegistry, DEFAULT_REGISTRY_PATH


@pytest.fixture()
def registry() -> AgentRegistry:
    return AgentRegistry(DEFAULT_REGISTRY_PATH)


@pytest.fixture()
def orchestrator(registry: AgentRegistry) -> Orchestrator:
    return Orchestrator(registry)


def test_select_agent_matches_by_task_type(orchestrator: Orchestrator):
    task = AgentTask(task_type="code_generation", description="Write a parser")
    agent = orchestrator.select_agent(task)
    assert agent.supports_task("code_generation")
    assert agent.is_active()


def test_select_agent_respects_required_capabilities(orchestrator: Orchestrator):
    task = AgentTask(
        task_type="documentation",
        description="Write architecture docs",
        required_capabilities=("automation_design",),
    )
    agent = orchestrator.select_agent(task)
    assert agent.has_capability("automation_design")
    assert agent.supports_task("documentation")


def test_select_agent_no_match_raises(orchestrator: Orchestrator):
    task = AgentTask(task_type="quantum_circuit_design", description="Not a real task")
    with pytest.raises(NoSuitableAgentError) as exc_info:
        orchestrator.select_agent(task)
    assert exc_info.value.task_type == "quantum_circuit_design"


def test_select_agent_capability_not_met_raises(orchestrator: Orchestrator):
    task = AgentTask(
        task_type="code_generation",
        description="Needs a capability nothing has",
        required_capabilities=("time_travel",),
    )
    with pytest.raises(NoSuitableAgentError):
        orchestrator.select_agent(task)


def test_select_agent_skips_inactive_agents():
    inactive_agent = Agent(
        name="inactive_only",
        provider="test",
        capabilities=(AgentCapability(name="niche_task"),),
        supported_tasks=("niche_task",),
        config_reference="agents/inactive_only/config",
        status=AgentStatus.INACTIVE,
        priority=AgentPriority.MEDIUM,
    )

    class _SingleAgentRegistry:
        def find_by_task(self, task_type: str):
            return [inactive_agent] if task_type == "niche_task" else []

    orchestrator = Orchestrator(_SingleAgentRegistry())
    task = AgentTask(task_type="niche_task", description="Only an inactive agent can do this")

    with pytest.raises(AgentUnavailableError) as exc_info:
        orchestrator.select_agent(task)
    assert exc_info.value.agent_name == "inactive_only"
    assert exc_info.value.status == "inactive"


def test_select_agent_picks_highest_priority_when_multiple_match(orchestrator: Orchestrator):
    # Both codex (priority: high) and aider (priority: medium) support 'debugging'.
    # codex must win because it has higher priority, not because of file order alone.
    task = AgentTask(task_type="debugging", description="Fix a bug")
    agent = orchestrator.select_agent(task)
    assert agent.name == "codex"
    assert agent.priority == AgentPriority.HIGH

    # Calling again must return the same agent (determinism, not randomness).
    agent_again = orchestrator.select_agent(task)
    assert agent.name == agent_again.name


def test_select_agent_priority_overrides_registry_order(tmp_path: Path):
    # aider is listed FIRST but has lower priority than codex, listed SECOND.
    # If selection were still pure "first in file" (pre-patch behavior), this
    # would incorrectly select aider. Priority must take precedence over order.
    path = tmp_path / "agent_registry.yaml"
    path.write_text(
        textwrap.dedent(
            """
            agents:
              - name: aider
                provider: openai
                capabilities:
                  - name: debugging
                supported_tasks:
                  - debugging
                config_reference: agents/aider/config
                status: active
                priority: medium
              - name: codex
                provider: openai
                capabilities:
                  - name: debugging
                supported_tasks:
                  - debugging
                config_reference: agents/openai-codex/config
                status: active
                priority: high
            """
        ),
        encoding="utf-8",
    )
    registry = AgentRegistry(path)
    orchestrator = Orchestrator(registry)

    task = AgentTask(task_type="debugging", description="Fix a bug")
    agent = orchestrator.select_agent(task)

    assert agent.name == "codex"


def test_select_agent_tie_breaks_by_registry_order_when_priority_equal(tmp_path: Path):
    # Two equal-priority agents: registry (insertion) order must decide, and
    # that choice must be stable across repeated calls.
    path = tmp_path / "agent_registry.yaml"
    path.write_text(
        textwrap.dedent(
            """
            agents:
              - name: second_but_first_in_file
                provider: test
                capabilities:
                  - name: writing
                supported_tasks:
                  - writing
                config_reference: agents/a/config
                status: active
                priority: high
              - name: also_high_priority
                provider: test
                capabilities:
                  - name: writing
                supported_tasks:
                  - writing
                config_reference: agents/b/config
                status: active
                priority: high
            """
        ),
        encoding="utf-8",
    )
    registry = AgentRegistry(path)
    orchestrator = Orchestrator(registry)

    task = AgentTask(task_type="writing", description="Draft something")
    first_call = orchestrator.select_agent(task)
    second_call = orchestrator.select_agent(task)

    assert first_call.name == "second_but_first_in_file"
    assert second_call.name == "second_but_first_in_file"
