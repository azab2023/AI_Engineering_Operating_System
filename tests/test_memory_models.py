"""Unit tests for orchestrator.memory.models.MemoryEntry."""

from __future__ import annotations

import pytest

from orchestrator.memory.models import MemoryEntry


def test_memory_entry_defaults():
    entry = MemoryEntry(key="last_task_id", value="abc-123")

    assert entry.key == "last_task_id"
    assert entry.value == "abc-123"
    assert entry.scope == "default"
    assert entry.metadata == {}
    assert entry.id
    assert entry.created_at.tzinfo is not None
    assert entry.updated_at.tzinfo is not None


def test_memory_entry_custom_scope_and_metadata():
    entry = MemoryEntry(
        key="preferred_model",
        value="claude",
        scope="agent:claude-code",
        metadata={"source": "settings"},
    )

    assert entry.scope == "agent:claude-code"
    assert entry.metadata == {"source": "settings"}


def test_memory_entry_two_instances_get_distinct_ids():
    first = MemoryEntry(key="k", value="v")
    second = MemoryEntry(key="k", value="v")

    assert first.id != second.id


def test_memory_entry_empty_key_raises():
    with pytest.raises(ValueError, match="key"):
        MemoryEntry(key="", value="v")


def test_memory_entry_empty_scope_raises():
    with pytest.raises(ValueError, match="scope"):
        MemoryEntry(key="k", value="v", scope="")
