"""Integration tests: a real ExecutionEngine + real Orchestrator + real
AgentRegistry, driven by HttpAgentInvoker instead of
SubprocessAgentInvoker.

Purpose: demonstrate ADR-0005's central claim -- ExecutionEngine works
completely unchanged when handed an HttpAgentInvoker instead of a
SubprocessAgentInvoker, because both implement the same AgentInvoker
Protocol. ExecutionEngine, Orchestrator, and AgentRegistry are the real,
unmodified Phase-04/05/06 classes here, not test doubles. Only the
network boundary (httpx.Client -> httpx.MockTransport) is faked, so no
real network call is ever made and no real config/model_providers.yaml
entry needs a live credential.
"""

from __future__ import annotations

import httpx
import pytest

from orchestrator.core import Orchestrator
from orchestrator.execution.engine import ExecutionEngine
from orchestrator.execution.http_invoker import HttpAgentInvoker
from orchestrator.execution.models import RetryPolicy
from orchestrator.models import AgentTask, ExecutionState
from orchestrator.providers.provider_registry import (
    DEFAULT_MODEL_PROVIDERS_PATH,
    ModelProviderRegistry,
)
from orchestrator.registry import DEFAULT_REGISTRY_PATH, AgentRegistry

NO_DELAY = RetryPolicy(max_attempts=3, initial_backoff_seconds=0)


@pytest.fixture
def orchestrator() -> Orchestrator:
    return Orchestrator(AgentRegistry(DEFAULT_REGISTRY_PATH))


def _engine_with_handler(orchestrator: Orchestrator, handler) -> ExecutionEngine:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider_registry = ModelProviderRegistry(DEFAULT_MODEL_PROVIDERS_PATH)
    invoker = HttpAgentInvoker(provider_registry=provider_registry, client=client)
    return ExecutionEngine(orchestrator, invoker=invoker, retry_policy=NO_DELAY)


def test_execution_engine_routes_and_succeeds_via_http_invoker(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "api.anthropic.com" in str(request.url)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "Docs written."}]})

    task = AgentTask(task_type="documentation", description="write the README")
    execution = orchestrator.submit_task(task)
    assert execution.state == ExecutionState.PENDING

    engine = _engine_with_handler(orchestrator, handler)
    result = engine.execute(execution)

    assert result.state == ExecutionState.AWAITING_APPROVAL
    assert result.result == "Docs written."
    # documentation is routed to claude_code (priority: high) over gemini
    # (priority: medium) per config/agent_registry.yaml.
    assert result.assigned_agent is not None
    assert result.assigned_agent.name == "claude_code"


def test_execution_engine_retries_transient_http_failure_then_succeeds(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, text="service unavailable")
        return httpx.Response(200, json={"content": [{"type": "text", "text": "Docs written."}]})

    task = AgentTask(task_type="documentation", description="write the README")
    execution = orchestrator.submit_task(task)

    engine = _engine_with_handler(orchestrator, handler)
    result = engine.execute(execution)

    assert result.state == ExecutionState.AWAITING_APPROVAL
    assert result.result == "Docs written."
    assert attempts["count"] == 2


def test_execution_engine_retries_timeout_then_exhausts_and_fails(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    task = AgentTask(task_type="documentation", description="write the README")
    execution = orchestrator.submit_task(task)

    engine = _engine_with_handler(orchestrator, handler)
    result = engine.execute(execution)

    assert result.state == ExecutionState.FAILED
    assert result.error is not None
    assert "claude_code" in result.error


def test_execution_engine_with_http_invoker_never_calls_subprocess(
    orchestrator: Orchestrator, monkeypatch: pytest.MonkeyPatch
):
    """Sanity check that HttpAgentInvoker never shells out -- the whole
    point of this AgentInvoker implementation."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    subprocess_calls = {"count": 0}

    import subprocess

    original_run = subprocess.run

    def spy_run(*args, **kwargs):
        subprocess_calls["count"] += 1
        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy_run)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    task = AgentTask(task_type="documentation", description="write the README")
    execution = orchestrator.submit_task(task)

    engine = _engine_with_handler(orchestrator, handler)
    engine.execute(execution)

    assert subprocess_calls["count"] == 0
