"""Unit tests for orchestrator.prompts.prompt_manager.PromptManager.

Uses a FakeRegistry / FakeRenderer test double pair (same style as
FakeProviderRegistry in test_http_agent_invoker.py) to keep
PromptManager's own logic (resolve -> agent check -> render -> wrap)
under test in isolation, plus end-to-end tests against the real shipped
prompts/prompt_registry.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from orchestrator.exceptions import MissingRequiredVariableError, PromptNotAllowedForAgentError
from orchestrator.prompts.models import PromptDefinition, PromptVariable, RenderedPrompt
from orchestrator.prompts.prompt_manager import PromptManager
from orchestrator.prompts.prompt_registry import PromptRegistry


def _definition(agents=("codex",)) -> PromptDefinition:
    return PromptDefinition(
        prompt_id="foo",
        category="coding",
        purpose="test",
        agents=agents,
        priority="high",
        version="1.0",
        template_path="templates/t.md",
        variables=(PromptVariable(name="task_description", required=True),),
    )


@dataclass
class FakeRegistry:
    definition: PromptDefinition
    template: str = "Task: $task_description"

    def get(self, prompt_id: str) -> PromptDefinition:
        assert prompt_id == self.definition.prompt_id
        return self.definition

    def template_text(self, definition: PromptDefinition) -> str:
        return self.template


@dataclass
class FakeRenderer:
    calls: list = field(default_factory=list)

    def render(self, definition, template_text, variables) -> str:
        self.calls.append((definition.prompt_id, template_text, variables))
        return template_text.replace("$task_description", variables.get("task_description", ""))


# --------------------------------------------------------------------- #
# resolve()
# --------------------------------------------------------------------- #


def test_resolve_returns_definition_when_agent_allowed():
    manager = PromptManager(registry=FakeRegistry(_definition(agents=("codex", "aider"))))
    definition = manager.resolve("foo", "codex")
    assert definition.prompt_id == "foo"


def test_resolve_raises_when_agent_not_allowed():
    manager = PromptManager(registry=FakeRegistry(_definition(agents=("codex",))))
    with pytest.raises(PromptNotAllowedForAgentError) as exc_info:
        manager.resolve("foo", "gemini")
    assert exc_info.value.prompt_id == "foo"
    assert exc_info.value.agent_name == "gemini"


# --------------------------------------------------------------------- #
# render()
# --------------------------------------------------------------------- #


def test_render_returns_rendered_prompt_via_injected_renderer():
    definition = _definition(agents=("codex",))
    renderer = FakeRenderer()
    manager = PromptManager(registry=FakeRegistry(definition), renderer=renderer)

    result = manager.render("foo", "codex", {"task_description": "sort a list"})

    assert isinstance(result, RenderedPrompt)
    assert result.prompt_id == "foo"
    assert result.version == "1.0"
    assert result.text == "Task: sort a list"
    assert renderer.calls == [
        ("foo", "Task: $task_description", {"task_description": "sort a list"})
    ]


def test_render_with_none_variables_passes_empty_dict():
    definition = _definition(agents=("codex",))
    renderer = FakeRenderer()
    manager = PromptManager(registry=FakeRegistry(definition), renderer=renderer)

    manager.render("foo", "codex", None)

    assert renderer.calls[0][2] == {}


def test_render_propagates_agent_not_allowed_before_rendering():
    definition = _definition(agents=("codex",))
    renderer = FakeRenderer()
    manager = PromptManager(registry=FakeRegistry(definition), renderer=renderer)

    with pytest.raises(PromptNotAllowedForAgentError):
        manager.render("foo", "gemini", {"task_description": "x"})

    assert renderer.calls == []


# --------------------------------------------------------------------- #
# End-to-end against the real shipped prompts/prompt_registry.yaml
# --------------------------------------------------------------------- #


def test_end_to_end_render_against_real_registry():
    manager = PromptManager(registry=PromptRegistry())
    result = manager.render(
        "code_generation", "codex", {"task_description": "add two numbers", "language": "Python"}
    )
    assert "add two numbers" in result.text
    assert "Python" in result.text
    assert result.prompt_id == "code_generation"


def test_end_to_end_missing_required_variable_raises():
    manager = PromptManager(registry=PromptRegistry())
    with pytest.raises(MissingRequiredVariableError):
        manager.render("code_generation", "codex", {})


def test_end_to_end_disallowed_agent_raises():
    manager = PromptManager(registry=PromptRegistry())
    with pytest.raises(PromptNotAllowedForAgentError):
        manager.render("code_generation", "gemini", {"task_description": "x"})
