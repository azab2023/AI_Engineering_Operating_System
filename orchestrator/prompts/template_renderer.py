"""
orchestrator.prompts.template_renderer
==========================================

Defines ``PromptRenderer``, the Port (Strategy/Protocol pattern) a
template-rendering implementation must satisfy, plus
``StringTemplateRenderer``, the sole concrete implementation for
Phase-08.

This mirrors ``ModelProvider`` (Phase-07, ``orchestrator.providers.
provider``) one layer over: ``PromptManager`` (see ``prompt_manager.py``)
depends only on this Protocol, never on ``StringTemplateRenderer``
directly, so a future renderer (e.g. a Jinja2-backed one, if a template
ever needs conditionals/loops -- see ADR-0006 Follow-up) can be added
without modifying ``PromptManager``.

Variable-substitution rules (fail-loudly, per ADR-0006 decision 8):
    - Every variable declared ``required: true`` on the
      ``PromptDefinition`` must be present in the variables mapping
      passed to ``render()``, or ``MissingRequiredVariableError`` is
      raised.
    - Every variable key passed to ``render()`` must be declared on the
      ``PromptDefinition`` (required or optional), or
      ``UnknownVariableError`` is raised. A typo'd variable name is
      never silently dropped.
"""

from __future__ import annotations

from string import Template
from typing import Protocol

from orchestrator.exceptions import MissingRequiredVariableError, UnknownVariableError
from orchestrator.prompts.models import PromptDefinition


class PromptRenderer(Protocol):
    """Port: something that can substitute variables into template text."""

    def render(
        self,
        definition: PromptDefinition,
        template_text: str,
        variables: dict[str, str],
    ) -> str:
        """Return ``template_text`` with every variable substituted.

        Raises:
            MissingRequiredVariableError: a variable declared
                ``required: true`` on ``definition`` is absent from
                ``variables``.
            UnknownVariableError: ``variables`` contains a key not
                declared on ``definition`` at all.
        """
        ...


class StringTemplateRenderer:
    """``PromptRenderer`` implementation using stdlib ``string.Template``
    (``$variable`` / ``${variable}`` substitution only -- no
    conditionals, no loops; see ADR-0006 decision 2)."""

    def render(
        self,
        definition: PromptDefinition,
        template_text: str,
        variables: dict[str, str],
    ) -> str:
        declared = definition.declared_variable_names()
        supplied = set(variables.keys())

        unknown = supplied - declared
        if unknown:
            raise UnknownVariableError(definition.prompt_id, sorted(unknown)[0])

        missing_required = definition.required_variable_names() - supplied
        if missing_required:
            raise MissingRequiredVariableError(definition.prompt_id, sorted(missing_required)[0])

        # safe_substitute (not substitute): an optional variable that was
        # not supplied should not raise -- required/unknown variables are
        # already validated explicitly above, so this is purely about not
        # crashing on an omitted *optional* placeholder.
        return Template(template_text).safe_substitute(variables)
