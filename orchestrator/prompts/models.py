"""
orchestrator.prompts.models
==============================

Data models for Phase-08 (Prompt Management System).

Design notes:
    - Plain, frozen dataclasses only, matching the convention already
      established in ``orchestrator.models`` (Phase-04),
      ``orchestrator.execution.models`` (Phase-06), and
      ``orchestrator.providers.models`` (Phase-07) -- no pydantic / ORM /
      external validation libraries.
    - ``PromptDefinition`` is the validated, in-memory representation of
      one entry in ``prompts/prompt_registry.yaml``, produced by
      ``PromptRegistry`` (see ``prompt_registry.py``).
    - ``RenderedPrompt`` is the terminal output of the prompt-management
      pipeline: the exact text that replaces ``AgentTask.description``
      when an invoker resolves and renders a prompt (see ADR-0006
      decision 6). It deliberately carries no variables or template
      metadata -- once rendered, a prompt is just text plus enough
      identity (``prompt_id``, ``version``) to trace it back to its
      source.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptVariable:
    """One variable a prompt template may reference.

    Attributes:
        name: the variable name as it appears in the template (without
            the ``$`` / ``${}`` substitution markers).
        required: whether a render call must supply this variable.
        description: human-readable purpose, for documentation only.
    """

    name: str
    required: bool
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("PromptVariable.name must be a non-empty string")


@dataclass(frozen=True)
class PromptDefinition:
    """A validated prompt entry, loaded from
    ``prompts/prompt_registry.yaml`` by ``PromptRegistry``.

    Attributes:
        prompt_id: unique identifier (the entry's top-level YAML key).
        category: grouping label (e.g. ``"coding"``, ``"debugging"``);
            mirrors the ``prompts/templates/<category>/`` directory
            layout.
        purpose: human-readable one-line description.
        agents: agent names (matching ``config/agent_registry.yaml``
            identifiers, e.g. ``"claude_code"``, ``"codex"``) allowed to
            use this prompt. Enforced by ``PromptManager.resolve()``.
        priority: ``"high"`` | ``"medium"`` | ``"low"``, documentation
            only in this phase (no scheduling behavior depends on it).
        version: free-form version string for this prompt's content.
            Documentation only in this phase -- see ADR-0006 Follow-up.
        template_path: path (relative to the prompt registry file's
            directory) to the template file, verified to exist by
            ``PromptRegistry`` at load time.
        variables: the full set of variables this template may
            reference. Rendering rejects both a missing ``required``
            variable and an undeclared one -- see
            ``MissingRequiredVariableError`` / ``UnknownVariableError``.
    """

    prompt_id: str
    category: str
    purpose: str
    agents: tuple[str, ...]
    priority: str
    version: str
    template_path: str
    variables: tuple[PromptVariable, ...]

    def __post_init__(self) -> None:
        if not self.prompt_id or not self.prompt_id.strip():
            raise ValueError("PromptDefinition.prompt_id must be a non-empty string")
        if not self.category or not self.category.strip():
            raise ValueError("PromptDefinition.category must be a non-empty string")
        if not self.purpose or not self.purpose.strip():
            raise ValueError("PromptDefinition.purpose must be a non-empty string")
        if not self.agents:
            raise ValueError(f"PromptDefinition {self.prompt_id!r} must list at least one agent")
        if not self.priority or not self.priority.strip():
            raise ValueError("PromptDefinition.priority must be a non-empty string")
        if not self.version or not self.version.strip():
            raise ValueError("PromptDefinition.version must be a non-empty string")
        if not self.template_path or not self.template_path.strip():
            raise ValueError("PromptDefinition.template_path must be a non-empty string")

    def allows_agent(self, agent_name: str) -> bool:
        return agent_name in self.agents

    def required_variable_names(self) -> frozenset[str]:
        return frozenset(v.name for v in self.variables if v.required)

    def declared_variable_names(self) -> frozenset[str]:
        return frozenset(v.name for v in self.variables)


@dataclass(frozen=True)
class RenderedPrompt:
    """The terminal output of ``PromptManager.render()`` -- the text an
    invoker sends to an agent in place of a raw ``AgentTask.description``.
    """

    prompt_id: str
    version: str
    text: str

    def __post_init__(self) -> None:
        if not self.prompt_id or not self.prompt_id.strip():
            raise ValueError("RenderedPrompt.prompt_id must be a non-empty string")
        if not self.version or not self.version.strip():
            raise ValueError("RenderedPrompt.version must be a non-empty string")
