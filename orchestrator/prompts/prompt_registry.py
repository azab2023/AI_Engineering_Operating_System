"""
orchestrator.prompts.prompt_registry
========================================

Loads and validates ``prompts/prompt_registry.yaml`` and exposes typed
lookup of each prompt's definition.

Responsibility boundary (ADR-0006 decision 3, mirroring ADR-0005
decision 3 for ``ModelProviderRegistry``): this module is responsible
for **configuration loading, validation, and lookup only**. It never
renders a template and never inspects an ``Agent`` or ``AgentTask`` --
that is ``PromptManager``'s job (see ``prompt_manager.py``).

Duplicate-key guard: ``yaml.safe_load`` silently keeps the *last* value
of a repeated top-level mapping key rather than raising -- this is the
exact failure mode described in ``orchestrator.exceptions``'s module
docstring that once corrupted this file. ``_DuplicateKeyGuardLoader``
below overrides ``construct_mapping`` to raise ``DuplicatePromptKeyError``
the moment a duplicate key is encountered, so this phase closes that gap
by construction rather than by convention.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from orchestrator.exceptions import (
    DuplicatePromptKeyError,
    PromptNotFoundError,
    PromptRegistryError,
    PromptTemplateFileMissingError,
)
from orchestrator.logging_setup import get_logger
from orchestrator.prompts.models import PromptDefinition, PromptVariable

logger = get_logger("prompts.prompt_registry")

_REQUIRED_FIELDS = {
    "category",
    "purpose",
    "agents",
    "priority",
    "version",
    "template_path",
}

DEFAULT_PROMPT_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent.parent / "prompts" / "prompt_registry.yaml"
)


class _DuplicateKeyGuardLoader(yaml.SafeLoader):
    """A ``SafeLoader`` that raises on a duplicate mapping key instead of
    silently keeping the last value (PyYAML's default behavior)."""


def _construct_mapping_no_duplicates(
    loader: yaml.SafeLoader, node: yaml.MappingNode
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise DuplicatePromptKeyError(str(key))
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


_DuplicateKeyGuardLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_duplicates,
)


class PromptRegistry:
    """In-memory, validated view of ``prompts/prompt_registry.yaml``.

    Configuration loading, validation, and per-prompt lookup only -- see
    the module docstring above. Rendering a looked-up
    ``PromptDefinition`` is ``PromptManager`` / ``PromptRenderer``'s
    responsibility, not this class's.
    """

    def __init__(self, registry_path: str | Path = DEFAULT_PROMPT_REGISTRY_PATH):
        self._registry_path = Path(registry_path)
        self._definitions: dict[str, PromptDefinition] = {}
        self._load()

    def _load(self) -> None:
        if not self._registry_path.exists():
            raise PromptRegistryError(f"Prompt registry file not found: {self._registry_path}")

        try:
            raw_text = self._registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PromptRegistryError(
                f"Could not read prompt registry file: {self._registry_path}"
            ) from exc

        try:
            data = yaml.load(raw_text, Loader=_DuplicateKeyGuardLoader)
        except DuplicatePromptKeyError:
            raise
        except yaml.YAMLError as exc:
            raise PromptRegistryError(
                f"Prompt registry file is not valid YAML: {self._registry_path}\n{exc}"
            ) from exc

        if not isinstance(data, dict) or "prompts" not in data:
            raise PromptRegistryError(
                "Prompt registry file must be a mapping with a top-level 'prompts' key"
            )

        prompts_data = data["prompts"]
        if not isinstance(prompts_data, dict) or not prompts_data:
            raise PromptRegistryError(
                "Prompt registry file 'prompts' key must be a non-empty mapping"
            )

        template_root = self._registry_path.parent
        for prompt_id, entry in prompts_data.items():
            self._definitions[prompt_id] = self._parse_entry(prompt_id, entry, template_root)

        logger.info(
            "Loaded prompt registry: %d prompt(s) from %s",
            len(self._definitions),
            self._registry_path,
        )

    def _parse_entry(self, prompt_id: str, entry: Any, template_root: Path) -> PromptDefinition:
        if not isinstance(entry, dict):
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r} must be a mapping, got {type(entry).__name__}"
            )

        missing = _REQUIRED_FIELDS - entry.keys()
        if missing:
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r} is missing required field(s): {sorted(missing)}"
            )

        category = entry["category"]
        if not isinstance(category, str) or not category.strip():
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r}: 'category' must be a non-empty string"
            )

        purpose = entry["purpose"]
        if not isinstance(purpose, str) or not purpose.strip():
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r}: 'purpose' must be a non-empty string"
            )

        agents = entry["agents"]
        if (
            not isinstance(agents, list)
            or not agents
            or not all(isinstance(a, str) for a in agents)
        ):
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r}: 'agents' must be a non-empty list of strings"
            )

        priority = entry["priority"]
        if not isinstance(priority, str) or not priority.strip():
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r}: 'priority' must be a non-empty string"
            )

        version = entry["version"]
        if not isinstance(version, str) or not version.strip():
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r}: 'version' must be a non-empty string"
            )

        template_path = entry["template_path"]
        if not isinstance(template_path, str) or not template_path.strip():
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r}: 'template_path' must be a non-empty string"
            )

        resolved_template_path = (template_root / template_path).resolve()
        if not resolved_template_path.is_file():
            raise PromptTemplateFileMissingError(prompt_id, template_path)

        variables_data = entry.get("variables", [])
        if not isinstance(variables_data, list):
            raise PromptRegistryError(f"Prompt entry for {prompt_id!r}: 'variables' must be a list")

        variables = tuple(
            self._parse_variable(prompt_id, index, item)
            for index, item in enumerate(variables_data)
        )

        return PromptDefinition(
            prompt_id=prompt_id,
            category=category,
            purpose=purpose,
            agents=tuple(agents),
            priority=priority,
            version=version,
            template_path=template_path,
            variables=variables,
        )

    def _parse_variable(self, prompt_id: str, index: int, item: Any) -> PromptVariable:
        if not isinstance(item, dict):
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r}: variables[{index}] must be a mapping"
            )

        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r}: variables[{index}].name must be non-empty"
            )

        required = item.get("required")
        if not isinstance(required, bool):
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r}: variables[{index}].required must be a boolean"
            )

        description = item.get("description", "")
        if not isinstance(description, str):
            raise PromptRegistryError(
                f"Prompt entry for {prompt_id!r}: variables[{index}].description must be a string"
            )

        return PromptVariable(name=name, required=required, description=description)

    def get(self, prompt_id: str) -> PromptDefinition:
        """Return the validated ``PromptDefinition`` for ``prompt_id``.

        Raises:
            PromptNotFoundError: no entry exists for ``prompt_id``.
        """
        try:
            return self._definitions[prompt_id]
        except KeyError as exc:
            raise PromptNotFoundError(prompt_id) from exc

    def template_text(self, definition: PromptDefinition) -> str:
        """Read and return the raw template text for ``definition``."""
        template_root = self._registry_path.parent
        resolved_path = (template_root / definition.template_path).resolve()
        try:
            return resolved_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PromptTemplateFileMissingError(
                definition.prompt_id, definition.template_path
            ) from exc

    def __len__(self) -> int:
        return len(self._definitions)

    def __contains__(self, prompt_id: str) -> bool:
        return prompt_id in self._definitions
