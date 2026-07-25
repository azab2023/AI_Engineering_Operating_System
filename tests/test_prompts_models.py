"""Unit tests for orchestrator.prompts.models."""

from __future__ import annotations

import pytest

from orchestrator.prompts.models import PromptDefinition, PromptVariable, RenderedPrompt


def _variable(name: str = "task_description", required: bool = True) -> PromptVariable:
    return PromptVariable(name=name, required=required)


def _definition(**overrides) -> PromptDefinition:
    defaults = dict(
        prompt_id="code_generation",
        category="coding",
        purpose="Generate code",
        agents=("codex", "aider"),
        priority="high",
        version="1.0",
        template_path="templates/coding/code_generation.md",
        variables=(_variable(),),
    )
    defaults.update(overrides)
    return PromptDefinition(**defaults)


# --------------------------------------------------------------------- #
# PromptVariable
# --------------------------------------------------------------------- #


def test_prompt_variable_rejects_empty_name():
    with pytest.raises(ValueError):
        PromptVariable(name="", required=True)


# --------------------------------------------------------------------- #
# PromptDefinition validation
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "field_name",
    ["prompt_id", "category", "purpose", "priority", "version", "template_path"],
)
def test_prompt_definition_rejects_empty_required_string_fields(field_name: str):
    with pytest.raises(ValueError):
        _definition(**{field_name: ""})


def test_prompt_definition_rejects_empty_agents():
    with pytest.raises(ValueError):
        _definition(agents=())


def test_prompt_definition_allows_agent():
    definition = _definition(agents=("codex", "aider"))
    assert definition.allows_agent("codex")
    assert not definition.allows_agent("gemini")


def test_prompt_definition_required_and_declared_variable_names():
    definition = _definition(
        variables=(
            _variable("task_description", required=True),
            _variable("language", required=False),
        )
    )
    assert definition.required_variable_names() == frozenset({"task_description"})
    assert definition.declared_variable_names() == frozenset({"task_description", "language"})


# --------------------------------------------------------------------- #
# RenderedPrompt
# --------------------------------------------------------------------- #


def test_rendered_prompt_rejects_empty_prompt_id():
    with pytest.raises(ValueError):
        RenderedPrompt(prompt_id="", version="1.0", text="hello")


def test_rendered_prompt_rejects_empty_version():
    with pytest.raises(ValueError):
        RenderedPrompt(prompt_id="x", version="", text="hello")


def test_rendered_prompt_holds_text():
    rendered = RenderedPrompt(prompt_id="x", version="1.0", text="hello world")
    assert rendered.text == "hello world"
