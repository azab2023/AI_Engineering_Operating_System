"""Unit tests for orchestrator.prompts.template_renderer.StringTemplateRenderer."""

from __future__ import annotations

import pytest

from orchestrator.exceptions import MissingRequiredVariableError, UnknownVariableError
from orchestrator.prompts.models import PromptDefinition, PromptVariable
from orchestrator.prompts.template_renderer import StringTemplateRenderer


def _definition(variables) -> PromptDefinition:
    return PromptDefinition(
        prompt_id="test_prompt",
        category="coding",
        purpose="test",
        agents=("codex",),
        priority="high",
        version="1.0",
        template_path="templates/coding/code_generation.md",
        variables=variables,
    )


def test_render_substitutes_all_variables():
    definition = _definition(
        (
            PromptVariable(name="task_description", required=True),
            PromptVariable(name="language", required=False),
        )
    )
    renderer = StringTemplateRenderer()
    result = renderer.render(
        definition,
        "Task: $task_description in $language",
        {"task_description": "sort a list", "language": "Python"},
    )
    assert result == "Task: sort a list in Python"


def test_render_leaves_omitted_optional_variable_untouched():
    definition = _definition(
        (
            PromptVariable(name="task_description", required=True),
            PromptVariable(name="language", required=False),
        )
    )
    renderer = StringTemplateRenderer()
    result = renderer.render(
        definition, "Task: $task_description ($language)", {"task_description": "x"}
    )
    assert result == "Task: x ($language)"


def test_render_raises_on_missing_required_variable():
    definition = _definition((PromptVariable(name="task_description", required=True),))
    renderer = StringTemplateRenderer()

    with pytest.raises(MissingRequiredVariableError) as exc_info:
        renderer.render(definition, "$task_description", {})

    assert exc_info.value.prompt_id == "test_prompt"
    assert exc_info.value.variable_name == "task_description"


def test_render_raises_on_unknown_variable():
    definition = _definition((PromptVariable(name="task_description", required=True),))
    renderer = StringTemplateRenderer()

    with pytest.raises(UnknownVariableError) as exc_info:
        renderer.render(definition, "$task_description", {"task_description": "x", "bogus": "y"})

    assert exc_info.value.variable_name == "bogus"


def test_unknown_variable_checked_before_missing_required():
    """An undeclared variable is rejected even if a required one is also
    missing -- both are configuration errors, but 'you passed something
    that doesn't exist' is checked first."""
    definition = _definition((PromptVariable(name="task_description", required=True),))
    renderer = StringTemplateRenderer()

    with pytest.raises(UnknownVariableError):
        renderer.render(definition, "$task_description", {"bogus": "y"})
