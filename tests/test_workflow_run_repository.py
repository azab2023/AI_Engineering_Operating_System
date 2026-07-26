"""Unit tests for orchestrator.workflow.repository.InMemoryWorkflowRunRepository."""

from __future__ import annotations

import pytest

from orchestrator.exceptions import UnknownWorkflowRunError, WorkflowRunAlreadyExistsError
from orchestrator.workflow.models import WorkflowRun, WorkflowRunState
from orchestrator.workflow.repository import InMemoryWorkflowRunRepository


@pytest.fixture
def repository() -> InMemoryWorkflowRunRepository:
    return InMemoryWorkflowRunRepository()


def test_add_and_get(repository: InMemoryWorkflowRunRepository):
    run = WorkflowRun(workflow_id="w1")
    repository.add(run)
    assert repository.get(run.run_id) is run


def test_add_duplicate_raises(repository: InMemoryWorkflowRunRepository):
    run = WorkflowRun(workflow_id="w1")
    repository.add(run)
    with pytest.raises(WorkflowRunAlreadyExistsError):
        repository.add(run)


def test_get_unknown_raises(repository: InMemoryWorkflowRunRepository):
    with pytest.raises(UnknownWorkflowRunError):
        repository.get("does-not-exist")


def test_update_unknown_raises(repository: InMemoryWorkflowRunRepository):
    run = WorkflowRun(workflow_id="w1")
    with pytest.raises(UnknownWorkflowRunError):
        repository.update(run)


def test_update_persists_changes(repository: InMemoryWorkflowRunRepository):
    run = WorkflowRun(workflow_id="w1")
    repository.add(run)
    run.state = WorkflowRunState.RUNNING
    repository.update(run)
    assert repository.get(run.run_id).state == WorkflowRunState.RUNNING


def test_list_all_and_filtered(repository: InMemoryWorkflowRunRepository):
    run_a = WorkflowRun(workflow_id="w1", state=WorkflowRunState.RUNNING)
    run_b = WorkflowRun(workflow_id="w2", state=WorkflowRunState.FAILED)
    repository.add(run_a)
    repository.add(run_b)

    assert {r.run_id for r in repository.list()} == {run_a.run_id, run_b.run_id}
    assert [r.run_id for r in repository.list(WorkflowRunState.RUNNING)] == [run_a.run_id]
    assert [r.run_id for r in repository.list(WorkflowRunState.FAILED)] == [run_b.run_id]


def test_contains(repository: InMemoryWorkflowRunRepository):
    run = WorkflowRun(workflow_id="w1")
    assert run.run_id not in repository
    repository.add(run)
    assert run.run_id in repository
