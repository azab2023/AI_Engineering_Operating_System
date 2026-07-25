"""
orchestrator.prompts.prompt_manager
=======================================

``PromptManager``: the sole Facade ``SubprocessAgentInvoker`` and
``HttpAgentInvoker`` depend on for prompt resolution and rendering (see
ADR-0006 decision 4). Neither invoker talks to ``PromptRegistry`` or
``PromptRenderer`` directly -- they only ever call
``PromptManager.render()``.
"""

from __future__ import annotations

from orchestrator.exceptions import PromptNotAllowedForAgentError
from orchestrator.logging_setup import get_logger
from orchestrator.prompts.models import PromptDefinition, RenderedPrompt
from orchestrator.prompts.prompt_registry import PromptRegistry
from orchestrator.prompts.template_renderer import PromptRenderer, StringTemplateRenderer

logger = get_logger("prompts.prompt_manager")


class PromptManager:
    """Resolves a ``prompt_id`` for a given agent and renders it against
    supplied variables.

    Args:
        registry: source of validated ``PromptDefinition`` lookups.
            Defaults to a ``PromptRegistry`` loaded from the default
            ``prompts/prompt_registry.yaml`` path.
        renderer: the ``PromptRenderer`` implementation used to
            substitute variables. Defaults to ``StringTemplateRenderer``.
    """

    def __init__(
        self,
        registry: PromptRegistry | None = None,
        renderer: PromptRenderer | None = None,
    ):
        self._registry = registry or PromptRegistry()
        self._renderer = renderer or StringTemplateRenderer()

    def resolve(self, prompt_id: str, agent_name: str) -> PromptDefinition:
        """Return the ``PromptDefinition`` for ``prompt_id``, verifying
        that ``agent_name`` is allowed to use it.

        Raises:
            PromptNotFoundError: no entry exists for ``prompt_id``.
            PromptNotAllowedForAgentError: ``agent_name`` is not in the
                prompt definition's ``agents`` list.
        """
        definition = self._registry.get(prompt_id)
        if not definition.allows_agent(agent_name):
            raise PromptNotAllowedForAgentError(prompt_id, agent_name)
        return definition

    def render(
        self,
        prompt_id: str,
        agent_name: str,
        variables: dict[str, str] | None = None,
    ) -> RenderedPrompt:
        """Resolve ``prompt_id`` for ``agent_name`` and render it against
        ``variables``.

        Raises:
            PromptNotFoundError: no entry exists for ``prompt_id``.
            PromptNotAllowedForAgentError: ``agent_name`` is not allowed
                to use this prompt.
            MissingRequiredVariableError: a required variable is absent.
            UnknownVariableError: an undeclared variable was supplied.
        """
        definition = self.resolve(prompt_id, agent_name)
        template_text = self._registry.template_text(definition)
        rendered_text = self._renderer.render(definition, template_text, variables or {})

        logger.info(
            "Prompt rendered: prompt_id=%s agent=%s version=%s",
            prompt_id,
            agent_name,
            definition.version,
        )
        return RenderedPrompt(
            prompt_id=definition.prompt_id,
            version=definition.version,
            text=rendered_text,
        )
