"""Unit tests for Orchestrator.select_agent (task -> agent matching)."""

from __future__ import annotations

import pytest

from orchestrator.core import Orchestrator
from orchestrator.exceptions import AgentUnavailableError, NoSuitableAgentError
from orchestrator.models import (
    Agent,
    AgentCapability,
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


def test_select_agent_picks_first_eligible_when_multiple_match(orchestrator: Orchestrator):
    task = AgentTask(task_type="debugging", description="Fix a bug")
    agent = orchestrator.select_agent(task)
    # Both codex and aider support 'debugging'; selection must be deterministic.
    assert agent.name in {"codex", "aider"}
    # Calling again must return the same agent (determinism, not randomness).
    agent_again = orchestrator.select_agent(task)
    assert agent.name == agent_again.name
