"""Unit tests for orchestrator.prompts.prompt_registry.PromptRegistry."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import (
    DuplicatePromptKeyError,
    PromptNotFoundError,
    PromptRegistryError,
    PromptTemplateFileMissingError,
)
from orchestrator.prompts.prompt_registry import DEFAULT_PROMPT_REGISTRY_PATH, PromptRegistry


def _write_registry(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "prompt_registry.yaml"
    path.write_text(textwrap.dedent(body))
    return path


def _make_template(tmp_path: Path, relative_path: str = "templates/t.md") -> None:
    template_path = tmp_path / relative_path
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text("Hello $name")


# --------------------------------------------------------------------- #
# Against the real, shipped prompts/prompt_registry.yaml
# --------------------------------------------------------------------- #


def test_real_prompt_registry_file_exists():
    assert DEFAULT_PROMPT_REGISTRY_PATH.exists(), (
        f"Expected prompt registry file at {DEFAULT_PROMPT_REGISTRY_PATH}"
    )


def test_real_prompt_registry_loads_all_seven_prompts():
    registry = PromptRegistry(DEFAULT_PROMPT_REGISTRY_PATH)
    expected = {
        "architecture_review",
        "code_generation",
        "code_refactoring",
        "debugging",
        "testing",
        "documentation",
        "automation_design",
    }
    assert len(registry) == 7
    for prompt_id in expected:
        assert prompt_id in registry


def test_real_prompt_registry_entries_reference_existing_templates():
    registry = PromptRegistry(DEFAULT_PROMPT_REGISTRY_PATH)
    for prompt_id in (
        "architecture_review",
        "code_generation",
        "code_refactoring",
        "debugging",
        "testing",
        "documentation",
        "automation_design",
    ):
        definition = registry.get(prompt_id)
        text = registry.template_text(definition)
        assert text.strip() != ""


# --------------------------------------------------------------------- #
# Loading / validation failures
# --------------------------------------------------------------------- #


def test_missing_file_raises_prompt_registry_error(tmp_path: Path):
    with pytest.raises(PromptRegistryError):
        PromptRegistry(tmp_path / "does_not_exist.yaml")


def test_duplicate_top_level_key_raises(tmp_path: Path):
    _make_template(tmp_path)
    body = """\
    prompts:
      foo:
        category: coding
        purpose: test
        agents: [codex]
        priority: high
        version: "1.0"
        template_path: templates/t.md
      foo:
        category: coding
        purpose: test again
        agents: [codex]
        priority: high
        version: "2.0"
        template_path: templates/t.md
    """
    path = _write_registry(tmp_path, body)
    with pytest.raises(DuplicatePromptKeyError) as exc_info:
        PromptRegistry(path)
    assert exc_info.value.prompt_id == "foo"


def test_missing_prompts_key_raises(tmp_path: Path):
    path = _write_registry(tmp_path, "not_prompts: {}\n")
    with pytest.raises(PromptRegistryError):
        PromptRegistry(path)


def test_empty_prompts_mapping_raises(tmp_path: Path):
    path = _write_registry(tmp_path, "prompts: {}\n")
    with pytest.raises(PromptRegistryError):
        PromptRegistry(path)


def test_entry_missing_required_field_raises(tmp_path: Path):
    _make_template(tmp_path)
    body = """\
    prompts:
      foo:
        category: coding
        purpose: test
        agents: [codex]
        priority: high
        template_path: templates/t.md
    """
    path = _write_registry(tmp_path, body)
    with pytest.raises(PromptRegistryError, match="version"):
        PromptRegistry(path)


def test_entry_with_non_list_agents_raises(tmp_path: Path):
    _make_template(tmp_path)
    body = """\
    prompts:
      foo:
        category: coding
        purpose: test
        agents: codex
        priority: high
        version: "1.0"
        template_path: templates/t.md
    """
    path = _write_registry(tmp_path, body)
    with pytest.raises(PromptRegistryError):
        PromptRegistry(path)


def test_missing_template_file_raises(tmp_path: Path):
    body = """\
    prompts:
      foo:
        category: coding
        purpose: test
        agents: [codex]
        priority: high
        version: "1.0"
        template_path: templates/does_not_exist.md
    """
    path = _write_registry(tmp_path, body)
    with pytest.raises(PromptTemplateFileMissingError):
        PromptRegistry(path)


def test_variable_missing_required_key_raises(tmp_path: Path):
    _make_template(tmp_path)
    body = """\
    prompts:
      foo:
        category: coding
        purpose: test
        agents: [codex]
        priority: high
        version: "1.0"
        template_path: templates/t.md
        variables:
          - name: task_description
    """
    path = _write_registry(tmp_path, body)
    with pytest.raises(PromptRegistryError):
        PromptRegistry(path)


# --------------------------------------------------------------------- #
# Successful load + lookup
# --------------------------------------------------------------------- #


def test_valid_registry_loads_and_lookup_succeeds(tmp_path: Path):
    _make_template(tmp_path)
    body = """\
    prompts:
      foo:
        category: coding
        purpose: test
        agents: [codex, aider]
        priority: high
        version: "1.0"
        template_path: templates/t.md
        variables:
          - name: name
            required: true
            description: who to greet
    """
    path = _write_registry(tmp_path, body)
    registry = PromptRegistry(path)

    assert len(registry) == 1
    assert "foo" in registry
    definition = registry.get("foo")
    assert definition.prompt_id == "foo"
    assert definition.agents == ("codex", "aider")
    assert definition.variables[0].name == "name"
    assert definition.variables[0].required is True


def test_variables_defaults_to_empty_list_when_omitted(tmp_path: Path):
    _make_template(tmp_path)
    body = """\
    prompts:
      foo:
        category: coding
        purpose: test
        agents: [codex]
        priority: high
        version: "1.0"
        template_path: templates/t.md
    """
    path = _write_registry(tmp_path, body)
    registry = PromptRegistry(path)
    assert registry.get("foo").variables == ()


def test_get_unknown_prompt_raises_prompt_not_found_error(tmp_path: Path):
    _make_template(tmp_path)
    body = """\
    prompts:
      foo:
        category: coding
        purpose: test
        agents: [codex]
        priority: high
        version: "1.0"
        template_path: templates/t.md
    """
    path = _write_registry(tmp_path, body)
    registry = PromptRegistry(path)

    with pytest.raises(PromptNotFoundError):
        registry.get("bar")


def test_template_text_reads_file_contents(tmp_path: Path):
    _make_template(tmp_path)
    body = """\
    prompts:
      foo:
        category: coding
        purpose: test
        agents: [codex]
        priority: high
        version: "1.0"
        template_path: templates/t.md
    """
    path = _write_registry(tmp_path, body)
    registry = PromptRegistry(path)
    definition = registry.get("foo")
    assert registry.template_text(definition) == "Hello $name"


def test_yaml_safe_dump_roundtrip_is_readable(tmp_path: Path):
    """Regression guard, matching the project-wide convention of
    generating YAML config via yaml.safe_dump rather than f-string
    interpolation (a prior test bug -- see project learnings)."""
    _make_template(tmp_path)
    data = {
        "prompts": {
            "foo": {
                "category": "coding",
                "purpose": "test; rm -rf $HOME",
                "agents": ["codex"],
                "priority": "high",
                "version": "1.0",
                "template_path": "templates/t.md",
            }
        }
    }
    path = tmp_path / "prompt_registry.yaml"
    path.write_text(yaml.safe_dump(data))
    registry = PromptRegistry(path)
    assert registry.get("foo").purpose == "test; rm -rf $HOME"
