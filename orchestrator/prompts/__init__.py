"""
orchestrator.prompts
=======================

Phase-08 Prompt Management System for the AI_Engineering_Operating_System.

This package provides:
    - ``PromptVariable`` / ``PromptDefinition`` / ``RenderedPrompt`` data
      models (models.py)
    - The ``PromptRenderer`` port (template_renderer.py) and its
      ``StringTemplateRenderer`` implementation
    - ``PromptRegistry``, which loads and validates
      ``prompts/prompt_registry.yaml`` and resolves a ``prompt_id`` to a
      validated ``PromptDefinition``
    - ``PromptManager``, the Facade that combines registry lookup and
      rendering, and is the only entry point
      ``orchestrator.execution.invoker.SubprocessAgentInvoker`` /
      ``orchestrator.execution.http_invoker.HttpAgentInvoker`` depend on

Scope note (Phase-08): this package turns a ``(prompt_id, variables)``
pair into a final prompt string, replacing a raw ``AgentTask.description``
when ``AgentTask.prompt_id`` is set. See ADR-0006 for the full design
rationale, including why prompt resolution happens inside each
``AgentInvoker`` rather than in ``Orchestrator`` or ``ExecutionEngine``.
"""

from orchestrator.prompts.models import PromptDefinition, PromptVariable, RenderedPrompt
from orchestrator.prompts.prompt_manager import PromptManager
from orchestrator.prompts.prompt_registry import PromptRegistry
from orchestrator.prompts.template_renderer import PromptRenderer, StringTemplateRenderer

__all__ = [
    "PromptVariable",
    "PromptDefinition",
    "RenderedPrompt",
    "PromptRenderer",
    "StringTemplateRenderer",
    "PromptRegistry",
    "PromptManager",
]
