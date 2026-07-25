"""Unit tests for orchestrator.execution.http_invoker.HttpAgentInvoker.

Uses a FakeProviderRegistry test double (same style as FakeAgentInvoker
in test_execution_engine.py) so these tests never touch
config/model_providers.yaml on disk, and httpx.MockTransport so no real
network call is ever made.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from orchestrator.exceptions import (
    AgentInvocationError,
    AgentTimeoutError,
    PromptNotAllowedForAgentError,
    ProviderConfigNotFoundError,
    ProviderDisabledError,
)
from orchestrator.execution.http_invoker import HttpAgentInvoker
from orchestrator.models import Agent, AgentCapability, AgentPriority, AgentStatus, AgentTask
from orchestrator.prompts.prompt_manager import PromptManager
from orchestrator.prompts.prompt_registry import PromptRegistry
from orchestrator.providers.models import ProviderConfig

ENV_VAR = "ANTHROPIC_API_KEY"


@dataclass
class FakeProviderRegistry:
    """Test double for ModelProviderRegistry: get_config() returns a
    fixed ProviderConfig or raises a fixed exception, without ever
    reading config/model_providers.yaml."""

    config: ProviderConfig | None = None
    error: Exception | None = None

    def get_config(self, agent_name: str) -> ProviderConfig:
        if self.error is not None:
            raise self.error
        assert self.config is not None
        return self.config


def _agent(name: str = "claude_code") -> Agent:
    return Agent(
        name=name,
        provider="anthropic",
        capabilities=(AgentCapability(name="documentation"),),
        supported_tasks=("documentation",),
        config_reference="agents/claude-code/config",
        status=AgentStatus.ACTIVE,
        priority=AgentPriority.HIGH,
    )


def _task() -> AgentTask:
    return AgentTask(task_type="documentation", description="write the README")


def _config() -> ProviderConfig:
    return ProviderConfig(
        provider_type="anthropic",
        enabled=True,
        base_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        api_key_env_var=ENV_VAR,
        timeout_seconds=30.0,
    )


def _invoker_with_handler(handler, prompt_manager: PromptManager | None = None) -> HttpAgentInvoker:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    registry = FakeProviderRegistry(config=_config())
    return HttpAgentInvoker(
        provider_registry=registry, client=client, prompt_manager=prompt_manager
    )


# --------------------------------------------------------------------- #
# Success -> ExecutionResult translation
# --------------------------------------------------------------------- #


def test_invoke_success_returns_execution_result(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "sk-ant-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "README written."}]})

    invoker = _invoker_with_handler(handler)
    result = invoker.invoke(_agent(), _task())

    assert result.output == "README written."
    assert result.exit_code == 0
    assert result.succeeded()
    assert result.duration_seconds >= 0


def test_invoke_passes_task_description_as_prompt(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "sk-ant-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert b"write the README" in request.read()
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    invoker = _invoker_with_handler(handler)
    invoker.invoke(_agent(), _task())


# --------------------------------------------------------------------- #
# Error mapping: ProviderTimeoutError -> AgentTimeoutError
# --------------------------------------------------------------------- #


def test_invoke_timeout_maps_to_agent_timeout_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "sk-ant-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    invoker = _invoker_with_handler(handler)
    with pytest.raises(AgentTimeoutError) as exc_info:
        invoker.invoke(_agent(), _task())

    assert exc_info.value.agent_name == "claude_code"
    assert exc_info.value.timeout_seconds == 30.0


# --------------------------------------------------------------------- #
# Error mapping: ProviderRequestError -> AgentInvocationError
# --------------------------------------------------------------------- #


def test_invoke_request_failure_maps_to_agent_invocation_error(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(ENV_VAR, "sk-ant-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})

    invoker = _invoker_with_handler(handler)
    with pytest.raises(AgentInvocationError) as exc_info:
        invoker.invoke(_agent(), _task())

    assert exc_info.value.agent_name == "claude_code"
    assert "401" in exc_info.value.reason


def test_invoke_missing_api_key_maps_to_agent_invocation_error(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv(ENV_VAR, raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    invoker = _invoker_with_handler(handler)
    with pytest.raises(AgentInvocationError):
        invoker.invoke(_agent(), _task())


# --------------------------------------------------------------------- #
# Registry-level errors: NOT translated, propagate unchanged
# (config bugs -- ExecutionEngine's retry loop only catches
#  AgentTimeoutError / AgentInvocationError, so these surface immediately)
# --------------------------------------------------------------------- #


def test_invoke_propagates_provider_config_not_found_unchanged():
    registry = FakeProviderRegistry(error=ProviderConfigNotFoundError("claude_code"))
    invoker = HttpAgentInvoker(provider_registry=registry)

    with pytest.raises(ProviderConfigNotFoundError):
        invoker.invoke(_agent(), _task())


def test_invoke_propagates_provider_disabled_unchanged():
    registry = FakeProviderRegistry(error=ProviderDisabledError("aider", "openai"))
    invoker = HttpAgentInvoker(provider_registry=registry)

    with pytest.raises(ProviderDisabledError):
        invoker.invoke(_agent("aider"), _task())


# --------------------------------------------------------------------- #
# Phase-08: prompt resolution (ADR-0006 decision 6)
# --------------------------------------------------------------------- #


def test_prompt_id_none_uses_description_unchanged_from_phase07(monkeypatch: pytest.MonkeyPatch):
    """Regression guard: when task.prompt_id is None, behavior must be
    byte-for-byte identical to pre-Phase-08."""
    monkeypatch.setenv(ENV_VAR, "sk-ant-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert b"write the README" in request.read()
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    invoker = _invoker_with_handler(handler)
    result = invoker.invoke(_agent(), _task())
    assert result.output == "ok"


def test_prompt_id_set_renders_via_prompt_manager(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "sk-ant-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b"write the README" not in body
        assert b"add two numbers" in body
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    invoker = _invoker_with_handler(
        handler, prompt_manager=PromptManager(registry=PromptRegistry())
    )
    task = AgentTask(
        task_type="documentation",
        description="write the README",
        prompt_id="code_generation",
        prompt_variables={"task_description": "add two numbers", "language": "Python"},
    )
    result = invoker.invoke(_agent("codex"), task)
    assert result.output == "ok"


def test_prompt_not_allowed_for_agent_propagates_uncaught(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ENV_VAR, "sk-ant-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not be called -- prompt resolution must fail first")

    invoker = _invoker_with_handler(
        handler, prompt_manager=PromptManager(registry=PromptRegistry())
    )
    task = AgentTask(
        task_type="documentation",
        description="x",
        prompt_id="code_generation",  # not allowed for claude_code
        prompt_variables={"task_description": "x"},
    )
    with pytest.raises(PromptNotAllowedForAgentError):
        invoker.invoke(_agent("claude_code"), task)
