"""
orchestrator
============

Phase-04 Agent Orchestration foundation for the AI_Engineering_Operating_System.

This package provides:
    - Data models for agents, capabilities, tasks, and executions (models.py)
    - A registry that loads and validates agent definitions (registry.py)
    - The orchestrator core that selects agents and tracks execution state (core.py)
    - A single, shared logging setup used by this and future phases (logging_setup.py)

Scope note (Phase-04):
    This package performs task -> agent SELECTION and ROUTING/STATE TRACKING.
    It does NOT invoke any agent CLI, API, or subprocess. Actual agent
    execution backends are out of scope for this phase.
"""

from orchestrator.core import Orchestrator
from orchestrator.exceptions import (
    AgentRegistryError,
    AgentUnavailableError,
    InvalidStateTransitionError,
    NoSuitableAgentError,
    OrchestratorError,
    UnknownExecutionError,
)
from orchestrator.models import (
    Agent,
    AgentCapability,
    AgentExecution,
    AgentPriority,
    AgentStatus,
    AgentTask,
    ExecutionState,
)
from orchestrator.registry import AgentRegistry

__all__ = [
    "Agent",
    "AgentCapability",
    "AgentTask",
    "AgentExecution",
    "AgentPriority",
    "ExecutionState",
    "AgentStatus",
    "AgentRegistry",
    "Orchestrator",
    "OrchestratorError",
    "AgentRegistryError",
    "NoSuitableAgentError",
    "AgentUnavailableError",
    "UnknownExecutionError",
    "InvalidStateTransitionError",
]

__version__ = "0.1.1"
