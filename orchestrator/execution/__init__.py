"""
orchestrator.execution
=========================

Phase-06 Agent Execution Engine for the AI_Engineering_Operating_System.

This package provides:
    - ``ExecutionResult`` / ``RetryPolicy`` / ``AgentCommand`` data models
      (models.py)
    - ``AgentCommandRegistry``, which loads and validates
      ``config/agent_commands.yaml`` (command_registry.py)
    - The ``AgentInvoker`` port and its ``SubprocessAgentInvoker``
      implementation, which actually runs an agent's CLI (invoker.py)
    - ``ExecutionEngine``, which routes (if needed), invokes with retries,
      and records the final outcome via ``orchestrator.core.Orchestrator``
      (engine.py)

Scope note (Phase-06): this package is what makes ``Orchestrator.route()``'s
RUNNING state mean something -- see ADR-0002's Phase-04 follow-up ("Agent
adapters ... are required before route()'s RUNNING state means anything
beyond 'assigned.'") and ADR-0004 for the full design rationale.
"""

from orchestrator.execution.command_registry import AgentCommandRegistry
from orchestrator.execution.engine import ExecutionEngine
from orchestrator.execution.invoker import AgentInvoker, SubprocessAgentInvoker
from orchestrator.execution.models import AgentCommand, ExecutionResult, RetryPolicy

__all__ = [
    "AgentCommand",
    "ExecutionResult",
    "RetryPolicy",
    "AgentCommandRegistry",
    "AgentInvoker",
    "SubprocessAgentInvoker",
    "ExecutionEngine",
]
