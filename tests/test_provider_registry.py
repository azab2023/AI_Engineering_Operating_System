"""Unit tests for orchestrator.providers.provider_registry.ModelProviderRegistry."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator.exceptions import (
    ModelProviderRegistryError,
    ProviderConfigNotFoundError,
    ProviderDisabledError,
)
from orchestrator.providers.provider_registry import (
    DEFAULT_MODEL_PROVIDERS_PATH,
    ModelProviderRegistry,
)

# --------------------------------------------------------------------- #
# Against the real, shipped config/model_providers.yaml
# --------------------------------------------------------------------- #


def test_real_model_providers_file_exists():
    assert DEFAULT_MODEL_PROVIDERS_PATH.exists(), (
        f"Expected model providers file at {DEFAULT_MODEL_PROVIDERS_PATH}"
    )


def test_real_model_providers_cover_all_registry_agents():
    registry = ModelProviderRegistry(DEFAULT_MODEL_PROVIDERS_PATH)
    for expected_name in ("claude_code", "codex", "aider", "gemini"):
        assert expected_name in registry


def test_real_model_providers_enabled_entries_are_resolvable():
    registry = ModelProviderRegistry(DEFAULT_MODEL_PROVIDERS_PATH)
    for expected_name in ("claude_code", "codex", "gemini"):
        config = registry.get_config(expected_name)
        assert config.provider_type
        assert config.base_url
        assert config.model
        assert config.api_key_env_var
        assert config.timeout_seconds > 0


def test_real_model_providers_aider_is_disabled():
    registry = ModelProviderRegistry(DEFAULT_MODEL_PROVIDERS_PATH)
    assert registry.is_enabled("aider") is False
    with pytest.raises(ProviderDisabledError):
        registry.get_config("aider")


# --------------------------------------------------------------------- #
# Validation, against temp files
# --------------------------------------------------------------------- #


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "model_providers.yaml"
    path.write_text(textwrap.dedent(content))
    return path


def _valid_yaml() -> str:
    return """\
        providers:
          claude_code:
            provider_type: anthropic
            enabled: true
            base_url: https://api.anthropic.com/v1/messages
            model: claude-sonnet-4-6
            api_key_env_var: ANTHROPIC_API_KEY
            timeout_seconds: 300

          codex:
            provider_type: openai
            enabled: false
            base_url: https://api.openai.com/v1/chat/completions
            model: gpt-4.1
            api_key_env_var: OPENAI_API_KEY
            timeout_seconds: 120
        """


def test_missing_file_raises(tmp_path: Path):
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(ModelProviderRegistryError, match="not found"):
        ModelProviderRegistry(missing)


def test_invalid_yaml_raises(tmp_path: Path):
    path = _write(tmp_path, "providers: [this, is, not, a, mapping, :::")
    with pytest.raises(ModelProviderRegistryError, match="not valid YAML"):
        ModelProviderRegistry(path)


def test_missing_top_level_providers_key_raises(tmp_path: Path):
    path = _write(tmp_path, "not_providers:\n  foo: bar\n")
    with pytest.raises(ModelProviderRegistryError, match="top-level 'providers' key"):
        ModelProviderRegistry(path)


def test_empty_providers_mapping_raises(tmp_path: Path):
    path = _write(tmp_path, "providers: {}\n")
    with pytest.raises(ModelProviderRegistryError, match="non-empty mapping"):
        ModelProviderRegistry(path)


def test_providers_not_a_mapping_raises(tmp_path: Path):
    path = _write(tmp_path, "providers: [claude_code, codex]\n")
    with pytest.raises(ModelProviderRegistryError, match="non-empty mapping"):
        ModelProviderRegistry(path)


def test_entry_not_a_mapping_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        providers:
          claude_code: "not a mapping"
        """,
    )
    with pytest.raises(ModelProviderRegistryError, match="must be a mapping"):
        ModelProviderRegistry(path)


@pytest.mark.parametrize(
    "missing_field",
    ["provider_type", "enabled", "base_url", "model", "api_key_env_var", "timeout_seconds"],
)
def test_missing_required_field_raises(tmp_path: Path, missing_field: str):
    fields = {
        "provider_type": "anthropic",
        "enabled": "true",
        "base_url": "https://api.anthropic.com/v1/messages",
        "model": "claude-sonnet-4-6",
        "api_key_env_var": "ANTHROPIC_API_KEY",
        "timeout_seconds": "300",
    }
    del fields[missing_field]
    body = "\n".join(f"    {key}: {value}" for key, value in fields.items())
    path = _write(tmp_path, f"providers:\n  claude_code:\n{body}\n")
    with pytest.raises(ModelProviderRegistryError, match="missing required"):
        ModelProviderRegistry(path)


def test_blank_provider_type_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        providers:
          claude_code:
            provider_type: "  "
            enabled: true
            base_url: https://api.anthropic.com/v1/messages
            model: claude-sonnet-4-6
            api_key_env_var: ANTHROPIC_API_KEY
            timeout_seconds: 300
        """,
    )
    with pytest.raises(ModelProviderRegistryError, match="provider_type"):
        ModelProviderRegistry(path)


def test_non_boolean_enabled_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        providers:
          claude_code:
            provider_type: anthropic
            enabled: "yes"
            base_url: https://api.anthropic.com/v1/messages
            model: claude-sonnet-4-6
            api_key_env_var: ANTHROPIC_API_KEY
            timeout_seconds: 300
        """,
    )
    with pytest.raises(ModelProviderRegistryError, match="'enabled' must be a boolean"):
        ModelProviderRegistry(path)


def test_non_positive_timeout_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        providers:
          claude_code:
            provider_type: anthropic
            enabled: true
            base_url: https://api.anthropic.com/v1/messages
            model: claude-sonnet-4-6
            api_key_env_var: ANTHROPIC_API_KEY
            timeout_seconds: 0
        """,
    )
    with pytest.raises(ModelProviderRegistryError, match="positive number"):
        ModelProviderRegistry(path)


def test_non_numeric_timeout_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """\
        providers:
          claude_code:
            provider_type: anthropic
            enabled: true
            base_url: https://api.anthropic.com/v1/messages
            model: claude-sonnet-4-6
            api_key_env_var: ANTHROPIC_API_KEY
            timeout_seconds: "fast"
        """,
    )
    with pytest.raises(ModelProviderRegistryError, match="must be a number"):
        ModelProviderRegistry(path)


# --------------------------------------------------------------------- #
# Lookup behavior (get_config / is_enabled / __contains__ / __len__)
# --------------------------------------------------------------------- #


def test_get_config_returns_provider_config(tmp_path: Path):
    registry = ModelProviderRegistry(_write(tmp_path, _valid_yaml()))
    config = registry.get_config("claude_code")
    assert config.provider_type == "anthropic"
    assert config.enabled is True
    assert config.model == "claude-sonnet-4-6"
    assert config.timeout_seconds == 300.0


def test_get_config_unknown_agent_raises_not_found(tmp_path: Path):
    registry = ModelProviderRegistry(_write(tmp_path, _valid_yaml()))
    with pytest.raises(ProviderConfigNotFoundError):
        registry.get_config("no_such_agent")


def test_get_config_disabled_agent_raises_disabled(tmp_path: Path):
    registry = ModelProviderRegistry(_write(tmp_path, _valid_yaml()))
    with pytest.raises(ProviderDisabledError):
        registry.get_config("codex")


def test_is_enabled_true_for_enabled_agent(tmp_path: Path):
    registry = ModelProviderRegistry(_write(tmp_path, _valid_yaml()))
    assert registry.is_enabled("claude_code") is True


def test_is_enabled_false_for_disabled_agent(tmp_path: Path):
    registry = ModelProviderRegistry(_write(tmp_path, _valid_yaml()))
    assert registry.is_enabled("codex") is False


def test_is_enabled_false_for_unknown_agent(tmp_path: Path):
    registry = ModelProviderRegistry(_write(tmp_path, _valid_yaml()))
    assert registry.is_enabled("no_such_agent") is False


def test_contains_and_len(tmp_path: Path):
    registry = ModelProviderRegistry(_write(tmp_path, _valid_yaml()))
    assert "claude_code" in registry
    assert "codex" in registry
    assert "no_such_agent" not in registry
    assert len(registry) == 2
